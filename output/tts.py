# 음성 안내 (Windows 기본 음성 엔진 SAPI 사용)
# pyttsx3는 Windows에서 두 번째 문장부터 소리가 나지 않는 문제가 있어
# 같은 엔진(SAPI)을 win32com으로 직접 호출한다.
#
# 두 가지 방식으로 말할 수 있다.
#   say(text)            : 다 읽을 때까지 기다린다 (보정처럼 안내를 순서대로 할 때)
#   say_async(text, tag) : 바로 돌아오고, 뒤에서 읽는다 (영상 분석을 멈추면 안 될 때)
#                          다 읽고 나면 poll_finished()가 (tag, 끝난 시각)을 돌려준다
#   interrupt(tag)       : 지금 그 tag 문장을 읽는 중이면 그 자리에서 끊는다
import queue
import threading
import time

import pythoncom
import win32com.client

import config

SVSF_ASYNC = 1    # 바로 돌아오기
SVSF_PURGE = 2    # 읽던 것 버리기


def _make_voice(rate):
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Rate = rate                     # -10(느림) ~ 10(빠름)
    korean = voice.GetVoices("Language=412")   # 412 = 한국어
    if korean.Count > 0:
        voice.Voice = korean.Item(0)
    return voice


class Speaker:
    def __init__(self, rate=None):
        self.rate = config.VOICE_RATE if rate is None else rate
        self._voice = None                # say()용 (부른 스레드에서 만든다)
        self._todo = queue.Queue()        # say_async로 들어온 (text, tag)
        self._done = queue.Queue()        # 다 읽은 (tag, 끝난 시각)
        self._pending = 0                 # 아직 다 읽지 않은 문장 수
        self._lock = threading.Lock()
        self._worker = None
        self._current = None              # 지금 읽고 있는 문장의 tag
        self._queued = []                 # 읽을 차례를 기다리는 tag들
        self._stop_tag = None             # 끊어 달라고 한 tag

    # ── 기다리는 방식 ────────────────────────────────────
    def say(self, text):
        print(f"[음성] {text}")
        if self._voice is None:
            self._voice = _make_voice(self.rate)
        self._voice.Speak(text)           # 다 읽을 때까지 기다림

    # ── 뒤에서 읽는 방식 ─────────────────────────────────
    def say_async(self, text, tag=None):
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        print(f"[음성] {text}")
        with self._lock:
            self._pending += 1            # 넣는 순간부터 '말하는 중'
            self._queued.append(tag)
        self._todo.put((text, tag))

    def busy(self):
        """아직 읽을 문장이 남았거나 읽는 중이면 True."""
        with self._lock:
            return self._pending > 0

    def interrupt(self, tag):
        """tag 문장을 읽는 중(또는 읽을 차례)이면 끊는다. 다음 문장은 그대로 읽는다."""
        with self._lock:
            if tag == self._current or tag in self._queued:
                self._stop_tag = tag      # 이미 다 읽었으면 아무것도 하지 않는다

    def poll_finished(self):
        """지난번 이후로 다 읽은 문장들의 (tag, 끝난 시각) 목록."""
        out = []
        while not self._done.empty():
            out.append(self._done.get())
        return out

    def wait_idle(self, timeout=30.0):
        end = time.time() + timeout
        while self.busy() and time.time() < end:
            time.sleep(0.05)

    def _run(self):
        # COM 객체는 만든 스레드에서만 써야 하므로 이 스레드에서 따로 만든다
        pythoncom.CoInitialize()
        voice = _make_voice(self.rate)
        while True:
            text, tag = self._todo.get()
            with self._lock:
                self._queued.remove(tag)
                self._current = tag
            try:
                if not self._should_stop(tag):
                    voice.Speak(text, SVSF_ASYNC)
                    # 조금씩 기다리면서, 끊어 달라는 요청이 오면 바로 멈춘다
                    while not voice.WaitUntilDone(50):
                        if self._should_stop(tag):
                            voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                            print(f"[음성 끊음] {tag}")
                            break
            except Exception as e:        # 음성이 실패해도 프로그램은 계속
                print(f"[음성 오류] {e}")
            self._done.put((tag, time.time()))
            with self._lock:
                self._pending -= 1
                self._current = None
                if self._stop_tag == tag:
                    self._stop_tag = None

    def _should_stop(self, tag):
        with self._lock:
            return tag is not None and self._stop_tag == tag
