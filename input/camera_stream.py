# DroidCam 영상 수신 (OpenCV)
import threading
import time

import cv2


class CameraStream:
    """백그라운드 스레드에서 프레임을 계속 읽어 항상 최신 프레임만 보관한다.

    DroidCam(IP 스트림)은 프레임이 버퍼에 쌓이면 지연이 커지므로,
    처리 속도와 상관없이 가장 최근 프레임을 꺼내 쓰도록 한다.
    """

    def __init__(self, source, width=640, reconnect_delay=2.0):
        self.source = source
        self.width = width
        self.reconnect_delay = reconnect_delay
        self._cap = None
        self._frame = None
        self._frame_time = 0.0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        self._open()
        self._running = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return self

    def wait_ready(self, timeout=5.0):
        """첫 프레임이 들어올 때까지 기다린다. 시간 안에 오면 True."""
        end = time.time() + timeout
        while time.time() < end:
            if self._frame is not None:
                return True
            time.sleep(0.05)
        return False

    def read(self):
        """(프레임, 수신 시각)을 반환한다. 아직 프레임이 없으면 (None, 0.0)."""
        with self._lock:
            if self._frame is None:
                return None, 0.0
            return self._frame.copy(), self._frame_time

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()

    def _open(self):
        if self._cap is not None:
            self._cap.release()
        if isinstance(self.source, int):
            # Windows에서는 DirectShow 백엔드가 장치 연결이 빠르다
            self._cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
        else:
            self._cap = cv2.VideoCapture(self.source)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _reader(self):
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(self.reconnect_delay)
                self._open()
                continue
            h, w = frame.shape[:2]
            if w != self.width:
                frame = cv2.resize(frame, (self.width, int(h * self.width / w)))
            with self._lock:
                self._frame = frame
                self._frame_time = time.time()
