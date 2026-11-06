# 3단계 얼굴 랜드마크 추출 테스트
#   python test_landmarks.py               -> 영상 창에 눈·홍채 점 표시
#   python test_landmarks.py --headless 10 -> 창 없이 10초간 검출률만 출력
# 종료: 영상 창에서 q 또는 ESC
import sys
import time

import cv2

import config
from input.camera_stream import CameraStream
from vision.face_landmarker import (FaceLandmarkDetector, LEFT_EYE, LEFT_IRIS,
                                    RIGHT_EYE, RIGHT_IRIS)

GREEN = (0, 220, 0)
RED = (0, 0, 255)
CYAN = (255, 255, 0)
WHITE = (255, 255, 255)


def draw_eye(frame, face, eye_idx, iris_idx):
    for i in eye_idx:
        cv2.circle(frame, face.px(i), 2, GREEN, -1)
    center = face.px(iris_idx[0])
    edge = face.px(iris_idx[1])
    radius = max(2, int(((center[0] - edge[0]) ** 2 + (center[1] - edge[1]) ** 2) ** 0.5))
    cv2.circle(frame, center, radius, CYAN, 1)
    cv2.circle(frame, center, 2, RED, -1)


def main():
    headless = len(sys.argv) > 1 and sys.argv[1] == "--headless"
    duration = float(sys.argv[2]) if headless and len(sys.argv) > 2 else 10.0

    stream = CameraStream(config.CAMERA_SOURCE, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()
    detector = FaceLandmarkDetector()

    last_frame_time = 0.0
    processed = detected = 0
    det_ms_total = 0.0
    fps, fps_count, fps_start = 0.0, 0, time.time()
    start = time.time()
    try:
        while True:
            frame, frame_time = stream.read()
            if frame is None or frame_time == last_frame_time:
                time.sleep(0.005)
                if headless and time.time() - start > duration:
                    break
                continue
            last_frame_time = frame_time

            t0 = time.perf_counter()
            face = detector.detect(frame)
            det_ms = (time.perf_counter() - t0) * 1000
            processed += 1
            det_ms_total += det_ms
            if face:
                detected += 1

            fps_count += 1
            if time.time() - fps_start >= 1.0:
                fps = fps_count / (time.time() - fps_start)
                fps_count, fps_start = 0, time.time()

            if headless:
                if time.time() - start > duration:
                    break
                continue

            if face:
                draw_eye(frame, face, RIGHT_EYE, RIGHT_IRIS)
                draw_eye(frame, face, LEFT_EYE, LEFT_IRIS)
                status, color = "FACE: OK", GREEN
                blink_l = face.blendshapes.get("eyeBlinkLeft", 0)
                blink_r = face.blendshapes.get("eyeBlinkRight", 0)
                cv2.putText(frame, f"blink L {blink_l:.2f}  R {blink_r:.2f}", (10, 90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)
            else:
                status, color = "FACE: NOT FOUND", RED
            cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.putText(frame, f"FPS: {fps:.1f}  detect: {det_ms:.0f} ms", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 1)
            cv2.imshow("OpticCall - Landmark Test", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        stream.stop()
        detector.close()
        cv2.destroyAllWindows()

    if processed:
        print(f"처리 프레임 : {processed}")
        print(f"얼굴 검출률 : {detected / processed * 100:.1f}%")
        print(f"평균 검출 시간 : {det_ms_total / processed:.1f} ms")


if __name__ == "__main__":
    main()
