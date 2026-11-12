# 7단계 알림 로직 테스트 (실제로 보내지 않고 가짜 전송으로 검사)
#   python test_notifier.py
from datetime import datetime, timedelta

import requests

import config
from output.notifier import Notifier, build_message

config.NOTIFY_RETRIES = 3


class FakeResponse:
    def __init__(self, status, desc=""):
        self.status_code = status
        self._desc = desc

    def json(self):
        return {"ok": self.status_code == 200, "description": self._desc}


class FakePost:
    """Chat ID별로 정해 둔 응답을 차례로 돌려준다. 보낸 기록을 남긴다."""

    def __init__(self, plan=None):
        self.plan = plan or {}
        self.calls = []

    def __call__(self, url, data, timeout):
        self.calls.append(data["chat_id"])
        seq = self.plan.get(data["chat_id"], [200])
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item, "Bad Request: chat not found" if item == 400 else "")


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
    r = send(Notifier("TOKEN", ["111", "222"], "302호 2번", post), t0)
    results.append(check("두 수신자 모두에게 전송", r.ok and r.sent == ["111", "222"], r))

    msg = build_message("302호 2번", t0)
    results.append(check("첫 호출 문구에 침상·시각 포함", "간호 호출" in msg and "302호 2번" in msg and "14:00:00" in msg, msg))

    n = Notifier("TOKEN", ["111"], "302호 2번", FakePost())
    send(n, t0)
    r2 = send(n, t0 + timedelta(minutes=3))
    results.append(check("5분 안에 다시 호출하면 '재호출 2회째'", r2.count == 2, r2))
    msg2 = build_message("302호 2번", t0 + timedelta(minutes=3), 2, t0)
    results.append(check("재호출 문구에 회차·경과 시간", "재호출 (2회째 · 첫 호출 3분 전)" in msg2, msg2))

    n = Notifier("TOKEN", ["111"], "302호 2번", FakePost())
    send(n, t0)
    r3 = send(n, t0 + timedelta(minutes=6))
    results.append(check("5분이 지나서 호출하면 다시 첫 호출로", r3.count == 1, r3))

    post = FakePost({"111": [requests.ConnectionError(), 200]})
    r = send(Notifier("TOKEN", ["111"], "x", post))
    results.append(check("연결이 한 번 끊겨도 다시 보내서 성공", r.ok and post.calls.count("111") == 2, post.calls))

    post = FakePost({"111": [400]})
    r = send(Notifier("TOKEN", ["111", "222"], "x", post))
    results.append(check("잘못된 Chat ID는 다시 보내지 않고, 나머지는 받음",
                         r.ok and r.sent == ["222"] and post.calls.count("111") == 1, (r, post.calls)))

    post = FakePost({"111": [requests.Timeout()]})
    r = send(Notifier("TOKEN", ["111"], "x", post))
    results.append(check("계속 실패하면 3번 시도 후 실패로 알림", not r.ok and post.calls.count("111") == 3, post.calls))

    r = send(Notifier("", [], "x", FakePost()))
    results.append(check(".env 설정이 없으면 실패로 처리", not r.ok and r.failed, r))

    print(f"\n결과: {sum(results)}/{len(results)} 통과")


if __name__ == "__main__":
    main()
