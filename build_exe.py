# 실행 파일 만들기 (Windows)
#   pip install pyinstaller
#   python build_exe.py
#
# 결과: dist/OpticCall/ 폴더 -> 폴더째 복사해서 OpticCall.exe를 더블클릭하면 설정 화면이 열린다.
# 파이썬이 없는 PC에서도 실행된다. (.env, profiles/, logs/는 exe 옆에 만들어진다)
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "OpticCall")
MODEL = os.path.join("models", "face_landmarker.task")


def main():
    if not os.path.exists(os.path.join(ROOT, MODEL)):
        sys.exit(f"{MODEL}이 없습니다. MediaPipe 얼굴 모델을 먼저 받아 두세요.")
    cmd = [sys.executable, "-m", "PyInstaller", "app.py",
           "--name", "OpticCall",
           "--onedir",                    # 한 파일(onefile)보다 시작이 빠르다
           "--console",                   # 시작 점검·호출 기록을 보여 주는 창 (설정 화면에서는 숨김)
           "--noconfirm", "--clean",
           "--collect-all", "mediapipe",  # 얼굴 분석 모듈의 데이터 파일까지 포함
           "--hidden-import", "win32timezone"]
    subprocess.run(cmd, cwd=ROOT, check=True)

    # exe 옆에 둘 파일: 얼굴 모델, 설정 예시, 빈 프로필 폴더
    os.makedirs(os.path.join(DIST, "models"), exist_ok=True)
    shutil.copy2(os.path.join(ROOT, MODEL), os.path.join(DIST, MODEL))
    shutil.copy2(os.path.join(ROOT, ".env.example"), os.path.join(DIST, ".env.example"))
    os.makedirs(os.path.join(DIST, "profiles"), exist_ok=True)
    with open(os.path.join(DIST, "사용 방법.txt"), "w", encoding="utf-8") as f:
        f.write("OpticCall 사용 방법\n\n"
                "1. OpticCall.exe를 더블클릭하면 설정 화면이 열립니다.\n"
                "2. 카메라 주소(DroidCam 앱에 보이는 IP)를 넣고 [연결 확인]을 누릅니다.\n"
                "3. 침상 이름, 봇 토큰을 넣고, 알림 받을 사람이 봇에서 '시작'을 누른 뒤 [Chat ID 찾기]로 고릅니다.\n"
                "4. [테스트 알림 보내기]로 알림이 오는지 확인합니다.\n"
                "5. 필요하면 환자 이름을 넣고 응시 시간을 바꾼 뒤 [저장하고 시작]을 누릅니다.\n\n"
                "종료: 영상 창에서 q 또는 ESC\n"
                "호출 기록: logs/call_history.csv\n")
    print(f"\n완료: {DIST}\\OpticCall.exe")


if __name__ == "__main__":
    main()
