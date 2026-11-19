# 실행 파일(OpticCall.exe)의 시작점
#   OpticCall.exe            -> 설정 화면 ([저장하고 시작]을 누르면 아래처럼 새 창에서 실행)
#   OpticCall.exe --run ...  -> 호출 시스템 실행 (main.py와 같은 옵션: --user, --camera, --no-window ...)
#
# 실행 파일 만들기: python build_exe.py
import sys


def entry():
    # 출력을 파일 등으로 돌렸을 때 ✅ 같은 글자 때문에 멈추지 않게 (검은 창에서는 원래 잘 나온다)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
    if "--run" in sys.argv:
        sys.argv.remove("--run")
        import main
        main.main()
    else:
        import settings_app
        settings_app.main()


if __name__ == "__main__":
    entry()
