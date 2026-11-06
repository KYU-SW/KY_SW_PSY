# 카메라 응시 여부 · EAR 계산
import json
import math
import os
from dataclasses import dataclass

import numpy as np

import config
from vision.face_landmarker import LEFT_EYE, LEFT_IRIS, RIGHT_EYE, RIGHT_IRIS


@dataclass
class EyeState:
    ear: float          # 눈 열림 정도 (두 눈 평균, 감으면 0에 가까움)
    blink: float        # MediaPipe 눈 감김 점수 (두 눈 평균, 0~1)
    iris_h: float       # 홍채 가로 위치 (0 = 화면 왼쪽 눈꼬리, 1 = 오른쪽 눈꼬리)
    iris_v: float       # 홍채 세로 위치 (+ 아래, - 위)
    yaw: float          # 고개 좌우 회전 (도)
    pitch: float        # 고개 상하 회전 (도)
    eyes_closed: bool
    gazing: bool        # 카메라를 보고 있는가


def load_calibration(user=None):
    """사용자의 개인 보정값을 불러온다. 이름이 없거나 보정 파일이 없으면 공통 기준."""
    calib = dict(config.DEFAULT_CALIBRATION)
    path = config.calibration_file(user)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            calib.update(json.load(f))
    return calib


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(face, idx):
    """EAR = (세로 거리 2개의 합) / (2 × 가로 거리)."""
    p = [face.px(i) for i in idx]
    width = _dist(p[0], p[3])
    if width == 0:
        return 0.0
    return (_dist(p[1], p[5]) + _dist(p[2], p[4])) / (2.0 * width)


def iris_position(face, eye_idx, iris_idx):
    """눈꼬리 두 점을 기준으로 홍채 중심의 (가로, 세로) 위치를 구한다."""
    a = np.array(face.px(eye_idx[0]), dtype=float)
    b = np.array(face.px(eye_idx[3]), dtype=float)
    c = np.array(face.px(iris_idx[0]), dtype=float)
    axis = b - a
    length2 = float(axis @ axis)
    if length2 == 0:
        return 0.5, 0.0
    h = float((c - a) @ axis) / length2
    normal = np.array([-axis[1], axis[0]])          # 눈 가로축에 수직 (화면 아래 방향이 +)
    v = float((c - (a + b) / 2) @ normal) / length2
    return h, v


def head_angles(matrix):
    """얼굴 변환 행렬에서 (yaw, pitch)를 도 단위로 구한다."""
    if matrix is None:
        return 0.0, 0.0
    r = np.asarray(matrix)[:3, :3]
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -r[2, 0]))))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    return yaw, pitch


def raw_features(face):
    """판정 전의 특징값을 두 눈 평균으로 계산한다."""
    ear = (eye_aspect_ratio(face, RIGHT_EYE) + eye_aspect_ratio(face, LEFT_EYE)) / 2
    blink = (face.blendshapes.get("eyeBlinkLeft", 0.0) + face.blendshapes.get("eyeBlinkRight", 0.0)) / 2
    rh, rv = iris_position(face, RIGHT_EYE, RIGHT_IRIS)
    lh, lv = iris_position(face, LEFT_EYE, LEFT_IRIS)
    yaw, pitch = head_angles(face.matrix)
    return {
        "ear": ear, "blink": blink,
        "iris_h": (rh + lh) / 2, "iris_v": (rv + lv) / 2,
        "yaw": yaw, "pitch": pitch,
    }


class FeatureExtractor:
    """프레임마다 특징값을 계산하고, 보정값을 기준으로 응시·눈 감김을 판정한다."""

    def __init__(self, calibration=None, tolerance=None, smoothing=config.SMOOTHING):
        self.calib = calibration or load_calibration()
        self.tol = tolerance or self.calib.get("tolerance") or config.GAZE_TOLERANCE
        self.smoothing = smoothing
        self._smoothed = None

    def reset(self):
        self._smoothed = None

    def update(self, face):
        """얼굴이 없으면 None, 있으면 EyeState를 반환한다."""
        if face is None:
            self.reset()
            return None
        raw = raw_features(face)
        if self._smoothed is None:
            self._smoothed = raw
        else:
            a = self.smoothing
            self._smoothed = {k: a * raw[k] + (1 - a) * self._smoothed[k] for k in raw}
        f = self._smoothed
        eyes_closed, gazing = judge(f, self.calib, self.tol)
        return EyeState(eyes_closed=eyes_closed, gazing=gazing, **f)


def judge(f, calib, tol):
    """특징값 f로 (눈 감음 여부, 카메라 응시 여부)를 판정한다."""
    eyes_closed = f["ear"] <= calib["ear_closed"] or f["blink"] >= calib["blink_closed"]
    # 눈을 감으면 홍채 위치를 믿을 수 없으므로 응시가 아닌 것으로 본다
    gazing = (
        not eyes_closed
        and abs(f["iris_h"] - calib["iris_h_center"]) <= tol["iris_h"]
        and abs(f["iris_v"] - calib["iris_v_center"]) <= tol["iris_v"]
        and abs(f["yaw"] - calib["yaw_center"]) <= tol["yaw"]
        and abs(f["pitch"] - calib["pitch_center"]) <= tol["pitch"]
    )
    return eyes_closed, gazing
