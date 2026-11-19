# 7단계 알림 로직 테스트 (실제로 보내지 않고 가짜 전송으로 검사)
#   python test_notifier.py
from datetime import datetime, timedelta

import json
import time

import requests

import config
from output.notifier import Notifier, build_message

config.NOTIFY_RETRIES = 3


class FakeResponse:
    def __init__(self, status, desc="", message_id=None):
        self.status_code = status
        self._desc = desc
        self._message_id = message_id

    def json(self):
        out = {"ok": self.status_code == 200, "description": self._desc}
        if self._message_id is not None:
            out["result"] = {"message_id": self._message_id}
        return out


class FakePost:
    """Chat ID별로 정해 둔 응답을 차례로 돌려준다. 보낸 기록을 남긴다."""

    def __init__(self, plan=None):
        self.plan = plan or {}
        self.calls = []          # sendMessage를 받은 Chat ID
        self.sent = []           # sendMessage로 보낸 내용
        self.other = []          # (방법, 내용): 버튼 응답·알림 수정
        self.next_id = 100

    def __call__(self, url, data, timeout):
        method = url.rsplit("/", 1)[-1]
        if method != "sendMessage":
            self.other.append((method, data))
            return FakeResponse(200)
        self.calls.append(data["chat_id"])
        self.sent.append(data)
        seq = self.plan.get(data["chat_id"], [200])
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        self.next_id += 1
        return FakeResponse(item, "Bad Request: chat not found" if item == 400 else "", self.next_id)


class NoUpdates:
    """'확인' 버튼 수신을 실제 Telegram 대신 '아무 일 없음'으로 (테스트 중 인터넷 접속 안 함)."""

    def __call__(self, url, params, timeout):
        time.sleep(1)
        return self

    def json(self):
        return {"ok": True, "result": []}


def N(*args):
    return Notifier(*args, get=NoUpdates())


def press(notifier, chat_id, call_no=None, run_id=None, name="김간호"):
    """chat_id 사람이 call_no번째 알림의 '확인' 버튼을 누른 것처럼 처리한다."""
    data = f"ack:{run_id or notifier._run_id}:{call_no or notifier.last_call_no}"
    return notifier.handle_callback({"id": "cb1", "data": data, "from": {"first_name": name},
                                     "message": {"chat": {"id": int(chat_id)}}})


def check(name, cond, detail=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  ({detail})" if detail and not cond else ""))
    return bool(cond)


def send(notifier, when=None):
    notifier.notify_call(when)
    return notifier.wait_results(1, timeout=10)[0]


def main():
    results = []
    print("알림 로직 테스트\n")
    t0 = datetime(2026, 11, 12, 14, 0, 0)

    post = FakePost()
    r = send(N("TOKEN", ["111", "222"], "302호 2번", post), t0)
    results.append(check("두 수신자 모두에게 전송", r.ok and r.sent == ["111", "222"], r))

    msg = build_message("302호 2번", t0)
    results.append(check("첫 호출 문구에 침상·시각 포함", "간호 호출" in msg and "302호 2번" in msg and "14:00:00" in msg, msg))

    n = N("TOKEN", ["111"], "302호 2번", FakePost())
    send(n, t0)
    r2 = send(n, t0 + timedelta(minutes=3))
    results.append(check("5분 안에 다시 호출하면 '재호출 2회째'", r2.count == 2, r2))
    msg2 = build_message("302호 2번", t0 + timedelta(minutes=3), 2, t0)
    results.append(check("재호출 문구에 회차·경과 시간", "재호출 (2회째 · 첫 호출 3분 전)" in msg2, msg2))

    n = N("TOKEN", ["111"], "302호 2번", FakePost())
    send(n, t0)
    r3 = send(n, t0 + timedelta(minutes=6))
    results.append(check("5분이 지나서 호출하면 다시 첫 호출로", r3.count == 1, r3))

    post = FakePost({"111": [requests.ConnectionError(), 200]})
    r = send(N("TOKEN", ["111"], "x", post))
    results.append(check("연결이 한 번 끊겨도 다시 보내서 성공", r.ok and post.calls.count("111") == 2, post.calls))

    post = FakePost({"111": [400]})
    r = send(N("TOKEN", ["111", "222"], "x", post))
    results.append(check("잘못된 Chat ID는 다시 보내지 않고, 나머지는 받음",
                         r.ok and r.sent == ["222"] and post.calls.count("111") == 1, (r, post.calls)))

    post = FakePost({"111": [requests.Timeout()]})
    r = send(N("TOKEN", ["111"], "x", post))
    results.append(check("계속 실패하면 3번 시도 후 실패로 알림", not r.ok and post.calls.count("111") == 3, post.calls))

    r = send(N("", [], "x", FakePost()))
    results.append(check(".env 설정이 없으면 실패로 처리", not r.ok and r.failed, r))

    # ── 간호사 '확인' 버튼 ──
    post = FakePost()
    n = N("TOKEN", ["111", "222"], "302호 2번", post)
    send(n, t0)
    markup = json.loads(post.sent[0].get("reply_markup", "{}"))
    button = markup.get("inline_keyboard", [[{}]])[0][0]
    results.append(check("호출 알림에 '확인' 버튼이 달림", button.get("callback_data", "").startswith("ack:"), post.sent[0]))

    ack = press(n, "222")
    edits = [d for m, d in post.other if m == "editMessageText"]
    results.append(check("버튼을 누르면 확인 결과(누가·최근 호출)가 나옴",
                         ack is not None and ack.who == "김간호" and ack.latest and n.poll_acks() == [ack], ack))
    results.append(check("두 수신자의 알림 모두에 '확인' 표시, 버튼 없앰",
                         len(edits) == 2 and all("김간호님이 확인" in d["text"] and "reply_markup" not in d for d in edits), edits))

    again = press(n, "111", name="박간호")
    answers = [d["text"] for m, d in post.other if m == "answerCallbackQuery"]
    results.append(check("다른 사람이 또 누르면 '이미 확인함'으로 안내만", again is None and "이미 김간호님이 확인했습니다." in answers, answers))

    n = N("TOKEN", ["111"], "x", FakePost())
    send(n, t0)
    send(n, t0 + timedelta(minutes=1))
    old = press(n, "111", call_no=1)
    results.append(check("지난 호출의 확인은 환자에게 안내하지 않음 (latest=False)", old is not None and not old.latest, old))

    n = N("TOKEN", ["111"], "x", FakePost())
    send(n, t0)
    results.append(check("이전 실행의 버튼·모르는 대화방은 무시",
                         press(n, "111", run_id="123") is None and press(n, "999") is None and not n.poll_acks()))

    print(f"\n결과: {sum(results)}/{len(results)} 통과")


if __name__ == "__main__":
    main()
