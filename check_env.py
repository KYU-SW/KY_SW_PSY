# 1단계 개발 환경 확인용 스크립트
import sys

import cv2
import mediapipe as mp
import pyttsx3
import requests
import dotenv
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

print(f"Python      : {sys.version.split()[0]}")
print(f"OpenCV      : {cv2.__version__}")
print(f"MediaPipe   : {mp.__version__}")
print(f"requests    : {requests.__version__}")

# 모델 파일 로드 확인
options = vision.FaceLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path="models/face_landmarker.task"),
    num_faces=1,
)
with vision.FaceLandmarker.create_from_options(options):
    print("FaceLandmarker 모델 로드 : OK")

# 음성 엔진 및 한국어 음성 확인
engine = pyttsx3.init()
voices = engine.getProperty("voices")
korean = [v for v in voices if "ko" in str(v.languages).lower() or "korean" in v.name.lower()]
print(f"TTS 음성 수  : {len(voices)}")
for v in voices:
    print(f"  - {v.name}")
print("한국어 음성 : " + (korean[0].name if korean else "없음"))
