# Telegram Bot 알림 전송
#
#   notifier = Notifier()            # .env에서 토큰·Chat ID·침상 이름을 읽는다
#   notifier.notify_call()           # 바로 돌아오고, 뒤에서 모든 수신자에게 보낸다
#   for result in notifier.poll_results():   # 매 프레임: 보낸 결과 확인
#       if not result.ok: ...        # 한 명도 못 받았으면 환자에게 다시 호출하라고 안내
#   for ack in notifier.poll_acks():          # 매 프레임: 간호사가 알림의 '확인' 버튼을 눌렀는가
#       if ack.latest: ...           # 환자에게 "간호사가 호출을 확인했습니다" 안내
#
# 인터넷이 느려도 영상 분석이 멈추지 않도록 전송과 '확인' 버튼 수신은 별도 스레드에서 한다.
import json
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
    load_dotenv(config.ENV_FILE, override=True)    # 설정 화면에서 바꾼 값도 반영
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


ACK_BUTTON = "✅ 확인 (지금 갑니다)"


@dataclass
class AckResult:
    call_no: int        # 몇 번째 알림에 대한 확인인지 (실행 중 1부터)
    count: int          # 그 알림이 몇 번째 호출이었는지 (재호출이면 2 이상)
    who: str            # 버튼을 누른 사람 (Telegram 이름)
    seconds: float      # 호출부터 확인까지 걸린 시간
    latest: bool        # 가장 최근 호출에 대한 확인인가 (환자에게 안내할지)


@dataclass
class SendResult:
    ok: bool                           # 한 명이라도 받았으면 True
    count: int                         # 몇 번째 호출인지 (재호출이면 2 이상)
    sent: list = field(default_factory=list)     # 받은 Chat ID
    failed: list = field(default_factory=list)   # (Chat ID, 이유)
    seconds: float = 0.0               # 호출 확정부터 전송 완료까지 걸린 시간
    retries: int = 0                   # 다시 보낸 횟수 (모든 수신자 합계)


class Notifier:
    def __init__(self, token=None, chat_ids=None, bed=None, post=requests.post, get=requests.get):
        env_token, env_ids, env_bed = load_settings()
        self.token = token if token is not None else env_token
        self.chat_ids = chat_ids if chat_ids is not None else env_ids
        self.bed = bed or env_bed
        self._post = post                  # 테스트에서 가짜 전송으로 바꿀 수 있게
        self._get = get
        self._calls = []                   # 최근 호출 시각 (재호출 판단용)
        self._todo = queue.Queue()
        self._results = queue.Queue()
        self._worker = None
        # '확인' 버튼: 이번 실행의 알림인지 구별하려고 버튼에 실행 번호를 넣는다
        self._run_id = str(int(time.time()))
        self.last_call_no = 0
        self._sent_calls = {}              # call_no -> {"when", "count", "messages": [(chat_id, message_id, text)]}
        self._acked = {}                   # call_no -> 누른 사람
        self._acks = queue.Queue()
        self._lock = threading.Lock()
        self._listener = None

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
        self.last_call_no += 1
        with self._lock:
            self._sent_calls[self.last_call_no] = {"when": time.time(), "count": count, "messages": []}
        self._start_worker()
        self._todo.put((text, count, time.time(), self.last_call_no))
        return count

    def send_text(self, text):
        """설정 확인용: 문구를 그대로 보낸다 (바로 돌아옴). '확인' 버튼은 달지 않는다."""
        self._start_worker()
        self._todo.put((text, 0, time.time(), 0))

    def _start_worker(self):
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def poll_acks(self):
        """간호사가 누른 '확인' 버튼 (AckResult 목록)."""
        out = []
        while not self._acks.empty():
            out.append(self._acks.get())
        return out

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
            text, count, queued_at, call_no = self._todo.get()
            result = SendResult(ok=False, count=count)
            if not self.configured():
                result.failed.append(("-", ".env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS가 없음"))
            for chat_id in self.chat_ids if self.configured() else []:
                reason, tries, message_id = self._send_one(chat_id, text, call_no)
                result.retries += tries - 1
                if reason is None:
                    result.sent.append(chat_id)
                    if call_no and message_id is not None:
                        with self._lock:
                            self._sent_calls[call_no]["messages"].append((chat_id, message_id, text))
                else:
                    result.failed.append((chat_id, reason))
            result.ok = bool(result.sent)
            result.seconds = time.time() - queued_at
            for chat_id, reason in result.failed:
                print(f"[알림 실패] {chat_id}: {reason}")
            if result.sent:
                extra = f", 재시도 {result.retries}번" if result.retries else ""
                print(f"[알림 전송] {len(result.sent)}명 수신 ({result.seconds:.1f}초{extra})")
                if call_no and self._listener is None:     # 첫 호출 알림을 보낸 뒤부터 '확인' 버튼을 기다린다
                    self._listener = threading.Thread(target=self._listen, daemon=True)
                    self._listener.start()
            self._results.put(result)

    def _send_one(self, chat_id, text, call_no=0):
        """(실패 이유 또는 None, 시도 횟수, 메시지 번호). 실패하면 1초, 2초 기다렸다가 다시 보낸다."""
        url = API_URL.format(token=self.token, method="sendMessage")
        data = {"chat_id": chat_id, "text": text}
        if call_no:
            data["reply_markup"] = json.dumps({"inline_keyboard": [[
                {"text": ACK_BUTTON, "callback_data": f"ack:{self._run_id}:{call_no}"}]]})
        reason = "알 수 없음"
        for attempt in range(config.NOTIFY_RETRIES):
            if attempt:
                print(f"[알림 재시도] {chat_id}: {reason}")
                time.sleep(attempt)
            try:
                r = self._post(url, data=data, timeout=config.NOTIFY_TIMEOUT_SEC)
                if r.status_code == 200:
                    try:
                        message_id = r.json().get("result", {}).get("message_id")
                    except (ValueError, AttributeError):
                        message_id = None
                    return None, attempt + 1, message_id
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
        return reason, attempt + 1, None

    # ── '확인' 버튼 수신 ─────────────────────────────────
    def _listen(self):
        """Telegram에 '버튼이 눌렸는지'를 계속 물어본다 (롱 폴링, 최대 25초씩 기다림)."""
        url = API_URL.format(token=self.token, method="getUpdates")
        offset = None
        while True:
            try:
                params = {"timeout": 25}
                if offset is not None:
                    params["offset"] = offset
                data = self._get(url, params=params, timeout=35).json()
            except (requests.RequestException, ValueError):
                time.sleep(3)
                continue
            if not data.get("ok"):
                time.sleep(5)
                continue
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    self.handle_callback(update["callback_query"])

    def handle_callback(self, cq):
        """'확인' 버튼 하나를 처리한다. 처음 누른 사람만 기록하고, 모든 수신자의 알림에 표시한다."""
        user = cq.get("from", {})
        who = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or user.get("username", "누군가")
        parts = str(cq.get("data", "")).split(":")
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
        if len(parts) != 3 or parts[0] != "ack" or chat_id not in self.chat_ids:
            self._answer(cq, "")
            return None
        if parts[1] != self._run_id:
            self._answer(cq, "이전 실행의 알림입니다.")
            return None
        call_no = int(parts[2])
        with self._lock:
            call = self._sent_calls.get(call_no)
            first = self._acked.get(call_no)
            if call and first is None:
                self._acked[call_no] = who
        if call is None:
            self._answer(cq, "")
            return None
        if first is not None:
            self._answer(cq, f"이미 {first}님이 확인했습니다.")
            return None
        seconds = time.time() - call["when"]
        self._answer(cq, "확인되었습니다. 환자에게 안내합니다.")
        mark = f"\n\n✅ {who}님이 확인 ({datetime.now().strftime('%H:%M:%S')}, {seconds:.0f}초 후)"
        for cid, mid, text in list(call["messages"]):
            # 버튼을 없애고 누가 확인했는지 적는다 (다른 수신자도 알 수 있게)
            self._api("editMessageText", {"chat_id": cid, "message_id": mid, "text": text + mark})
        ack = AckResult(call_no, call["count"], who, seconds, call_no == self.last_call_no)
        print(f"[알림 확인] {who}님이 {call['count']}회째 호출을 확인 ({seconds:.0f}초 후)")
        self._acks.put(ack)
        return ack

    def _answer(self, cq, text):
        """버튼을 누른 사람 화면에 짧은 안내를 띄운다 (버튼의 '로딩 중' 표시도 끝난다)."""
        self._api("answerCallbackQuery", {"callback_query_id": cq.get("id", ""), "text": text})

    def _api(self, method, data):
        try:
            self._post(API_URL.format(token=self.token, method=method), data=data,
                       timeout=config.NOTIFY_TIMEOUT_SEC)
        except requests.RequestException:
            pass
