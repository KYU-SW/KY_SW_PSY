# 기본 응시·눈 감김 시간, EAR 임계치, 쿨다운 등 설정값

# ── 카메라 ──────────────────────────────────────────────
# DroidCam Wi-Fi 연결: 스마트폰 앱에 표시된 IP 주소를 입력
#   예) CAMERA_SOURCE = "http://192.168.0.12:4747/video"
# DroidCam Client(가상 웹캠) 또는 USB 웹캠: 장치 번호(0, 1, 2 ...)를 입력
CAMERA_SOURCE = "http://10.22.14.83:4747/video"

FRAME_WIDTH = 640           # 분석용 프레임 가로 크기 (px)
RECONNECT_DELAY_SEC = 2.0   # 영상이 끊겼을 때 재연결 대기 시간

# ── 응시 · 눈 감김 판정 ──────────────────────────────────
# 기본은 "공통 기준"으로 누구나 보정 없이 사용한다.
# 공통 기준이 잘 맞지 않는 사람만 calibrate.py --user 이름 으로 개인 보정을 하면
# 그 사람의 보정 파일 값이 아래 기본값을 덮어쓴다.
PROFILE_DIR = "profiles"
CALIBRATION_LOG = "profiles/calibration_results.csv"   # 보정할 때마다 정확도 기록


def calibration_file(user=None):
    """사용자별 보정 파일 경로. 이름이 없으면 공용 파일."""
    name = f"calibration_{user}.json" if user else "calibration.json"
    return f"{PROFILE_DIR}/{name}"


# 공통 기준: 여러 사람의 보정 데이터(profiles/samples_*.json)에서 공통으로 맞는 값
# (evaluate_universal.py로 사람별 정확도를 확인할 수 있다)
DEFAULT_CALIBRATION = {
    "ear_closed": 0.15,      # EAR이 이 값 이하면 눈 감음
    "blink_closed": 0.45,    # MediaPipe eyeBlink 점수가 이 값 이상이면 눈 감음
    "iris_h_center": 0.50,   # 카메라를 볼 때의 홍채 가로 위치 (눈꼬리 사이 0~1)
    "iris_v_center": -0.07,  # 카메라를 볼 때의 홍채 세로 위치 (눈 가로 길이 대비)
    "yaw_center": 0.0,       # 카메라를 볼 때의 고개 좌우 각도 (도)
    "pitch_center": 0.0,     # 카메라를 볼 때의 고개 상하 각도 (도)
}
# 기준값에서 이 범위 안이면 "카메라 응시"로 판정.
# 고개 상하 각도는 카메라 높이·누운 자세에 따라 크게 달라서(같은 응시인데 0° ~ -15°) 넓게 둔다.
GAZE_TOLERANCE = {
    "iris_h": 0.06,
    "iris_v": 0.05,
    "yaw": 5.0,
    "pitch": 30.0,
}
# 보정할 때 이 후보들 중에서 그 사람에게 가장 잘 맞는 허용 범위를 자동으로 고른다.
# 너무 좁으면 보정 직후에만 잘 맞고 조금만 자세가 바뀌어도 응시가 끊기므로 최솟값을 둔다.
TOLERANCE_GRID = {
    "iris": [0.04, 0.05, 0.06, 0.08],
    "head": [5.0, 6.0, 8.0, 12.0],
}
# 둘러보기 중 '응시' 오판정이 이 비율(%) 이하인 범위 중에서 가장 넓은 것을 고른다.
# 순간적인 오판정은 5초 연속 응시 조건에서 걸러지므로, 응시가 끊기지 않는 쪽을 우선한다.
MAX_AWAY_FALSE_GAZE = 10.0
SMOOTHING = 0.5

# ── 음성 안내 ────────────────────────────────────────
# 말하기 속도 (-10 느림 ~ 10 빠름). 1이면 질문이 8.3초 -> 7.7초, 알아듣기에도 무리 없음
VOICE_RATE = 1

# ── 호출 판정 (Decision Layer) ──────────────────────────
# 사용자별 응시 시간 기본값 (profiles/users.json에서 사람마다 바꿀 수 있음)
DWELL_DEFAULTS = {
    "first_gaze_sec": 3.5,     # 1차 응시: 이만큼 보면 "호출하시겠습니까?" 질문
    "confirm_gaze_sec": 3.5,   # 2차 응시: 질문 후 이만큼 보면 호출 확정
    "cancel_close_sec": 3.5,   # 눈 감기: 질문 후 이만큼 감으면 호출 취소
}
DWELL_MIN_SEC = 2.0
DWELL_MAX_SEC = 10.0
DWELL_STEP_SEC = 0.5

GRACE_SEC = 0.5              # 응시·눈 감김이 이 시간 이하로 끊기면 타이머를 이어서 센다
FACE_LOST_GRACE_SEC = 1.0    # 얼굴을 이 시간 이하로 놓치면 타이머를 멈춘 채 기다린다
RESPONSE_EXTRA_SEC = 7.0     # 질문 후 응답 대기 = 확정/취소 시간 중 긴 쪽 + 이 시간
# 쿨다운은 고정 시간이 아니라 "결과 안내 음성이 끝나고, 환자가 시선을 한 번 뗄 때까지"로 정한다.
#  - 안내가 끝나기 전에 다시 질문하면 음성이 겹치고
#  - 계속 쳐다보는 것만으로 다시 질문이 나오면 원치 않는 반복 질문이 되며
#  - 그 외의 기다림은 응급 상황에서 재호출만 늦춘다
# 재호출은 어차피 1차 응시 → 질문 → 2차 응시의 이중 확인을 다시 거치므로 중복 호출은 따로 막지 않는다.
