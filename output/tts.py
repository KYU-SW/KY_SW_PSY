# 음성 안내 (Windows 기본 음성 엔진 SAPI 사용)
# pyttsx3는 Windows에서 두 번째 문장부터 소리가 나지 않는 문제가 있어
# 같은 엔진(SAPI)을 win32com으로 직접 호출한다. pywin32는 pyttsx3와 함께 설치된다.
import win32com.client


class Speaker:
    """한국어 음성으로 안내 문구를 읽는다. (말이 끝날 때까지 기다리는 방식)"""

    def __init__(self, rate=0):
        self._voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._voice.Rate = rate          # -10(느림) ~ 10(빠름)
        korean = self._voice.GetVoices("Language=412")   # 412 = 한국어
        if korean.Count > 0:
            self._voice.Voice = korean.Item(0)

    def say(self, text):
        print(f"[음성] {text}")
        self._voice.Speak(text)          # 기본값: 다 읽을 때까지 기다림
