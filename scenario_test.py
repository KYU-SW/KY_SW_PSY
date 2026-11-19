# 시험 단계: 정해진 순서로 호출 · 취소 · 오호출을 시험하고 결과를 기록한다
#   python scenario_test.py --name 시험자A                 -> 공통 기준, 알림 없이 (약 4분)
#   python scenario_test.py --name 시험자A --note 안경     -> 시험 조건을 함께 기록 (안경, 누운 자세, 어두운 조명 등)
#   python scenario_test.py --name 시험자A --notify        -> 실제 Telegram 알림까지 ('[시험]' 표시, 확인 버튼 시간도 기록)
#   python scenario_test.py --report                       -> 지금까지 시험한 사람 전체 결과표
#
# 시험 순서 (음성으로 안내한다)
#   1. 호출 3번  : 카메라를 보고, 질문이 나오면 다시 카메라를 본다      -> CALL이 나와야 성공
#   2. 취소 2번  : 카메라를 보고, 질문이 나오면 눈을 감는다            -> CANCEL이 나와야 성공
#   3. 딴 데 보기 : 60초 동안 카메라를 보지 않고 편하게 주변을 본다     -> 질문·호출이 없어야 성공
#
# 결과: results/시험자_날짜시각.csv (시도별), results/summary.csv (사람별 요약, --report로 보기)
# results/에는 시험자 이름이 들어가므로 GitHub에 올리지 않는다.
import argparse
import csv
import os
import time
from dataclasses import dataclass, field
from datetime import datetime

import config
from decision.call_controller import CallController

RESULT_DIR = "results"
SUMMARY_FILE = os.path.join(RESULT_DIR, "summary.csv")
RESULT_EVENTS = ("CALL", "CANCEL", "TIMEOUT")
TRIAL_LIMIT_SEC = 45.0        # 호출·취소 시도 하나의 최대 시간 (질문이 안 나오면 실패)
AWAY_SEC = 60.0               # 딴 데 보기 시험 시간
REST_SEC = 2.0                # 시도 사이 쉬는 시간

INSTRUCTIONS = {
    "CALL": "카메라를 바라봐 주세요. 질문이 나오면, 다시 카메라를 바라보시면 됩니다.",
    "CANCEL": "카메라를 바라봐 주세요. 질문이 나오면, 이번에는 눈을 감아 주세요.",
    "AWAY": "이번에는 1분 동안 카메라를 보지 말고, 텔레비전을 보거나 옆 사람과 이야기하듯 편하게 주변을 봐 주세요.",
}
LABEL = {"CALL": "호출", "CANCEL": "취소", "AWAY": "딴 데 보기"}


@dataclass
class Trial:
    kind: str                       # CALL, CANCEL, AWAY
    no: int                         # 같은 종류 안에서 몇 번째
    outcome: str = "NONE"           # CALL, CANCEL, TIMEOUT, NONE(질문이 안 나옴) / AWAY는 OK, FALSE_ASK
    ok: bool = False
    ask_sec: float = None           # 시작부터 질문까지 (1차 응시 시간 포함)
    answer_sec: float = None        # 질문 음성이 끝난 뒤 결과까지 (확정·취소 시간 포함)
    false_asks: int = 0             # AWAY: 원치 않는 질문 횟수
    false_calls: int = 0            # AWAY: 원치 않는 호출 횟수
    face_lost: float = 0.0          # 얼굴을 못 찾은 프레임 비율
    alert_sec: float = None         # 알림 전송에 걸린 시간 (--notify)
    ack_sec: float = None           # 호출부터 '확인' 버튼까지 (--notify)
    frames: int = 0
    lost_frames: int = 0
    finished: bool = False          # 끝까지 진행한 시도만 저장한다
    events: list = field(default_factory=list)


def plan(calls=3, cancels=2, away=True):
    trials = [Trial("CALL", i + 1) for i in range(calls)] + [Trial("CANCEL", i + 1) for i in range(cancels)]
    return trials + ([Trial("AWAY", 1)] if away else [])


class ScenarioRunner:
    """시험 순서를 진행한다. 프레임마다 update(eye, now)를 부르면 된다 (카메라 없이도 시험 가능)."""

    def __init__(self, speaker, guide, dwell, trials, notifier=None, ack_wait=0.0, say=print):
        self.speaker, self.guide, self.dwell = speaker, guide, dwell
        self.trials, self.notifier, self.ack_wait = trials, notifier, ack_wait
        self.say = say                 # 화면 출력
        self.i = -1
        self.phase = "start"
        self.controller = None
        self.t0 = self.ask_at = self.question_end = self.call_at = 0.0
        self.until = 0.0
        self._next_trial(time.time())

    @property
    def done(self):
        return self.phase == "done"

    @property
    def trial(self):
        return self.trials[self.i] if 0 <= self.i < len(self.trials) else None

    def status(self, now):
        t = self.trial
        if t is None:
            return "DONE"
        head = f"{self.i + 1}/{len(self.trials)} {t.kind} #{t.no}"
        if self.phase == "run" and t.kind == "AWAY":
            return f"{head}  look away {max(0, self.t0 + AWAY_SEC - now):.0f}s"
        return f"{head}  {self.phase}"

    def _next_trial(self, now):
        self.i += 1
        if self.trial is None:
            self.phase = "done"
            self.speaker.say_async("시험이 끝났습니다. 수고하셨습니다.", "END")
            return
        t = self.trial
        self.say(f"\n── {self.i + 1}/{len(self.trials)}  {LABEL[t.kind]} {t.no}번째 ──")
        self.speaker.say_async(INSTRUCTIONS[t.kind] if t.no == 1 or t.kind == "AWAY" else
                               f"{LABEL[t.kind]} {t.no}번째입니다. " + INSTRUCTIONS[t.kind], "INSTR")
        self.phase = "instruct"

    def _sync_voice(self, now):
        for tag, finished_at in self.speaker.poll_finished():
            if tag == "INSTR" and self.phase == "instruct":
                self.phase = "run"
                self.t0 = finished_at
                self.controller = CallController(self.dwell)
            elif self.controller and tag == "ASK":
                self.controller.question_finished(finished_at)
                self.question_end = finished_at
            elif self.controller and tag in RESULT_EVENTS:
                self.controller.announcement_finished(finished_at)

    def update(self, eye, now):
        self._sync_voice(now)
        if self.notifier:
            for r in self.notifier.poll_results():
                if self.trial and self.trial.kind == "CALL" and r.ok:
                    self.trial.alert_sec = r.seconds
            for ack in self.notifier.poll_acks():
                if self.trial and self.trial.kind == "CALL" and self.call_at:
                    self.trial.ack_sec = now - self.call_at
                    self.guide.nurse_acked()
                    self.say(f"  간호사 확인: {self.trial.ack_sec:.1f}초")
        t = self.trial
        if t is None:
            return

        if self.phase == "run":
            t.frames += 1
            t.lost_frames += eye is None
            for event in self.controller.update(eye, now):
                self._on_event(t, event, now)
            if self.phase == "run":
                limit = AWAY_SEC if t.kind == "AWAY" else TRIAL_LIMIT_SEC
                if now - self.t0 >= limit and self.controller.state in ("IDLE", "COOLDOWN"):
                    self._finish(t, now)
                elif now - self.t0 >= limit + 20:          # 질문 중이어도 너무 길면 끝낸다
                    self._finish(t, now)

        elif self.phase == "ack":
            if t.ack_sec is not None or now >= self.until:
                self._rest(now)

        elif self.phase == "rest":
            if now >= self.until and not self.speaker.busy():
                self._next_trial(now)

    def _on_event(self, t, event, now):
        t.events.append(event)
        if event != "READY":
            self.say(f"  [{now - self.t0:5.1f}초] {event}")
        if event == "CALL" and self.notifier:
            self.notifier.notify_call()
        self.guide.on_event(event)
        if t.kind == "AWAY":
            t.false_asks += event == "ASK"
            t.false_calls += event == "CALL"
            return
        if event == "ASK" and t.ask_sec is None:
            t.ask_sec = now - self.t0
        elif event in RESULT_EVENTS and t.outcome == "NONE":
            t.outcome = event
            t.ok = event == t.kind
            if self.question_end:
                t.answer_sec = now - self.question_end
            if event == "CALL":
                self.call_at = now
            self._finish(t, now)

    def _finish(self, t, now):
        t.finished = True
        if t.kind == "AWAY":
            t.outcome = "FALSE_CALL" if t.false_calls else "FALSE_ASK" if t.false_asks else "OK"
            t.ok = t.outcome == "OK"
        t.face_lost = t.lost_frames / t.frames if t.frames else 0.0
        mark = "✅" if t.ok else "❌"
        self.say(f"  {mark} {LABEL[t.kind]} {t.no}: {t.outcome}")
        if t.kind == "CALL" and t.ok and self.notifier and self.ack_wait > 0:
            self.phase = "ack"
            self.until = now + self.ack_wait
            self.say(f"  Telegram '확인' 버튼을 눌러 주세요 ({self.ack_wait:.0f}초 기다림)")
        else:
            self._rest(now)

    def _rest(self, now):
        self.phase = "rest"
        self.until = now + REST_SEC
        self.question_end = self.call_at = 0.0
        self.controller = None


# ── 결과 저장 · 요약 ─────────────────────────────────
def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def summarize(name, note, trials, user):
    calls = [t for t in trials if t.kind == "CALL"]
    cancels = [t for t in trials if t.kind == "CANCEL"]
    away = [t for t in trials if t.kind == "AWAY"]
    return {
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "시험자": name, "조건": note, "응시 시간 설정": user or "(공통 기준)",
        "호출 성공": f"{sum(t.ok for t in calls)}/{len(calls)}",
        "취소 성공": f"{sum(t.ok for t in cancels)}/{len(cancels)}",
        "딴 데 보기 질문": sum(t.false_asks for t in away) if away else "",
        "딴 데 보기 호출": sum(t.false_calls for t in away) if away else "",
        "질문까지(초)": mean(t.ask_sec for t in calls + cancels),
        "호출 확정까지(초)": mean(t.answer_sec for t in calls if t.ok),
        "취소까지(초)": mean(t.answer_sec for t in cancels if t.ok),
        "알림 전송(초)": mean(t.alert_sec for t in calls),
        "간호사 확인(초)": mean(t.ack_sec for t in calls),
        "얼굴 놓침(%)": round(100 * mean(t.face_lost for t in trials), 1) if trials else "",
    }


def save(name, note, trials, user):
    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detail = os.path.join(RESULT_DIR, f"{name}_{stamp}.csv")
    with open(detail, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["순서", "시험", "번째", "결과", "성공", "질문까지(초)", "결과까지(초)", "딴 데 보기 질문",
                    "딴 데 보기 호출", "얼굴 놓침(%)", "알림 전송(초)", "간호사 확인(초)", "이벤트"])
        for i, t in enumerate(trials, 1):
            r = lambda v: "" if v is None else round(v, 2)
            w.writerow([i, LABEL[t.kind], t.no, t.outcome, "O" if t.ok else "X", r(t.ask_sec), r(t.answer_sec),
                        t.false_asks if t.kind == "AWAY" else "", t.false_calls if t.kind == "AWAY" else "",
                        round(100 * t.face_lost, 1), r(t.alert_sec), r(t.ack_sec), " ".join(t.events)])
    row = summarize(name, note, trials, user)
    new = not os.path.exists(SUMMARY_FILE)
    with open(SUMMARY_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    return detail, row


def report():
    if not os.path.exists(SUMMARY_FILE):
        print("아직 시험 결과가 없습니다. python scenario_test.py --name 이름 으로 시험하세요.")
        return
    with open(SUMMARY_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cols = ["시험자", "조건", "호출 성공", "취소 성공", "딴 데 보기 질문", "딴 데 보기 호출",
            "질문까지(초)", "호출 확정까지(초)", "알림 전송(초)", "간호사 확인(초)", "얼굴 놓침(%)"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(r.get(c, "") or "-" for c in cols) + " |")

    def total(col):
        ok = n = 0
        for r in rows:
            a, _, b = r[col].partition("/")
            ok, n = ok + int(a or 0), n + int(b or 0)
        return f"{ok}/{n} ({100 * ok / n:.0f}%)" if n else "-"
    false_asks = sum(int(r["딴 데 보기 질문"] or 0) for r in rows)
    false_calls = sum(int(r["딴 데 보기 호출"] or 0) for r in rows)
    away_runs = sum(1 for r in rows if r["딴 데 보기 질문"] != "")
    print(f"\n전체 {len(rows)}회 시험: 호출 성공 {total('호출 성공')}, 취소 성공 {total('취소 성공')}, "
          f"딴 데 보기 {away_runs}분 동안 원치 않는 질문 {false_asks}번 · 호출 {false_calls}번")


# ── 실행 ─────────────────────────────────────────────
def run(args):
    import cv2
    from input.camera_stream import CameraStream, check_reachable
    from output.notifier import Notifier
    from output.tts import Speaker
    from output.voice_guide import VoiceGuide
    from profiles.profile_manager import load_profile
    from vision.face_landmarker import FaceLandmarkDetector
    from vision.features import FeatureExtractor, load_calibration

    source = config.parse_camera_source(args.camera) if args.camera else config.CAMERA_SOURCE
    ok, why = check_reachable(source)
    if not ok:
        print(f"카메라에 연결할 수 없습니다: {why}")
        return
    stream = CameraStream(source, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()
    if not stream.wait_ready(8.0):
        stream.stop()
        print(f"카메라 영상이 들어오지 않습니다: {source}")
        return
    notifier = None
    if args.notify:
        notifier = Notifier()
        notifier.bed = f"[시험] {notifier.bed}"
        ok, info = notifier.check()
        print(f"알림: {info}" if ok else f"알림 설정 문제: {info}")

    dwell = load_profile(args.user)
    detector = FaceLandmarkDetector()
    extractor = FeatureExtractor(load_calibration(args.user))
    speaker = Speaker()
    guide = VoiceGuide(speaker, dwell)
    trials = plan(args.calls, args.cancels, not args.no_away)
    print(f"시험자: {args.name}  조건: {args.note or '-'}  응시 시간: {dwell['first_gaze_sec']:g}초 "
          f"시도 {len(trials)}개  중단: 영상 창에서 q")
    runner = ScenarioRunner(speaker, guide, dwell, trials, notifier, args.ack_wait if notifier else 0)
    last = 0.0
    try:
        while not (runner.done and not speaker.busy()):
            frame, frame_time = stream.read()
            if frame is None or frame_time == last:
                time.sleep(0.005)
                continue
            last = frame_time
            now = time.time()
            eye = extractor.update(detector.detect(frame))
            runner.update(eye, now)
            cv2.putText(frame, runner.status(now), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
            state = runner.controller.state if runner.controller else "-"
            gaze = "FACE: NOT FOUND" if eye is None else f"GAZE {'ON' if eye.gazing else 'off'}  EYE {'CLOSED' if eye.eyes_closed else 'open'}"
            cv2.putText(frame, f"{state}   {gaze}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.imshow("OpticCall - Scenario Test", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                print("\n중단했습니다. 끝난 시도까지만 저장합니다.")
                break
    finally:
        stream.stop()
        detector.close()
        cv2.destroyAllWindows()
    finished = [t for t in trials if t.finished]
    if not finished:
        print("저장할 결과가 없습니다.")
        return
    detail, row = save(args.name, args.note, finished, args.user)
    print("\n── 결과 ──")
    for k, v in row.items():
        print(f"  {k}: {'-' if v in ('', None) else v}")
    print(f"\n시도별 기록: {detail}\n전체 결과표: python scenario_test.py --report")


def main():
    parser = argparse.ArgumentParser(description="OpticCall 시험 (호출·취소·오호출)")
    parser.add_argument("--name", help="시험자 이름 (결과 파일에 기록)")
    parser.add_argument("--note", default="", help="시험 조건 (예: 안경, 누운 자세, 어두운 조명)")
    parser.add_argument("--user", help="응시 시간·보정값을 불러올 사람 (없으면 공통 기준)")
    parser.add_argument("--camera", help="이번 시험만 쓸 카메라 (DroidCam IP 또는 장치 번호)")
    parser.add_argument("--notify", action="store_true", help="실제 Telegram 알림까지 시험 ('[시험]' 표시)")
    parser.add_argument("--ack-wait", type=float, default=20.0, help="--notify일 때 '확인' 버튼을 기다리는 시간(초)")
    parser.add_argument("--calls", type=int, default=3, help="호출 시도 횟수")
    parser.add_argument("--cancels", type=int, default=2, help="취소 시도 횟수")
    parser.add_argument("--no-away", action="store_true", help="딴 데 보기(60초) 시험 빼기")
    parser.add_argument("--report", action="store_true", help="지금까지 시험한 사람 전체 결과표")
    args = parser.parse_args()
    if args.report:
        report()
    elif not args.name:
        parser.error("--name 시험자 이름을 넣어 주세요 (예: --name 시험자A)")
    else:
        run(args)


if __name__ == "__main__":
    main()
