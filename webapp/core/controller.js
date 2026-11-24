// 1차 응시 → 확인 질문 → 확정/취소, 쿨다운 (파이썬 decision/call_controller.py를 그대로 옮김)
//
//   IDLE ──(1차 응시 N초)──▶ ASKING ──(질문 음성 끝)──▶ WAITING ─┬─(2차 응시 N초)──▶ CALL ────┐
//                                                               ├─(눈 감기 N초)───▶ CANCEL ──┼─▶ COOLDOWN
//                                                               └─(응답 없음)─────▶ TIMEOUT ─┘
//   COOLDOWN: 결과 안내 음성이 끝나고, 환자가 시선을 한 번 떼면 다시 IDLE
export const IDLE = "IDLE", ASKING = "ASKING", WAITING = "WAITING", COOLDOWN = "COOLDOWN";

export const DWELL_DEFAULTS = { first_gaze_sec: 3.5, confirm_gaze_sec: 3.5, cancel_close_sec: 3.5 };
export const DWELL_MIN_SEC = 2.0;
export const DWELL_MAX_SEC = 10.0;
export const DWELL_STEP_SEC = 0.5;
export const GRACE_SEC = 0.5;
export const FACE_LOST_GRACE_SEC = 1.0;
export const RESPONSE_EXTRA_SEC = 7.0;

class HoldTimer {
  constructor(grace) {
    this.grace = grace;
    this.reset();
  }
  reset() {
    this.start = null;
    this.lastActive = null;
  }
  update(active, now) {
    if (active) {
      if (this.start === null) this.start = now;
      this.lastActive = now;
    } else if (this.start !== null && now - this.lastActive > this.grace) {
      this.reset();
    }
  }
  elapsed() {
    return this.start === null ? 0 : this.lastActive - this.start;
  }
  holding() {
    return this.start !== null;
  }
}

export class CallController {
  constructor(dwell) {
    this.dwell = { ...DWELL_DEFAULTS, ...(dwell || {}) };
    this.gaze = new HoldTimer(GRACE_SEC);
    this.closed = new HoldTimer(GRACE_SEC);
    this.state = IDLE;
    this.deadline = 0;
    this.announced = false;
    this.faceLostSince = null;
  }

  get responseTimeout() {
    const d = this.dwell;
    return Math.max(d.confirm_gaze_sec, d.cancel_close_sec) + RESPONSE_EXTRA_SEC;
  }

  questionFinished(now) {
    if (this.state === ASKING) {
      this.gaze.reset();
      this.state = WAITING;
      this.deadline = now + this.responseTimeout;
    }
  }

  announcementFinished() {
    if (this.state === COOLDOWN) this.announced = true;
  }

  // eye: { gazing, eyesClosed } 또는 null(얼굴 없음). 발생한 이벤트 배열을 돌려준다.
  update(eye, now) {
    this.updateTimers(eye, now);
    const d = this.dwell;
    if (this.state === IDLE) {
      if (this.gaze.elapsed() >= d.first_gaze_sec) {
        this.state = ASKING;
        this.resetTimers();
        return ["ASK"];
      }
    } else if (this.state === ASKING) {
      if (this.closed.elapsed() >= d.cancel_close_sec) return this.coolDown("CANCEL");
    } else if (this.state === WAITING) {
      if (this.gaze.elapsed() >= d.confirm_gaze_sec) return this.coolDown("CALL");
      if (this.closed.elapsed() >= d.cancel_close_sec) return this.coolDown("CANCEL");
      if (now >= this.deadline) return this.coolDown("TIMEOUT");
    } else if (this.state === COOLDOWN) {
      if (this.announced && !this.gaze.holding()) {
        this.state = IDLE;
        this.resetTimers();
        return ["READY"];
      }
    }
    return [];
  }

  // 화면 표시용: { kind, value(0~1), remain(초) }
  progress(now) {
    const d = this.dwell;
    if (this.state === IDLE) return { kind: "gaze", value: Math.min(1, this.gaze.elapsed() / d.first_gaze_sec) };
    if (this.state === WAITING) {
      const g = this.gaze.elapsed() / d.confirm_gaze_sec;
      const c = this.closed.elapsed() / d.cancel_close_sec;
      const remain = Math.max(0, this.deadline - now);
      return g >= c ? { kind: "confirm", value: Math.min(1, g), remain } : { kind: "close", value: Math.min(1, c), remain };
    }
    if (this.state === COOLDOWN) return { kind: this.announced ? "lookaway" : "announce", value: 0 };
    if (this.closed.holding()) return { kind: "close", value: Math.min(1, this.closed.elapsed() / d.cancel_close_sec) };
    return { kind: "asking", value: 0 };
  }

  updateTimers(eye, now) {
    if (!eye) {
      if (this.faceLostSince === null) this.faceLostSince = now;
      if (now - this.faceLostSince > FACE_LOST_GRACE_SEC) this.resetTimers();
      return;
    }
    this.faceLostSince = null;
    this.gaze.update(eye.gazing, now);
    this.closed.update(eye.eyesClosed, now);
  }

  resetTimers() {
    this.gaze.reset();
    this.closed.reset();
  }

  coolDown(event) {
    this.state = COOLDOWN;
    this.announced = false;
    this.closed.reset();
    return [event];
  }
}

export const secondsText = (s) => `${+s.toFixed(1)}초`;

export function buildPhrases(dwell) {
  const d = { ...DWELL_DEFAULTS, ...(dwell || {}) };
  const confirm = secondsText(d.confirm_gaze_sec);
  const cancel = secondsText(d.cancel_close_sec);
  const ask =
    confirm === cancel
      ? `호출할까요? 카메라를 ${confirm} 보시면 호출, 눈을 감으시면 취소합니다.`
      : `호출할까요? 카메라를 ${confirm} 보시면 호출, 눈을 ${cancel} 감으시면 취소합니다.`;
  return {
    START: "옵틱콜을 시작합니다.",
    ASK: ask,
    CALL: "간호사를 호출했습니다. 잠시만 기다려 주세요.",
    CANCEL: "호출을 취소했습니다.",
    TIMEOUT: "응답이 없어 호출하지 않았습니다.",
    NOTIFY_FAIL: "알림을 보내지 못했습니다. 다시 호출해 주세요.",
    ACK: "간호사가 호출을 확인했습니다. 곧 도착합니다.",
  };
}
