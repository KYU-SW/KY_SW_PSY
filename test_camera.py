# 2단계 카메라 연결 테스트
#   python test_camera.py                 -> config.py의 CAMERA_SOURCE 사용
#   python test_camera.py 192.168.0.12    -> DroidCam Wi-Fi (IP만 입력)
#   python test_camera.py 1               -> 장치 번호 1번 카메라
#   python test_camera.py --list          -> 사용 가능한 장치 번호 찾기
# 종료: 영상 창에서 q 또는 ESC
import sys
import time

import cv2

import config
from input.camera_stream import CameraStream


def parse_source(arg):
    if arg.isdigit():
        return int(arg)
    if arg.startswith("http"):
        return arg
    return f"http://{arg}:4747/video"


def list_devices(max_index=5):
    print("장치 번호 확인 중...")
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        if ok:
            h, w = frame.shape[:2]
            print(f"  {i}번: 사용 가능 ({w}x{h})")
        else:
            print(f"  {i}번: 없음")
        cap.release()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_devices()
        return

    source = parse_source(sys.argv[1]) if len(sys.argv) > 1 else config.CAMERA_SOURCE
    print(f"카메라 연결: {source}")
    stream = CameraStream(source, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()

    frames, fps, last_frame_time, fps_start = 0, 0.0, 0.0, time.time()
    try:
        while True:
            frame, frame_time = stream.read()
            if frame is None:
                time.sleep(0.05)
                continue

            if frame_time != last_frame_time:   # 새 프레임만 FPS 계산에 포함
                frames += 1
                last_frame_time = frame_time
            if time.time() - fps_start >= 1.0:
                fps = frames / (time.time() - fps_start)
                frames, fps_start = 0, time.time()

            delay = time.time() - frame_time
            color = (0, 200, 0) if fps >= 15 else (0, 0, 255)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.putText(frame, f"Delay: {delay * 1000:.0f} ms", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.imshow("OpticCall - Camera Test", frame)

            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        stream.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
