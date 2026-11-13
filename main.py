# OpticCall 전체 실행
#   python main.py                       -> .env의 카메라·텔레그램 설정, 공통 기준으로 누구나 사용
#   python main.py --user patient01      -> 그 사람의 응시 시간(profiles/users.json)·개인 보정값 사용
#   python main.py --camera 10.22.9.230  -> 이번 실행만 다른 카메라 (DroidCam IP 또는 장치 번호)
#   python main.py --no-window           -> 영상 창 없이 실행 (종료: Ctrl+C)
#   python main.py --no-notify           -> 텔레그램 알림 없이 (시연·연습용)
# 종료: 영상 창에서 q 또는 ESC
#
#   카메라(Input) → 얼굴·눈 분석(Vision) → 호출 판정(Decision) → 음성·알림(Output)
import argparse
import csv
import os
import sys
import time
from datetime import datetime

import cv2

import config
from decision.call_controller import ASKING, COOLDOWN, IDLE, WAITING, CallController
from input.camera_stream import CameraStream, check_reachable
from output.notifier import Notifier
from output.tts import Speaker
from output.voice_guide import VoiceGuide
from profiles.profile_manager import load_profile
from vision.face_landmarker import FaceLandmarkDetector
from vision.features import FeatureExtractor, load_calibration

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "call_history.csv")
STATE_COLOR = {IDLE: (200, 200, 200), ASKING: (0, 200, 255), WAITING: (255, 200, 0), COOLDOWN: (160, 160, 160)}
EVENT_KO = {"ASK": "질문", "CALL": "호출 확정", "CANCEL": "취소", "TIMEOUT": "응답 없음", "READY": "다시 대기"}


class CallHistory:
    """호출 기록을 logs/call_history.csv에 남긴다 (엑셀로 열 수 있음)."""

    def __init__(self, user, bed):
        os.makedirs(LOG_DIR, exist_ok=True)
        new = not os.path.exists(LOG_FILE)
        self._f = open(LOG_FILE, "a", newline="", encoding="utf-8-sig")
        self._w = csv.writer(self._f)
        if new:
            self._w.writerow(["시각", "사용자", "침상", "이벤트", "내용"])
        self.user = user or "(공통)"
        self.bed = bed
        self.counts = {}

    def write(self, event, detail=""):
        self.counts[event] = self.counts.get(event, 0) + 1
        self._w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.user, self.bed, event, detail])
        self._f.flush()

    def close(self):
        self._f.close()


def startup(args):
    """시작 전 점검. 문제가 있으면 무엇을 하면 되는지 알려 주고 멈춘다."""
    print("── OpticCall 시작 점검 ─────────────────────")
    source = config.parse_camera_source(args.camera) if args.camera else config.CAMERA_SOURCE
    ok, why = check_reachable(source)
    if not ok:
        print(f"❌ 카메라: {why}")
        print("   1) 휴대폰 DroidCam 앱이 켜져 있고 화면이 꺼지지 않았는지")
        print("   2) 앱에 보이는 IP가 .env의 CAMERA_SOURCE와 같은지")
        print("   3) 휴대폰과 노트북이 같은 와이파이인지 확인하세요.")
        return None
    stream = CameraStream(source, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()
    if not stream.wait_ready(8.0):
        stream.stop()
        print(f"❌ 카메라: 연결은 되지만 영상이 오지 않습니다 ({source})")
        print("   DroidCam Client나 다른 테스트 창이 카메라를 쓰고 있으면 닫고 다시 실행하세요.")
        return None
    print(f"✅ 카메라: {source}")

    dwell = load_profile(args.user)
    calib = load_calibration(args.user)
    print(f"✅ 사용자: {args.user or '(공통 기준)'}  응시 {dwell['first_gaze_sec']:g}초 · "
          f"확정 {dwell['confirm_gaze_sec']:g}초 · 취소 {dwell['cancel_close_sec']:g}초")

    notifier = None
    if args.no_notify:
        print("⚠️  알림: 끔 (--no-notify)")
    else:
        notifier = Notifier()
        ok, info = notifier.check()
        if ok:
            print(f"✅ 알림: 텔레그램 {info} → 수신자 {len(notifier.chat_ids)}명, 침상 '{notifier.bed}'")
        else:
            print(f"⚠️  알림: {info}")
            print("   이대로 호출하면 '알림을 보내지 못했습니다'라고 안내합니다. (python telegram_setup.py 로 설정)")
    print("────────────────────────────────────────────")
    return stream, dwell, calib, notifier


def draw(frame, controller, eye, now, recent):
    state = controller.state
    label, ratio = controller.progress(now)
    cv2.putText(frame, state, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, STATE_COLOR[state], 3)
    cv2.putText(frame, label, (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    color = (0, 0, 255) if "cancel" in label else (0, 220, 0)
    cv2.rectangle(frame, (10, 82), (310, 96), (80, 80, 80), 1)
    cv2.rectangle(frame, (10, 82), (10 + int(300 * ratio), 96), color, -1)
    if eye is None:
        cv2.putText(frame, "FACE: NOT FOUND", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    else:
        cv2.putText(frame, f"GAZE {'ON' if eye.gazing else 'off'}   EYE {'CLOSED' if eye.eyes_closed else 'open'}",
                    (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    h = frame.shape[0]
    for i, line in enumerate(recent):
        cv2.putText(frame, line, (10, h - 12 - 20 * (len(recent) - 1 - i)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def main():
    parser = argparse.ArgumentParser(description="OpticCall 비접촉식 시선 추적 간호 호출")
    parser.add_argument("--user", help="응시 시간·보정값을 불러올 사람 이름 (없으면 공통 기준)")
    parser.add_argument("--camera", help="이번 실행만 쓸 카메라 (DroidCam IP 또는 장치 번호)")
    parser.add_argument("--no-window", action="store_true", help="영상 창 없이 실행")
    parser.add_argument("--no-notify", action="store_true", help="텔레그램 알림 없이 실행")
    args = parser.parse_args()

    ready = startup(args)
    if ready is None:
        sys.exit(1)
    stream, dwell, calib, notifier = ready

    detector = FaceLandmarkDetector()
    extractor = FeatureExtractor(calib)
    controller = CallController(dwell)
    guide = VoiceGuide(Speaker(), dwell)
    history = CallHistory(args.user, notifier.bed if notifier else "-")
    history.write("START")
    guide.start()
    print("실행 중입니다." + (" 종료: Ctrl+C" if args.no_window else " 종료: 영상 창에서 q 또는 ESC"))

    recent = []
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
            guide.sync(controller)                 # 음성이 끝난 시각을 판정에 전달
            if notifier:
                for r in notifier.poll_results():
                    if r.ok:
                        history.write("ALERT_SENT", f"{r.count}회째 호출, {len(r.sent)}명 수신, "
                                                    f"{r.seconds:.1f}초 걸림, 재시도 {r.retries}번")
                    else:
                        history.write("ALERT_FAILED", "; ".join(f"{c}: {why}" for c, why in r.failed))
                        guide.notify_failed()

            for event in controller.update(eye, now):
                stamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{stamp}] {EVENT_KO[event]}")
                recent = (recent + [f"{stamp}  {event}"])[-5:]
                if event != "READY":
                    history.write(event)
                if event == "CALL":
                    if notifier:
                        notifier.notify_call()
                    else:
                        history.write("ALERT_SKIPPED", "--no-notify")
                guide.on_event(event)

            if not args.no_window:
                draw(frame, controller, eye, now, recent)
                cv2.imshow("OpticCall", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        history.write("STOP")
        c = history.counts
        print(f"\n종료합니다. 이번 실행: 질문 {c.get('ASK', 0)}회 · 호출 {c.get('CALL', 0)}회 · "
              f"취소 {c.get('CANCEL', 0)}회 · 응답 없음 {c.get('TIMEOUT', 0)}회 "
              f"(알림 실패 {c.get('ALERT_FAILED', 0)}회)")
        print(f"호출 기록: {LOG_FILE}")
        history.close()
        stream.stop()
        detector.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
