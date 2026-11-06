# 보정 때 저장한 원본 측정값(profiles/samples_<이름>.json)으로
# 눈 감김 판정 방식과 응시 허용 범위를 바꿔 가며 정확도를 비교한다.
#   python analyze_calibration.py --user 이름
import argparse
import json
import statistics

import config


def median(samples, key):
    return statistics.median(s[key] for s in samples)


def pct(samples, fn):
    return sum(fn(s) for s in samples) / len(samples) * 100 if samples else 0.0


def main():
    parser = argparse.ArgumentParser(description="보정 데이터 분석")
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    with open(f"{config.PROFILE_DIR}/samples_{args.user}.json", encoding="utf-8") as f:
        data = json.load(f)
    look, closed, away = data["look"], data["closed"], data["away"]
    print(f"기록 프레임: 응시 {len(look)} / 감음 {len(closed)} / 둘러보기 {len(away)}\n")

    ear_th = (median(look, "ear") + median(closed, "ear")) / 2
    blink_th = (median(look, "blink") + median(closed, "blink")) / 2
    rules = {
        "EAR만": lambda s: s["ear"] <= ear_th,
        "blink만": lambda s: s["blink"] >= blink_th,
        "EAR 또는 blink": lambda s: s["ear"] <= ear_th or s["blink"] >= blink_th,
        "EAR 그리고 blink": lambda s: s["ear"] <= ear_th and s["blink"] >= blink_th,
    }
    print("── 눈 감김 판정 방식 비교 ─────────────────────────")
    print(f"  {'방식':<16}{'감은 눈 맞춤':>10}{'뜬 눈 오판정':>12}")
    for name, rule in rules.items():
        print(f"  {name:<16}{pct(closed, rule):>9.1f}%{pct(look, rule):>11.1f}%")

    center = {k: median(look, k) for k in ("iris_h", "iris_v", "yaw", "pitch")}
    print("\n── 응시 판정: 특징값별 '카메라 응시' vs '둘러보기' 차이 ──────")
    print(f"  {'특징':<8}{'응시 범위(10~90%)':>22}{'둘러보기 범위(10~90%)':>24}")
    for k in center:
        lv = sorted(abs(s[k] - center[k]) for s in look)
        av = sorted(abs(s[k] - center[k]) for s in away)
        q = lambda v, p: v[int(p * (len(v) - 1))]
        print(f"  {k:<8}{q(lv, .1):>10.3f} ~ {q(lv, .9):<10.3f}{q(av, .1):>12.3f} ~ {q(av, .9):<10.3f}")

    print("\n── 응시 허용 범위 배율별 정확도 (눈 감김은 'EAR만' 기준) ─────")
    print(f"  {'배율':<6}{'응시 맞춤':>10}{'둘러보기 오판정':>16}")
    tol = config.GAZE_TOLERANCE
    for scale in (0.5, 0.75, 1.0, 1.25, 1.5):
        def gazing(s, scale=scale):
            return s["ear"] > ear_th and all(abs(s[k] - center[k]) <= tol[k] * scale for k in center)
        print(f"  x{scale:<5}{pct(look, gazing):>9.1f}%{pct(away, gazing):>15.1f}%")


if __name__ == "__main__":
    main()
