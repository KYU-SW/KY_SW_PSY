# 시험 도구(scenario_test.py) 확인: 카메라·스피커 없이 가짜 시선으로 시험 순서를 끝까지 돌린다
#   python test_scenario.py
import os
import shutil
import tempfile
import unittest

import config
import scenario_test as st
from vision.features import EyeState


class FakeSpeaker:
    """말하는 데 0.5초 걸린다고 치고, 끝난 시각을 돌려준다."""

    def __init__(self, clock):
        self.clock, self.queue, self.said = clock, [], []

    def say_async(self, text, tag=None):
        start = max([self.clock[0]] + [end for _, end in self.queue])
        self.queue.append((tag, start + 0.5))
        self.said.append(tag)

    def interrupt(self, tag):
        pass

    def busy(self):
        return any(end > self.clock[0] for _, end in self.queue)

    def poll_finished(self):
        done = [(t, e) for t, e in self.queue if e <= self.clock[0]]
        self.queue = [(t, e) for t, e in self.queue if e > self.clock[0]]
        return done


class FakeGuide:
    def __init__(self, speaker):
        self.speaker = speaker

    def on_event(self, event):
        if event in ("ASK", "CALL", "CANCEL", "TIMEOUT"):
            self.speaker.say_async(event, event)

    def nurse_acked(self):
        self.speaker.say_async("ACK", "ACK")


def eye(gazing=False, closed=False):
    return EyeState(gazing=gazing, eyes_closed=closed, **{k: 0.0 for k in EyeState.__dataclass_fields__
                                                          if k not in ("gazing", "eyes_closed")})


class Person:
    """시험자 흉내: 지시대로 행동한다. 질문을 들으면 다시 보거나 눈을 감는다."""

    def __init__(self, runner, away_glance=0.0):
        self.runner, self.away_glance = runner, away_glance

    def eye(self, now):
        r = self.runner
        t = r.trial
        if t is None or r.phase != "run":
            return eye()
        if t.kind == "AWAY":
            # 가끔 카메라를 힐끗 본다 (away_glance초 동안)
            return eye(gazing=(now - r.t0) % 15 < self.away_glance)
        if r.controller.state == "WAITING" and t.kind == "CANCEL":
            return eye(closed=True)
        if r.controller.state == "ASKING":
            return eye()                         # 질문 듣는 동안은 가만히
        return eye(gazing=True)


def play(trials, away_glance=0.0, end=600.0):
    clock = [1000.0]
    speaker = FakeSpeaker(clock)
    runner = st.ScenarioRunner(speaker, FakeGuide(speaker), dict(config.DWELL_DEFAULTS), trials, say=lambda *_: None)
    person = Person(runner, away_glance)
    while not runner.done and clock[0] < 1000 + end:
        clock[0] += 1 / 15                       # 15fps
        runner.update(person.eye(clock[0]), clock[0])
    return runner


class ScenarioTest(unittest.TestCase):
    def test_full_run(self):
        runner = play(st.plan())
        self.assertTrue(runner.done)
        kinds = [(t.kind, t.outcome, t.ok) for t in runner.trials]
        self.assertEqual(kinds, [("CALL", "CALL", True)] * 3 + [("CANCEL", "CANCEL", True)] * 2 + [("AWAY", "OK", True)])
        for t in runner.trials[:5]:
            self.assertAlmostEqual(t.ask_sec, 3.5, delta=0.3)       # 1차 응시 3.5초
            self.assertAlmostEqual(t.answer_sec, 3.5, delta=0.3)    # 2차 응시 / 눈 감기 3.5초
        self.assertTrue(all(t.finished for t in runner.trials))

    def test_short_glances_are_not_calls(self):
        runner = play([st.Trial("AWAY", 1)], away_glance=2.0)       # 2초 힐끗은 질문이 안 나와야 한다
        t = runner.trials[0]
        self.assertEqual((t.outcome, t.false_asks, t.false_calls), ("OK", 0, 0))

    def test_long_stare_counts_as_false_ask(self):
        runner = play([st.Trial("AWAY", 1)], away_glance=5.0)       # 5초 응시는 질문이 나온다 -> 기록돼야 함
        t = runner.trials[0]
        self.assertEqual(t.outcome, "FALSE_ASK")
        self.assertGreater(t.false_asks, 0)
        self.assertFalse(t.ok)

    def test_no_face_fails_trial(self):
        clock = [1000.0]
        speaker = FakeSpeaker(clock)
        runner = st.ScenarioRunner(speaker, FakeGuide(speaker), dict(config.DWELL_DEFAULTS),
                                   [st.Trial("CALL", 1)], say=lambda *_: None)
        while not runner.done and clock[0] < 1200:
            clock[0] += 1 / 15
            runner.update(None, clock[0])                            # 얼굴이 안 잡힘
        t = runner.trials[0]
        self.assertEqual((t.outcome, t.ok), ("NONE", False))
        self.assertAlmostEqual(t.face_lost, 1.0)

    def test_save_and_report(self):
        tmp = tempfile.mkdtemp()
        old = st.RESULT_DIR, st.SUMMARY_FILE
        st.RESULT_DIR, st.SUMMARY_FILE = tmp, os.path.join(tmp, "summary.csv")
        try:
            runner = play(st.plan())
            detail, row = st.save("시험자A", "안경", runner.trials, None)
            st.save("시험자B", "", runner.trials, None)
            self.assertTrue(os.path.exists(detail))
            self.assertEqual((row["호출 성공"], row["취소 성공"], row["딴 데 보기 호출"]), ("3/3", "2/2", 0))
            st.report()
        finally:
            st.RESULT_DIR, st.SUMMARY_FILE = old
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
