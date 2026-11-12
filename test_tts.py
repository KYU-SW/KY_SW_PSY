# 6단계 음성 안내 확인
#   python test_tts.py              -> 안내 문구를 하나씩 읽고 길이(초)를 잰다
#   python test_tts.py --rate 1     -> 말하기 속도 바꿔서 (-10 ~ 10)
# 뒤에서 읽는 동안 메인 루프가 멈추지 않는지도 함께 확인한다.
import argparse
import time

from output.tts import Speaker
from output.voice_guide import build_phrases
from profiles.profile_manager import load_profile


def main():
    parser = argparse.ArgumentParser(description="OpticCall 음성 안내 확인")
    parser.add_argument("--user", help="응시 시간을 불러올 사람 이름")
    parser.add_argument("--rate", type=int, default=0, help="말하기 속도 (-10 ~ 10)")
    args = parser.parse_args()

    speaker = Speaker(rate=args.rate)
    phrases = build_phrases(load_profile(args.user))
    print(f"말하기 속도: {args.rate}\n")
    for tag, text in phrases.items():
        start = time.time()
        speaker.say_async(text, tag)
        ticks = 0                       # 읽는 동안 메인 루프가 돈 횟수 (영상 프레임 대신)
        while speaker.busy():
            ticks += 1
            time.sleep(1 / 30)
        finished = speaker.poll_finished()
        length = finished[0][1] - start if finished else time.time() - start
        print(f"   -> {tag:8s} {length:4.1f}초   (읽는 동안 루프 {ticks}회 = 약 {ticks / 30:.1f}초 분량 프레임)\n")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
