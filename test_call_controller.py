# 5단계 호출 판정 로직 시나리오 테스트 (카메라 없이 가짜 눈 상태로 검사)
#   python test_call_controller.py
from types import SimpleNamespace

from decision.call_controller import ASKING, COOLDOWN, IDLE, WAITING, CallController

FPS = 30
GAZE = SimpleNamespace(gazing=True, eyes_closed=False)
AWAY = SimpleNamespace(gazing=False, eyes_closed=False)
CLOSED = SimpleNamespace(gazing=False, eyes_closed=True)
NO_FACE = None


class Sim:
    """가짜 시계로 프레임을 흘려보내며 이벤트를 모은다."""

    def __init__(self, dwell=None):
        self.c = CallController(dwell)
        self.t = 0.0
        self.events = []

    def run(self, eye, seconds):
        for _ in range(round(seconds * FPS)):
            self.t += 1 / FPS
            for e in self.c.update(eye, self.t):
                self.events.append((e, round(self.t, 2)))
        return self

    def answer_ready(self):
        """질문 음성이 끝났다고 알린다."""
        self.c.question_finished(self.t)
        return self

    def announced(self):
        """결과 안내 음성이 끝났다고 알린다."""
        self.c.announcement_finished(self.t)
        return self

    def names(self):
        return [e for e, _ in self.events]


def check(name, cond, detail=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  ({detail})" if detail and not cond else ""))
    return cond


def main():
    results = []
    print("호출 판정 시나리오 테스트 (응시 시간 3.5초 기준)\n")

    s = Sim().run(GAZE, 3.6)
    results.append(check("3.5초 응시하면 질문", s.names() == ["ASK"] and s.c.state == ASKING, s.events))

    s = Sim().run(GAZE, 3.0)
    results.append(check("3초만 응시하면 질문 안 함", s.names() == [], s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(GAZE, 3.6)
    results.append(check("질문 후 3.5초 응시하면 호출", s.names() == ["ASK", "CALL"], s.events))

    s = Sim().run(GAZE, 3.6).run(GAZE, 5).answer_ready()
    results.append(check("질문 음성이 나오는 동안의 응시는 확정으로 치지 않음",
                         s.names() == ["ASK"] and s.c.state == WAITING, s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(CLOSED, 3.6)
    results.append(check("질문 후 3.5초 눈 감으면 취소", s.names() == ["ASK", "CANCEL"], s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(AWAY, 11)
    results.append(check("질문 후 응답이 없으면 시간 초과 (10.5초)", s.names() == ["ASK", "TIMEOUT"], s.events))

    s = Sim()
    for _ in range(6):                      # 0.7초 응시 + 0.3초 끊김 반복
        s.run(GAZE, 0.7).run(AWAY, 0.3)
    results.append(check("0.3초 끊김은 봐주고 이어서 셈", "ASK" in s.names(), s.events))

    s = Sim().run(GAZE, 2).run(AWAY, 1).run(GAZE, 2)
    results.append(check("1초 이상 다른 곳을 보면 처음부터 다시 셈", s.names() == [], s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(GAZE, 1.5).run(CLOSED, 0.2).run(GAZE, 2)
    results.append(check("확정 응시 중 깜빡임(0.2초)은 무시", s.names() == ["ASK", "CALL"], s.events))

    s = Sim().run(GAZE, 2).run(NO_FACE, 0.8).run(GAZE, 1.6)
    results.append(check("얼굴을 0.8초 놓쳐도 이어서 셈", "ASK" in s.names(), s.events))

    s = Sim().run(GAZE, 2).run(NO_FACE, 1.5).run(GAZE, 2)
    results.append(check("얼굴을 1.5초 놓치면 처음부터 다시 셈", s.names() == [], s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(GAZE, 3.6).run(AWAY, 2).run(GAZE, 5)
    results.append(check("결과 안내가 끝나기 전에는 다시 질문 안 함", s.names() == ["ASK", "CALL"], s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(GAZE, 3.6).announced().run(GAZE, 30)
    results.append(check("안내 후에도 계속 쳐다보기만 하면 다시 질문 안 함", s.names() == ["ASK", "CALL"]
                         and s.c.state == COOLDOWN, s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(GAZE, 3.6).announced().run(AWAY, 0.6)
    call_time = s.t
    s.run(GAZE, 3.6)
    ask_after = s.events[-1][1] - call_time if s.events else 0
    results.append(check(f"안내 후 시선을 뗐다가 다시 보면 바로 재호출 질문 (시선 뗀 뒤 {ask_after:.1f}초)",
                         s.names() == ["ASK", "CALL", "READY", "ASK"], s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(CLOSED, 3.6).announced().run(CLOSED, 0.1)
    results.append(check("취소 안내가 끝나면 바로 대기로 복귀", s.names() == ["ASK", "CANCEL", "READY"]
                         and s.c.state == IDLE, s.events))

    s = Sim().run(GAZE, 3.6).answer_ready().run(GAZE, 3.6).announced().run(NO_FACE, 1.5)
    results.append(check("안내 후 얼굴이 안 보여도 대기로 복귀", s.names()[-1] == "READY", s.events))

    s = Sim({"first_gaze_sec": 2.0}).run(GAZE, 2.1)
    results.append(check("사용자 설정 2초면 2초 응시로 질문", s.names() == ["ASK"], s.events))

    s = Sim().run(CLOSED, 10)
    results.append(check("대기 중 눈을 오래 감아도 아무 일 없음", s.names() == [] and s.c.state == IDLE, s.events))

    print(f"\n결과: {sum(results)}/{len(results)} 통과")


if __name__ == "__main__":
    main()
