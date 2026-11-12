# 1단계 개발 환경 확인용 스크립트
import sys

import cv2
import mediapipe as mp
import win32com.client
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

# 음성 엔진(Windows SAPI) 및 한국어 음성 확인
voice = win32com.client.Dispatch("SAPI.SpVoice")
voices = voice.GetVoices()
korean = voice.GetVoices("Language=412")
print(f"TTS 음성 수  : {voices.Count}")
for i in range(voices.Count):
    print(f"  - {voices.Item(i).GetDescription()}")
print("한국어 음성 : " + (korean.Item(0).GetDescription() if korean.Count else "없음"))
