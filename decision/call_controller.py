# 1차 응시 → 확인 질문 → 확정/취소, 쿨다운
#
#   IDLE ──(1차 응시 N초)──▶ ASKING ──(질문 음성 끝)──▶ WAITING ─┬─(2차 응시 N초)──▶ CALL ────┐
#                                                               ├─(눈 감기 N초)───▶ CANCEL ──┼─▶ COOLDOWN
#                                                               └─(응답 없음)─────▶ TIMEOUT ─┘
#   COOLDOWN: 결과 안내 음성이 끝나고, 환자가 카메라에서 시선을 한 번 떼면 다시 IDLE
#
# 질문 음성이 나오는 동안(ASKING):
#   - 응시는 세지 않는다. 질문을 듣느라 계속 카메라를 보고 있던 사람이 저절로 호출되지 않게.
#   - 눈 감기는 센다. "눈을 감으시면 취소"를 듣자마자 감는 게 자연스럽고,
#     3.5초 눈 감기는 일부러 해야 하는 행동이며, 잘못 판정돼도 취소 쪽이 안전하다.
#     질문 중에 다 채우면 바로 CANCEL(질문을 끊는다), 질문이 끝난 뒤까지 감고 있으면 합쳐서 센다.
#
# 음성·알림은 여기서 직접 하지 않고 이벤트(ASK, CALL, CANCEL, TIMEOUT, READY)만 돌려준다.
# 바깥에서 질문 음성이 끝나면 question_finished(), 결과 안내가 끝나면 announcement_finished()를 불러 준다.
import config

IDLE, ASKING, WAITING, COOLDOWN = "IDLE", "ASKING", "WAITING", "COOLDOWN"


class HoldTimer:
    """어떤 상태가 '계속' 유지된 시간을 잰다. grace초 이하의 짧은 끊김은 무시한다."""

    def __init__(self, grace):
        self.grace = grace
        self.reset()

    def reset(self):
        self.start = None
        self.last_active = None

    def update(self, active, now):
        if active:
            if self.start is None:
                self.start = now
            self.last_active = now
        elif self.start is not None and now - self.last_active > self.grace:
            self.reset()

    def elapsed(self):
        return 0.0 if self.start is None else self.last_active - self.start

    def holding(self):
        return self.start is not None


class CallController:
    def __init__(self, dwell=None, cfg=config):
        self.dwell = dict(cfg.DWELL_DEFAULTS, **(dwell or {}))
        self.cfg = cfg
        self.gaze = HoldTimer(cfg.GRACE_SEC)
        self.closed = HoldTimer(cfg.GRACE_SEC)
        self.state = IDLE
        self.deadline = 0.0           # WAITING 응답 마감 시각
        self._announced = False       # COOLDOWN 중 결과 안내가 끝났는가
        self._face_lost_since = None

    @property
    def response_timeout(self):
        d = self.dwell
        return max(d["confirm_gaze_sec"], d["cancel_close_sec"]) + self.cfg.RESPONSE_EXTRA_SEC

    def question_finished(self, now):
        """질문 음성이 끝났을 때 부른다. 이때부터 2차 응시 시간을 잰다. (눈 감기는 이어서 센다)"""
        if self.state == ASKING:
            self.gaze.reset()
            self.state = WAITING
            self.deadline = now + self.response_timeout

    def announcement_finished(self, now):
        """결과 안내 음성(호출했습니다 등)이 끝났을 때 부른다."""
        if self.state == COOLDOWN:
            self._announced = True

    def update(self, eye, now):
        """프레임마다 부른다. eye는 EyeState(얼굴이 없으면 None). 발생한 이벤트 목록을 돌려준다."""
        self._update_timers(eye, now)
        d = self.dwell

        if self.state == IDLE:
            if self.gaze.elapsed() >= d["first_gaze_sec"]:
                self.state = ASKING
                self._reset_timers()
                return ["ASK"]

        elif self.state == ASKING:
            if self.closed.elapsed() >= d["cancel_close_sec"]:
                return self._cool_down("CANCEL")

        elif self.state == WAITING:
            if self.gaze.elapsed() >= d["confirm_gaze_sec"]:
                return self._cool_down("CALL")
            if self.closed.elapsed() >= d["cancel_close_sec"]:
                return self._cool_down("CANCEL")
            if now >= self.deadline:
                return self._cool_down("TIMEOUT")

        elif self.state == COOLDOWN:
            # 안내가 끝난 뒤, 시선을 뗀 상태(또는 얼굴이 안 보이는 상태)가 되면 다시 대기
            if self._announced and not self.gaze.holding():
                self.state = IDLE
                self._reset_timers()
                return ["READY"]
        return []

    def progress(self, now):
        """화면 표시용: (설명, 0~1 진행률)."""
        d = self.dwell
        if self.state == IDLE:
            return "gaze to ask", min(1.0, self.gaze.elapsed() / d["first_gaze_sec"])
        if self.state == WAITING:
            g = self.gaze.elapsed() / d["confirm_gaze_sec"]
            c = self.closed.elapsed() / d["cancel_close_sec"]
            return ("gaze to CALL", min(1.0, g)) if g >= c else ("close to cancel", min(1.0, c))
        if self.state == COOLDOWN:
            return ("look away to reset" if self._announced else "announcing..."), 0.0
        if self.closed.holding():          # ASKING 중 눈 감기
            return "close to cancel", min(1.0, self.closed.elapsed() / d["cancel_close_sec"])
        return "asking...", 0.0

    def _update_timers(self, eye, now):
        if eye is None:
            # 얼굴을 잠깐 놓친 건 기다려 주고, 오래 놓치면 처음부터 다시 센다
            if self._face_lost_since is None:
                self._face_lost_since = now
            if now - self._face_lost_since > self.cfg.FACE_LOST_GRACE_SEC:
                self._reset_timers()
            return
        self._face_lost_since = None
        self.gaze.update(eye.gazing, now)
        self.closed.update(eye.eyes_closed, now)

    def _reset_timers(self):
        self.gaze.reset()
        self.closed.reset()

    def _cool_down(self, event):
        self.state = COOLDOWN
        self._announced = False
        # 결과가 나온 순간에도 응시 중이면, 시선을 한 번 떼야 다시 셀 수 있게 응시 상태를 유지한다
        self.closed.reset()
        return [event]
