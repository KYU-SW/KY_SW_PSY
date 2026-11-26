# OpticCall :eyes:
비접촉식 시선 추적 간호 호출 시스템  
#  프로젝트 소개
**OpticCall**은 수술 직후 거동이 불편한 환자 및 운동 장애 환자가 손이나 몸을 움직이지 않고도 의료진을 호출할 수 있도록 기획된 비접촉식 시선 추적 기반 호출 시스템  
환자의 실시간 시선과 눈 깜빡임 패턴을 감지하여, 신체 움직임 없이도 즉각적으로 간호사·의료진·보호자를 호출할 수 있다.
# 프로젝트 목표
* **비접촉식 호출 환경 제공**: 호출 버튼을 누르기 어려운 환자도 카메라를 응시하는 것만으로 의료진을 호출할 수 있도록 한다.
* **저비용 시스템 구축**: 별도의 웹캠이나 전용 장비 없이 스마트폰 카메라(DroidCam)와 일반 PC만으로 동작하며, 별도 모델 학습 없이 실시간 분석이 가능하도록 한다.
* **오호출 방지**: 1차 응시 → 음성 확인 질문 → 2차 응시로 이어지는 이중 확인 절차와 쿨다운 타이머를 통해 무의식적인 시선 이동이나 중복 호출을 차단한다.
* **신속한 원격 알림**: 호출 확정 즉시 간호사·의료진·보호자의 스마트폰으로 알림을 동시에 전송하여 대응 시간을 단축한다.
* **사용자 맞춤 설정**: 환자의 상태와 시선 유지 능력에 따라 응시·눈 감김 시간을 개별 설정하여, 누구나 부담 없이 사용할 수 있도록 한다.
# 세부 기능
* **카메라 스트리밍 연동**: 침상에 거치한 스마트폰 카메라 영상을 DroidCam을 통해 Wi-Fi / USB로 PC에 실시간 전송하고, OpenCV로 프레임 단위 수신
* **안면 및 시선·깜빡임 추적**: MediaPipe Face Landmarker로 478개 안면 랜드마크를 추출하여 홍채 위치·고개 각도 기반 카메라 응시 여부와 EAR(Eye Aspect Ratio) 기반 눈 감김 여부 판정 (공통 기준으로 누구나 보정 없이 사용, 필요 시 개인 보정 가능)
* **1차 응시 감지**: 환자가 카메라를 설정된 시간(기본 3.5초) 동안 응시하면 Dwell Time 타이머가 누적되어 호출 확인 단계로 진입
* **음성 확인 질문**: Windows 음성 엔진(SAPI)으로 병실 스피커를 통해 "호출하시겠습니까?" 및 "호출을 원하시면 다시 N초간 카메라를 응시하시고, 원하지 않으시면 눈을 N초간 감아주세요"를 음성 안내 (N은 사용자별 설정값, 화면을 볼 수 없는 환자를 고려)
* **호출 확정 / 취소**: 설정된 시간 동안 다시 응시하면 호출 확정, 설정된 시간 동안 눈을 감으면 호출하지 않고 대기 상태로 복귀하며 결과를 음성으로 안내 (눈 감기는 질문 음성 도중에도 인정하여, 다 채우면 질문을 끊고 바로 취소)
* **사용자별 응시 시간 설정**: 환자(침상)별 프로필에 1차 응시 · 확정 응시 · 취소 눈 감김 시간을 각각 저장 (2~10초, 0.5초 단위), 간호사·보호자가 환자 상태에 맞게 조정하며 음성 안내 문구에도 자동 반영
* **원격 알림 발송**: Telegram Bot API를 통해 간호사·의료진·보호자 스마트폰으로 호출 알림을 동시에 푸시 전송 (수신자는 Telegram 앱만 설치). 5분 안에 다시 호출하면 '재호출 (N회째)'로 표시하고, 전송에 실패하면 환자에게 다시 호출하라고 음성으로 안내
* **간호사 응답 확인**: 알림의 '✅ 확인 (지금 갑니다)' 버튼을 누르면 환자에게 "간호사가 호출을 확인했습니다. 곧 도착합니다."라고 음성으로 알려 주고, 모든 수신자의 알림에 누가 몇 초 만에 확인했는지 표시 (처음 누른 사람만 기록)
* **설정 화면**: 카메라 주소·침상 이름·알림 받을 사람·환자별 응시 시간을 창에서 바꾸고 [저장하고 시작]으로 실행 (카메라 연결 확인, Chat ID 찾기, 테스트 알림 버튼 포함)
* **실행 파일**: 파이썬이 없는 PC에서도 `OpticCall.exe` 더블클릭으로 실행
* **오호출 방지 쿨다운**: 고정 대기 시간 대신 "결과 안내 음성이 끝나고 환자가 시선을 한 번 뗄 때까지"만 다음 질문을 막아, 음성 겹침·반복 질문은 막으면서 응급 시 재호출은 지연시키지 않음
  
# 시스템 아키텍처
<img width="996" height="712" alt="OpticCall 시스템 아키텍처" src="https://github.com/user-attachments/assets/2082d37a-7b7a-485e-b734-260a4220a776" />

| 계층 | 구성 | 역할 |
| --- | --- | --- |
| **Input Layer** | 스마트폰 카메라 → DroidCam Client → OpenCV | 환자 얼굴 영상 수집 및 프레임 수신 |
| **Vision Layer** | 프레임 전처리 → MediaPipe Face Landmarker → 특징값 계산 | 카메라 응시 여부 · 눈 감김 여부 판정 |
| **Decision Layer** | 1차 응시 감지 → 호출 확인 질문 → 호출 확정 / 취소 | 호출 이벤트 생성 및 제어 |
| **Output Layer** | Windows SAPI 음성 안내 · Telegram Bot API 원격 알림 | 환자 안내 및 의료진·보호자 알림 |

# Use Case Diagram
<img width="1408" height="958" alt="OpticCall Use Case Diagram" src="https://github.com/user-attachments/assets/73ea2963-564f-4f09-9ce5-d76b900fde04" />

# 기술 스택 및 개발 환경
* **개발 언어:** Python

* **개발 환경:** Visual Studio Code

* **영상 입력:** DroidCam (스마트폰 앱 + PC 클라이언트), OpenCV

* **비전 분석:** MediaPipe Face Landmarker

* **음성 안내:** Windows SAPI (pywin32, 오프라인 TTS)

* **원격 알림:** Telegram Bot API

* **버전 관리:** GitHub

# 프로젝트 구조
```text
OpticCall/
├── main.py                  # 전체 실행 (시작 점검 · 호출 판정 · 음성 · 알림 · 호출 기록)
├── settings_app.py          # 설정 화면 (카메라 · 알림 · 환자별 응시 시간)
├── app.py                   # 실행 파일 시작점 (설정 화면 / --run 실행)
├── build_exe.py             # 실행 파일 만들기 (PyInstaller)
├── config.py                # 기본 응시·눈 감김 시간, EAR 임계치, 쿨다운 등 설정값
│
├── profiles/
│   ├── profile_manager.py   # 사용자별 설정 불러오기 · 저장 · 범위 검증
│   └── users.json           # 환자(침상)별 응시 · 눈 감김 시간
│
├── input/
│   └── camera_stream.py     # DroidCam 영상 수신 (OpenCV)
│
├── vision/
│   ├── face_landmarker.py   # MediaPipe 안면 랜드마크 추출
│   └── features.py          # 카메라 응시 여부 · EAR 계산
│
├── decision/
│   └── call_controller.py   # 1차 응시 → 확인 질문 → 확정/취소, 쿨다운
│
├── output/
│   ├── tts.py               # Windows SAPI 음성 안내
│   ├── voice_guide.py       # 호출 단계별 안내 문구 · 음성 종료 시점 전달
│   └── notifier.py          # Telegram Bot 알림 전송 · '확인' 버튼 수신
│
├── docs/
│   ├── architecture.webp
│   └── usecase.png
│
├── telegram_setup.py        # 알림 수신자 Chat ID 확인 · 테스트 알림 전송
├── scenario_test.py         # 시험 도구: 호출 · 취소 · 딴 데 보기(오호출) 시험과 결과표
├── webapp/                  # 휴대폰 앱 (웹앱, 홈 화면에 설치)
│   ├── patient/             # 환자 앱: 홈 · 시선 추적 · 눈 맞추기 · 설정
│   ├── nurse/               # 의료진 앱: 침상 상태 · 호출 알람 · 확인 보내기 · 오늘 기록
│   ├── core/                # 판정 로직 (파이썬 features · call_controller를 옮김), 음성, 카메라
│   └── test/                # 판정 로직 확인 페이지 (파이썬 테스트와 같은 경우 포함)
├── requirements.txt
├── .env.example             # 카메라 IP · Telegram Bot 토큰 · 수신자 Chat ID · 침상 이름
└── README.md
```

# 실행 방법
**1. 설치** (Windows, Python 3.13)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
`models/face_landmarker.task`(MediaPipe 얼굴 모델)가 있어야 한다.

**2. 설정 파일 만들기** — `.env.example`을 복사해 `.env`로 이름을 바꾸고 값을 채운다. (`.env`는 GitHub에 올라가지 않는다)

| 항목 | 내용 |
| --- | --- |
| `CAMERA_SOURCE` | DroidCam 앱에 보이는 IP (예: `10.22.9.230`), USB·웹캠이면 장치 번호 (예: `1`) |
| `TELEGRAM_BOT_TOKEN` | BotFather에게 받은 봇 토큰 |
| `TELEGRAM_CHAT_IDS` | 알림 받을 사람의 Chat ID (쉼표로 여러 명), `python telegram_setup.py`로 확인 |
| `BED_LABEL` | 알림에 표시할 침상 이름 |

알림 받을 사람은 Telegram에서 봇을 찾아 **시작**을 누른 뒤, `python telegram_setup.py --test`로 테스트 알림을 받아 본다.

설정 화면을 쓰면 `.env`를 직접 고치지 않아도 된다: `python settings_app.py` → 값 입력 → **[저장하고 시작]**

**3. 실행**
```bash
python main.py
```
시작할 때 카메라 · 사용자 응시 시간 · 텔레그램 알림을 점검하고, "옵틱콜을 시작합니다" 음성이 나오면 사용할 수 있다. 종료는 영상 창에서 `q` 또는 `ESC`.

| 옵션 | 내용 |
| --- | --- |
| `--user 이름` | 그 사람의 응시 시간(`profiles/users.json`)·개인 보정값 사용 (없으면 공통 기준) |
| `--camera IP` | 이번 실행만 다른 카메라 사용 |
| `--no-window` | 영상 창 없이 실행 (종료: Ctrl+C) |
| `--no-notify` | 텔레그램 알림 없이 실행 (연습·시연용) |

사용자별 응시 시간 설정: `python -m profiles.profile_manager --user 이름 --set first_gaze_sec=3`

호출 기록은 `logs/call_history.csv`에 쌓인다 (질문 · 호출 · 취소 · 알림 전송 결과와 걸린 시간).

**시험하기** (한 사람당 약 5분)
```bash
python scenario_test.py --name 시험자A --note 안경
```
음성 안내에 따라 호출 3번(보고 → 질문 → 다시 보기), 취소 2번(보고 → 질문 → 눈 감기), 60초 딴 데 보기(질문·호출이 없어야 성공)를 차례로 한다.
`--notify`를 붙이면 실제 Telegram 알림('[시험]' 표시)과 '확인' 버튼까지 시간을 잰다. 결과는 `results/`에 저장되고(GitHub에는 올리지 않음), 전체 결과표는 `python scenario_test.py --report`.

**휴대폰 앱 (환자)**
휴대폰을 침대 옆쪽 위(얼굴 정면에서 30° 정도, 40~60cm)에 두고, 환자는 고개를 돌리지 않고 눈만 돌려 화면 위 눈 모양을 바라본다.
평소 천장을 볼 때는 반응하지 않는다. 노트북에서 시험할 때:
```bash
python -m http.server 8765 --directory webapp
```
Chrome에서 `http://localhost:8765/patient/` → [눈 맞추기] → [호출 대기 시작]. 판정 로직 확인: `http://localhost:8765/test/`
의료진 앱은 `http://localhost:8765/nurse/` (지금은 같은 브라우저의 탭끼리 연결된다. 휴대폰 두 대 연결은 준비 중).
환자 앱 설정에서 환자별 응시 시간과 호출 후 쉬는 시간(기본 30초)을 바꿀 수 있다.

휴대폰에서는 카메라 때문에 `https://` 주소가 필요하다. GitHub Pages(ready 브랜치)를 켜면:
`https://kyu-sw.github.io/KY_SW_PSY/webapp/patient/`, `https://kyu-sw.github.io/KY_SW_PSY/webapp/nurse/`

**실행 파일(.exe) 만들기**
```bash
pip install pyinstaller
python build_exe.py
```
`dist/OpticCall/` 폴더를 통째로 복사하면 파이썬이 없는 PC에서도 `OpticCall.exe`를 더블클릭해 설정 화면 → 실행할 수 있다. (`.env`, `profiles/`, `logs/`는 exe 옆에 만들어진다)

**사용 환경 권장**: 카메라를 환자 눈높이, 40~60cm 거리에 둔다. 모자·붕대가 눈썹을 가리지 않게 하고, 스피커 소리를 켜 둔다.

