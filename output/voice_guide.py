# 호출 판정 이벤트(ASK, CALL, CANCEL, TIMEOUT)를 음성 안내로 바꾸고,
# 음성이 끝난 시각을 CallController에 알려 준다.
#
#   guide = VoiceGuide(speaker, dwell)
#   for event in controller.update(eye, now):
#       guide.on_event(event)
#   guide.sync(controller)      # 매 프레임: 끝난 음성을 컨트롤러에 전달
import config


def seconds_text(sec):
    """3.0 -> '3초', 3.5 -> '3.5초'"""
    return f"{sec:g}초"


def build_phrases(dwell=None):
    d = dict(config.DWELL_DEFAULTS, **(dwell or {}))
    confirm = seconds_text(d["confirm_gaze_sec"])
    cancel = seconds_text(d["cancel_close_sec"])
    # 질문이 길수록 2차 응시를 늦게 시작하므로 짧게. 몇 초 봐야 하는지는 꼭 말한다.
    if confirm == cancel:
        ask = f"호출할까요? 카메라를 {confirm} 보시면 호출, 눈을 감으시면 취소합니다."
    else:
        ask = f"호출할까요? 카메라를 {confirm} 보시면 호출, 눈을 {cancel} 감으시면 취소합니다."
    return {
        "START": "옵틱콜을 시작합니다.",
        "ASK": ask,
        "CALL": "간호사를 호출했습니다. 잠시만 기다려 주세요.",
        "CANCEL": "호출을 취소했습니다.",
        "TIMEOUT": "응답이 없어 호출하지 않았습니다.",
    }


class VoiceGuide:
    def __init__(self, speaker, dwell=None):
        self.speaker = speaker
        self.phrases = build_phrases(dwell)

    def start(self):
        """시작 안내. 소리가 나는지 확인하는 용도도 겸한다."""
        self.speaker.say_async(self.phrases["START"], "START")

    def on_event(self, event):
        if event in self.phrases and event != "START":
            self.speaker.say_async(self.phrases[event], event)

    def sync(self, controller):
        """다 읽은 음성을 컨트롤러에 알린다. 매 프레임 부른다."""
        for tag, finished_at in self.speaker.poll_finished():
            if tag == "ASK":
                controller.question_finished(finished_at)
            elif tag in ("CALL", "CANCEL", "TIMEOUT"):
                controller.announcement_finished(finished_at)
