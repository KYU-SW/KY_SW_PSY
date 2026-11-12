# 5~6단계 호출 흐름 실시간 확인 (실제 음성 안내 포함, 알림은 아직 없음)
#   python test_call_flow.py                 -> 공통 기준 + 실제 음성
#   python test_call_flow.py --user friend01 -> 그 사람의 보정값·응시 시간
#   python test_call_flow.py --no-voice      -> 음성 없이 음성 길이만 가정
# 종료: 영상 창에서 q 또는 ESC
import argparse
import time

import cv2

import config
from decision.call_controller import ASKING, COOLDOWN, IDLE, WAITING, CallController
from input.camera_stream import CameraStream
from output.tts import Speaker
from output.voice_guide import VoiceGuide
from profiles.profile_manager import load_profile
from vision.face_landmarker import FaceLandmarkDetector
from vision.features import FeatureExtractor, load_calibration

STATE_COLOR = {IDLE: (200, 200, 200), ASKING: (0, 200, 255), WAITING: (255, 200, 0), COOLDOWN: (160, 160, 160)}
EVENT_TEXT = {
    "ASK": "ASK   - (voice) Do you want to call?",
    "CALL": "CALL  - nurse called!",
    "CANCEL": "CANCEL- call canceled",
    "TIMEOUT": "TIMEOUT - no answer, back to idle",
    "READY": "READY - cooldown over",
}
EVENT_KO = {"ASK": "질문", "CALL": "호출 확정", "CANCEL": "취소", "TIMEOUT": "시간 초과", "READY": "다시 대기"}


def draw_bar(frame, x, y, w, h, ratio, color):
    cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 80, 80), 1)
    cv2.rectangle(frame, (x, y), (x + int(w * ratio), y + h), color, -1)


def main():
    parser = argparse.ArgumentParser(description="OpticCall 호출 흐름 확인")
    parser.add_argument("--user", help="보정값·응시 시간을 불러올 사람 이름")
    parser.add_argument("--no-voice", action="store_true", help="음성 없이 아래 길이만 가정")
    parser.add_argument("--question-sec", type=float, default=7.8, help="--no-voice일 때 질문 음성 길이 가정")
    parser.add_argument("--announce-sec", type=float, default=4.0, help="--no-voice일 때 결과 안내 길이 가정")
    args = parser.parse_args()

    dwell = load_profile(args.user)
    print(f"사용자: {args.user or '(기본값)'}  응시 시간: {dwell}")
    stream = CameraStream(config.CAMERA_SOURCE, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()
    if not stream.wait_ready():
        stream.stop()
        print(f"카메라 영상이 들어오지 않습니다: {config.CAMERA_SOURCE}")
        return
    detector = FaceLandmarkDetector()
    extractor = FeatureExtractor(load_calibration(args.user))
    controller = CallController(dwell)
    guide = None if args.no_voice else VoiceGuide(Speaker(), dwell)
    if guide:
        guide.start()            # 시작 안내 = 소리 확인

    log = []                  # 화면에 보일 최근 이벤트
    question_end = None       # 질문 음성이 끝나는 시각 (6단계에서 실제 음성으로 바뀜)
    announce_end = None       # 결과 안내 음성이 끝나는 시각
    start = time.time()
    last_frame_time = 0.0
    try:
        while True:
            frame, frame_time = stream.read()
            if frame is None or frame_time == last_frame_time:
                time.sleep(0.005)
                continue
            last_frame_time = frame_time
            now = time.time()

            eye = extractor.update(detector.detect(frame))
            if guide:
                guide.sync(controller)          # 실제 음성이 끝난 시각을 전달
            else:
                if question_end and now >= question_end:
                    controller.question_finished(now)
                    question_end = None
                if announce_end and now >= announce_end:
                    controller.announcement_finished(now)
                    announce_end = None
            for event in controller.update(eye, now):
                if guide:
                    guide.on_event(event)
                elif event == "ASK":
                    question_end = now + args.question_sec
                elif event in ("CALL", "CANCEL", "TIMEOUT"):
                    announce_end = now + args.announce_sec
                stamp = now - start
                log.append(f"{stamp:6.1f}s  {EVENT_TEXT[event]}")
                print(f"[{stamp:6.1f}s] {EVENT_KO[event]}")
            log = log[-5:]

            state = controller.state
            label, ratio = controller.progress(now)
            cv2.putText(frame, state, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, STATE_COLOR[state], 3)
            cv2.putText(frame, label, (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            bar_color = (0, 0, 255) if "cancel" in label else (0, 220, 0)
            draw_bar(frame, 10, 82, 300, 14, ratio, bar_color)
            if eye is None:
                cv2.putText(frame, "FACE: NOT FOUND", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            else:
                cv2.putText(frame, f"GAZE {'ON' if eye.gazing else 'off'}   EYE {'CLOSED' if eye.eyes_closed else 'open'}",
                            (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            h = frame.shape[0]
            for i, line in enumerate(log):
                cv2.putText(frame, line, (10, h - 12 - 20 * (len(log) - 1 - i)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.imshow("OpticCall - Call Flow Test", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        stream.stop()
        detector.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
