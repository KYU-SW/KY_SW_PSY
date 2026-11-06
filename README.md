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
* **호출 확정 / 취소**: 설정된 시간 동안 다시 응시하면 호출 확정, 설정된 시간 동안 눈을 감으면 호출하지 않고 대기 상태로 복귀하며 결과를 음성으로 안내
* **사용자별 응시 시간 설정**: 환자(침상)별 프로필에 1차 응시 · 확정 응시 · 취소 눈 감김 시간을 각각 저장 (2~10초, 0.5초 단위), 간호사·보호자가 환자 상태에 맞게 조정하며 음성 안내 문구에도 자동 반영
* **원격 알림 발송**: Telegram Bot API를 통해 간호사·의료진·보호자 스마트폰으로 호출 알림을 동시에 푸시 전송 (수신자는 Telegram 앱만 설치)
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
├── main.py                  # 전체 실행 루프
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
│   └── notifier.py          # Telegram Bot 알림 전송
│
├── docs/
│   ├── architecture.webp
│   └── usecase.png
│
├── requirements.txt
├── .env.example             # Telegram Bot 토큰 · 수신자 Chat ID
└── README.md
```
