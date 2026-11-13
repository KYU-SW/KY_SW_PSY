# Telegram Bot 알림 전송
#
#   notifier = Notifier()            # .env에서 토큰·Chat ID·침상 이름을 읽는다
#   notifier.notify_call()           # 바로 돌아오고, 뒤에서 모든 수신자에게 보낸다
#   for result in notifier.poll_results():   # 매 프레임: 보낸 결과 확인
#       if not result.ok: ...        # 한 명도 못 받았으면 환자에게 다시 호출하라고 안내
#
# 인터넷이 느려도 영상 분석이 멈추지 않도록 전송은 별도 스레드에서 한다.
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import requests
from dotenv import load_dotenv

import config

API_URL = "https://api.telegram.org/bot{token}/{method}"


def load_settings():
    """(.env) 토큰, Chat ID 목록, 침상 이름"""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = [c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    bed = os.getenv("BED_LABEL", "").strip() or "침상 미지정"
    return token, chat_ids, bed


def build_message(bed, when, count=1, first_when=None):
    """알림 문구. count가 2 이상이면 재호출."""
    clock = when.strftime("%H:%M:%S")
    if count <= 1:
        head = "🚨 간호 호출"
    else:
        ago = int((when - first_when).total_seconds() // 60) if first_when else 0
        head = f"🚨🚨 재호출 ({count}회째 · 첫 호출 {ago}분 전)" if ago else f"🚨🚨 재호출 ({count}회째)"
    return (f"{head}\n"
            f"침상: {bed}\n"
            f"시각: {clock}\n"
            f"환자가 시선으로 호출을 확정했습니다.")


@dataclass
class SendResult:
    ok: bool                           # 한 명이라도 받았으면 True
    count: int                         # 몇 번째 호출인지 (재호출이면 2 이상)
    sent: list = field(default_factory=list)     # 받은 Chat ID
    failed: list = field(default_factory=list)   # (Chat ID, 이유)
    seconds: float = 0.0               # 호출 확정부터 전송 완료까지 걸린 시간
    retries: int = 0                   # 다시 보낸 횟수 (모든 수신자 합계)


class Notifier:
    def __init__(self, token=None, chat_ids=None, bed=None, post=requests.post):
        env_token, env_ids, env_bed = load_settings()
        self.token = token if token is not None else env_token
        self.chat_ids = chat_ids if chat_ids is not None else env_ids
        self.bed = bed or env_bed
        self._post = post                  # 테스트에서 가짜 전송으로 바꿀 수 있게
        self._calls = []                   # 최근 호출 시각 (재호출 판단용)
        self._todo = queue.Queue()
        self._results = queue.Queue()
        self._worker = None

    def configured(self):
        return bool(self.token and self.chat_ids)

    def check(self):
        """시작할 때 확인: (True, 봇 이름) 또는 (False, 이유). 메시지는 보내지 않는다."""
        if not self.configured():
            return False, ".env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS가 없습니다"
        try:
            r = requests.get(API_URL.format(token=self.token, method="getMe"),
                             timeout=config.NOTIFY_TIMEOUT_SEC).json()
        except (requests.RequestException, ValueError) as e:
            return False, f"텔레그램 서버에 연결할 수 없습니다 ({type(e).__name__})"
        if not r.get("ok"):
            return False, f"봇 토큰이 올바르지 않습니다 ({r.get('description', '')})"
        return True, "@" + r["result"]["username"]

    def notify_call(self, when=None):
        """호출 알림을 보낸다 (바로 돌아옴). 몇 번째 호출인지 돌려준다."""
        when = when or datetime.now()
        # 재호출 구간 안의 호출만 남긴다
        self._calls = [t for t in self._calls
                       if (when - t).total_seconds() <= config.RECALL_WINDOW_SEC]
        self._calls.append(when)
        count = len(self._calls)
        text = build_message(self.bed, when, count, self._calls[0])
        print("[알림] " + text.replace("\n", " / "))
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        self._todo.put((text, count, time.time()))
        return count

    def send_text(self, text):
        """설정 확인용: 문구를 그대로 보낸다 (바로 돌아옴)."""
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        self._todo.put((text, 0, time.time()))

    def poll_results(self):
        out = []
        while not self._results.empty():
            out.append(self._results.get())
        return out

    def wait_results(self, n=1, timeout=30.0):
        out, end = [], time.time() + timeout
        while len(out) < n and time.time() < end:
            out += self.poll_results()
            time.sleep(0.05)
        return out

    def _run(self):
        while True:
            text, count, queued_at = self._todo.get()
            result = SendResult(ok=False, count=count)
            if not self.configured():
                result.failed.append(("-", ".env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS가 없음"))
            for chat_id in self.chat_ids if self.configured() else []:
                reason, tries = self._send_one(chat_id, text)
                result.retries += tries - 1
                if reason is None:
                    result.sent.append(chat_id)
                else:
                    result.failed.append((chat_id, reason))
            result.ok = bool(result.sent)
            result.seconds = time.time() - queued_at
            for chat_id, reason in result.failed:
                print(f"[알림 실패] {chat_id}: {reason}")
            if result.sent:
                extra = f", 재시도 {result.retries}번" if result.retries else ""
                print(f"[알림 전송] {len(result.sent)}명 수신 ({result.seconds:.1f}초{extra})")
            self._results.put(result)

    def _send_one(self, chat_id, text):
        """(실패 이유 또는 None, 시도 횟수). 실패하면 1초, 2초 기다렸다가 다시 보낸다."""
        url = API_URL.format(token=self.token, method="sendMessage")
        reason = "알 수 없음"
        for attempt in range(config.NOTIFY_RETRIES):
            if attempt:
                print(f"[알림 재시도] {chat_id}: {reason}")
                time.sleep(attempt)
            try:
                r = self._post(url, data={"chat_id": chat_id, "text": text},
                               timeout=config.NOTIFY_TIMEOUT_SEC)
                if r.status_code == 200:
                    return None, attempt + 1
                desc = ""
                try:
                    desc = r.json().get("description", "")
                except ValueError:
                    pass
                reason = f"HTTP {r.status_code} {desc}".strip()
                if r.status_code in (400, 401, 403, 404):   # 토큰·Chat ID 문제는 다시 보내도 같음
                    break
            except requests.RequestException as e:
                reason = f"연결 실패 ({type(e).__name__})"
        return reason, attempt + 1
