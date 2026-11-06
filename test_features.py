# 4단계 특징값 실시간 확인
#   python test_features.py --user 이름               -> 그 사람의 보정값으로 판정 표시
#   python test_features.py --user 이름 --headless 10 -> 창 없이 10초간 판정 비율만 출력
# 종료: 영상 창에서 q 또는 ESC
import argparse
import os
import time

import cv2

import config
from input.camera_stream import CameraStream
from vision.face_landmarker import FaceLandmarkDetector
from vision.features import FeatureExtractor, load_calibration

GREEN = (0, 220, 0)
RED = (0, 0, 255)
GRAY = (160, 160, 160)
WHITE = (255, 255, 255)


def put(frame, text, y, color=WHITE, scale=0.55, thick=1):
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


def main():
    parser = argparse.ArgumentParser(description="OpticCall 특징값 실시간 확인")
    parser.add_argument("--user", help="보정값을 불러올 사람 이름 (없으면 기본값)")
    parser.add_argument("--headless", type=float, metavar="초", help="창 없이 지정한 시간 동안만 실행")
    args = parser.parse_args()
    headless = args.headless is not None
    duration = args.headless or 0.0

    calib = load_calibration(args.user)
    path = config.calibration_file(args.user)
    print("보정값:", path if os.path.exists(path) else "기본값 (보정 전)")

    stream = CameraStream(config.CAMERA_SOURCE, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()
    detector = FaceLandmarkDetector()
    extractor = FeatureExtractor(calib)

    last_frame_time = 0.0
    gaze_since = closed_since = None     # 연속 응시 / 연속 눈 감김 시작 시각
    total = gaze_frames = closed_frames = no_face = 0
    start = time.time()
    try:
        while not (headless and time.time() - start > duration):
            frame, frame_time = stream.read()
            if frame is None or frame_time == last_frame_time:
                time.sleep(0.005)
                continue
            last_frame_time = frame_time
            now = time.time()

            state = extractor.update(detector.detect(frame))
            total += 1
            if state is None:
                no_face += 1
                gaze_since = closed_since = None
            else:
                gaze_frames += state.gazing
                closed_frames += state.eyes_closed
                gaze_since = (gaze_since or now) if state.gazing else None
                closed_since = (closed_since or now) if state.eyes_closed else None

            if headless:
                continue

            if state is None:
                put(frame, "FACE: NOT FOUND", 35, RED, 0.9, 2)
            else:
                gaze_txt = f"GAZE: ON  {now - gaze_since:4.1f}s" if gaze_since else "GAZE: OFF"
                eye_txt = f"EYE: CLOSED  {now - closed_since:4.1f}s" if closed_since else "EYE: OPEN"
                put(frame, gaze_txt, 35, GREEN if state.gazing else GRAY, 0.9, 2)
                put(frame, eye_txt, 70, RED if state.eyes_closed else GRAY, 0.9, 2)
                c = calib
                put(frame, f"EAR   {state.ear:.3f}  (closed <= {c['ear_closed']:.3f})", 105)
                put(frame, f"blink {state.blink:.2f}   (closed >= {c['blink_closed']:.2f})", 128)
                put(frame, f"iris  h {state.iris_h - c['iris_h_center']:+.3f}  v {state.iris_v - c['iris_v_center']:+.3f}", 151)
                put(frame, f"head  yaw {state.yaw - c['yaw_center']:+5.1f}  pitch {state.pitch - c['pitch_center']:+5.1f}", 174)
            cv2.imshow("OpticCall - Feature Test", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        stream.stop()
        detector.close()
        cv2.destroyAllWindows()

    if total:
        print(f"처리 프레임 {total} | 응시 {gaze_frames / total * 100:.1f}% | "
              f"눈 감음 {closed_frames / total * 100:.1f}% | 얼굴 없음 {no_face / total * 100:.1f}%")


if __name__ == "__main__":
    main()
