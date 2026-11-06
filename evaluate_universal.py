# 공통 기준(보정 없이 모두에게 같은 값)이 사람마다 얼마나 잘 맞는지 확인한다.
# 보정할 때 저장된 원본 측정값 profiles/samples_*.json을 모두 읽어서 계산한다.
#   python evaluate_universal.py
# 사람을 늘리려면: python calibrate.py --user 새이름  (녹화만 해도 samples 파일이 생긴다)
import glob
import json
import os

import config
from vision.features import judge


def pct(samples, fn):
    return sum(fn(s) for s in samples) / len(samples) * 100 if samples else 0.0


def longest_run_sec(samples, fn, fps=30):
    best = cur = 0
    for s in samples:
        cur = cur + 1 if fn(s) else 0
        best = max(best, cur)
    return best / fps


def main():
    calib, tol = config.DEFAULT_CALIBRATION, config.GAZE_TOLERANCE
    closed = lambda s: judge(s, calib, tol)[0]
    gazing = lambda s: judge(s, calib, tol)[1]
    dwell = config.DWELL_DEFAULTS["first_gaze_sec"]

    files = sorted(glob.glob(f"{config.PROFILE_DIR}/samples_*.json"))
    if not files:
        print("profiles/samples_*.json 이 없습니다. calibrate.py로 먼저 녹화해 주세요.")
        return

    print(f"공통 기준으로 평가 (보정 없음, {len(files)}명)\n")
    header = f"{'사용자':<12}{'응시 맞춤':>9}{'감김 맞춤':>9}{'둘러보기 오판정':>14}{'최장 연속':>9}{'뜬눈→감김':>10}"
    print(header)
    print("-" * len(header.encode("euc-kr")))
    rows = []
    for path in files:
        user = os.path.basename(path)[len("samples_"):-len(".json")]
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if len(d.get("look", [])) < 30 or len(d.get("closed", [])) < 30:
            print(f"{user:<12}  (데이터 부족으로 제외)")
            continue
        row = (pct(d["look"], gazing), pct(d["closed"], closed), pct(d["away"], gazing),
               longest_run_sec(d["away"], gazing), pct(d["look"], closed))
        rows.append(row)
        print(f"{user:<12}{row[0]:>8.1f}%{row[1]:>8.1f}%{row[2]:>13.1f}%{row[3]:>8.1f}s{row[4]:>9.1f}%")

    if rows:
        avg = [sum(r[i] for r in rows) / len(rows) for i in range(5)]
        print("-" * len(header.encode("euc-kr")))
        print(f"{'평균':<12}{avg[0]:>8.1f}%{avg[1]:>8.1f}%{avg[2]:>13.1f}%{max(r[3] for r in rows):>8.1f}s{avg[4]:>9.1f}%")
        print(f"\n'최장 연속'은 둘러보는 중 응시로 잘못 잡힌 시간이 가장 길게 이어진 값입니다.")
        print(f"이 값이 1차 응시 시간({dwell}초)보다 짧으면 둘러보기만으로 질문이 나오지 않습니다.")


if __name__ == "__main__":
    main()
