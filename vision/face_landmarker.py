# MediaPipe 안면 랜드마크 추출
import time
from dataclasses import dataclass

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# ── 랜드마크 번호 (MediaPipe Face Mesh 478점 기준) ─────────────
# 화면 기준이 아니라 "환자 본인 기준" 좌/우
# EAR 계산용 6점: [눈꼬리 A, 위1, 위2, 눈꼬리 B, 아래2, 아래1]
# 두 눈 모두 A → B 방향이 화면의 왼쪽 → 오른쪽이 되도록 배열
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
LEFT_EYE = [362, 385, 387, 263, 373, 380]
# 홍채: 첫 번째가 중심, 나머지 4개가 테두리
RIGHT_IRIS = [468, 469, 470, 471, 472]
LEFT_IRIS = [473, 474, 475, 476, 477]


@dataclass
class FaceResult:
    landmarks: list          # 478개 (x, y, z), x·y는 0~1 정규화 좌표
    blendshapes: dict        # 표정 계수 이름 -> 0~1 (예: eyeBlinkLeft)
    matrix: object           # 얼굴 회전·이동 4x4 행렬 (numpy), 고개 방향 계산용
    width: int               # 원본 프레임 크기 (픽셀 변환용)
    height: int

    def px(self, index):
        """랜드마크 하나를 픽셀 좌표 (x, y)로 변환한다."""
        lm = self.landmarks[index]
        return int(lm.x * self.width), int(lm.y * self.height)


class FaceLandmarkDetector:
    """영상 프레임에서 얼굴 1개의 랜드마크 478개를 추출한다 (VIDEO 모드)."""

    def __init__(self, model_path="models/face_landmarker.task"):
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_ts = 0

    def detect(self, frame_bgr):
        """얼굴이 있으면 FaceResult, 없으면 None을 반환한다."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # VIDEO 모드는 타임스탬프가 반드시 증가해야 한다
        ts = max(int(time.monotonic() * 1000), self._last_ts + 1)
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)

        if not result.face_landmarks:
            return None
        blendshapes = {}
        if result.face_blendshapes:
            blendshapes = {b.category_name: b.score for b in result.face_blendshapes[0]}
        matrix = None
        if result.facial_transformation_matrixes:
            matrix = result.facial_transformation_matrixes[0]
        h, w = frame_bgr.shape[:2]
        return FaceResult(result.face_landmarks[0], blendshapes, matrix, w, h)

    def close(self):
        self._landmarker.close()
