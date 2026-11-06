# 4단계 사용자 보정: 음성 안내에 따라 "응시 → 눈 감기 → 둘러보기"를 녹화하고
# 그 사람에게 맞는 판정 기준값을 profiles/calibration_<이름>.json에 저장한다.
#   python calibrate.py --user 이름
# 보정할 때마다 결과가 profiles/calibration_results.csv에 한 줄씩 쌓인다.
import argparse
import csv
import itertools
import json
import os
import statistics
import time
from datetime import datetime

import cv2

import config
from input.camera_stream import CameraStream
from output.tts import Speaker
from vision.face_landmarker import FaceLandmarkDetector
from vision.features import judge, raw_features

PHASES = [
    ("look", "LOOK AT CAMERA", "눈을 뜨고, 휴대폰 카메라 렌즈를 편하게 바라봐 주세요.", 4.0),
    ("closed", "CLOSE EYES", "눈을 감아 주세요. 눈을 뜨라는 안내가 나올 때까지 계속 감고 계세요.", 3.0),
    ("away", "LOOK AROUND", "이제 눈을 떠 주세요. 카메라가 아닌 왼쪽, 오른쪽, 위, 아래를 천천히 둘러봐 주세요.", 6.0),
]
SETTLE_SEC = 1.0    # 안내가 끝나고 자세를 잡을 시간 (이 동안은 기록하지 않음)


def record(stream, detector, title, seconds):
    """seconds 동안 프레임마다 특징값을 모은다."""
    samples, missed = [], 0
    last_frame_time = 0.0
    start = time.time()
    while time.time() - start < SETTLE_SEC + seconds:
        frame, frame_time = stream.read()
        if frame is None or frame_time == last_frame_time:
            time.sleep(0.005)
            continue
        last_frame_time = frame_time
        face = detector.detect(frame)
        recording = time.time() - start >= SETTLE_SEC
        if recording:
            if face:
                samples.append(raw_features(face))
            else:
                missed += 1

        remain = SETTLE_SEC + seconds - (time.time() - start)
        color = (0, 0, 255) if recording else (0, 200, 255)
        cv2.putText(frame, title, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        cv2.putText(frame, f"{'REC' if recording else 'READY'}  {remain:.1f}s", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.imshow("OpticCall - Calibration", frame)
        cv2.waitKey(1)
    return samples, missed


def median(samples, key):
    return statistics.median(s[key] for s in samples)


def rate(samples, calib, which):
    """samples 중 judge 결과가 참인 비율(%)."""
    if not samples:
        return 0.0
    idx = 0 if which == "closed" else 1
    tol = calib.get("tolerance", config.GAZE_TOLERANCE)
    hits = sum(judge(s, calib, tol)[idx] for s in samples)
    return hits / len(samples) * 100


def tune_tolerance(look, away, calib):
    """응시 허용 범위 후보 중 둘러보기 오판정이 MAX_AWAY_FALSE_GAZE % 이하이면서
    응시를 가장 잘 잡는 값을 고른다. 같으면 범위가 넓은 쪽을 고른다.
    조건을 만족하는 후보가 없으면 오판정이 가장 적은 값을 고른다.
    """
    best = None
    for ih, iv, head in itertools.product(config.TOLERANCE_GRID["iris"], config.TOLERANCE_GRID["iris"],
                                          config.TOLERANCE_GRID["head"]):
        tol = {"iris_h": ih, "iris_v": iv, "yaw": head, "pitch": head}
        trial = dict(calib, tolerance=tol)
        hit, false = rate(look, trial, "gaze"), rate(away, trial, "gaze")
        ok = false <= config.MAX_AWAY_FALSE_GAZE
        key = (ok, round(hit, 1) if ok else -false, ih + iv + head / 100)
        if best is None or key > best[0]:
            best = (key, tol)
    return best[1]


def append_log(user, calib, results, saved):
    """보정 결과를 CSV에 한 줄 추가한다 (여러 사람 결과 비교용)."""
    new_file = not os.path.exists(config.CALIBRATION_LOG)
    with open(config.CALIBRATION_LOG, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["시각", "사용자", "저장", "응시정확도", "감김정확도", "둘러보기오판정",
                             "응시중감김오판정", "EAR기준", "blink기준", "고개좌우", "고개상하"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), user, "O" if saved else "X",
                         *[f"{r:.1f}" for r in results],
                         calib["ear_closed"], calib["blink_closed"], calib["yaw_center"], calib["pitch_center"]])


def record_all():
    """음성 안내에 따라 세 단계를 녹화한다. 카메라가 없으면 None."""
    stream = CameraStream(config.CAMERA_SOURCE, config.FRAME_WIDTH, config.RECONNECT_DELAY_SEC).start()
    if not stream.wait_ready():
        stream.stop()
        print(f"카메라 영상이 들어오지 않습니다: {config.CAMERA_SOURCE}")
        print("휴대폰 DroidCam 앱이 켜져 있는지, IP가 바뀌지 않았는지 확인해 주세요.")
        return None
    detector = FaceLandmarkDetector()
    speaker = Speaker()

    data = {}
    try:
        speaker.say("시선 보정을 시작합니다. 안내에 따라 주세요.")
        for key, title, message, seconds in PHASES:
            speaker.say(message)
            data[key], missed = record(stream, detector, title, seconds)
            print(f"  {title}: {len(data[key])}프레임 기록, 얼굴 놓침 {missed}프레임")
        speaker.say("보정이 끝났습니다.")
    finally:
        stream.stop()
        detector.close()
        cv2.destroyAllWindows()
    return data


def main():
    parser = argparse.ArgumentParser(description="OpticCall 사용자 보정")
    parser.add_argument("--user", required=True, help="보정할 사람 이름 (파일 이름에 사용)")
    parser.add_argument("--from-samples", action="store_true",
                        help="새로 녹화하지 않고 저장된 원본 측정값으로 다시 계산")
    args = parser.parse_args()
    out_path = config.calibration_file(args.user)
    samples_path = f"{config.PROFILE_DIR}/samples_{args.user}.json"
    print(f"사용자: {args.user}  →  {out_path}")

    if args.from_samples:
        with open(samples_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = record_all()
        if data is None:
            return
        # 원본 측정값도 남겨 두면 다시 녹화하지 않고 판정 방식을 비교할 수 있다
        with open(samples_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    look, closed, away = data["look"], data["closed"], data["away"]
    if len(look) < 30 or len(closed) < 30:
        print("\n얼굴이 충분히 검출되지 않아 보정값을 저장하지 않았습니다.")
        print("얼굴 전체가 화면 가운데에 오도록 휴대폰 위치를 조정하고 다시 실행해 주세요.")
        return

    print("\n── 측정값 (중앙값) ──────────────────────")
    print(f"  EAR     : 뜬 눈 {median(look, 'ear'):.3f} / 감은 눈 {median(closed, 'ear'):.3f}")
    print(f"  blink   : 뜬 눈 {median(look, 'blink'):.2f} / 감은 눈 {median(closed, 'blink'):.2f}")
    print(f"  고개 각도: 좌우 {median(look, 'yaw'):+.1f}°, 상하 {median(look, 'pitch'):+.1f}°")

    calib = {
        "ear_closed": round((median(look, "ear") + median(closed, "ear")) / 2, 4),
        "blink_closed": round((median(look, "blink") + median(closed, "blink")) / 2, 4),
        "iris_h_center": round(median(look, "iris_h"), 4),
        "iris_v_center": round(median(look, "iris_v"), 4),
        "yaw_center": round(median(look, "yaw"), 2),
        "pitch_center": round(median(look, "pitch"), 2),
    }
    calib["tolerance"] = tune_tolerance(look, away, calib)
    results = [rate(look, calib, "gaze"), rate(closed, calib, "closed"),
               rate(away, calib, "gaze"), rate(look, calib, "closed")]

    problem = None
    if median(look, "ear") < 0.12 or median(look, "blink") > 0.5:
        problem = ("'카메라를 바라봐 주세요' 단계에서 눈이 거의 감긴 것으로 측정됐습니다.",
                   "노트북 화면이 아니라 휴대폰 카메라 렌즈를 똑바로 보고 다시 실행해 주세요.")
    elif median(closed, "ear") >= median(look, "ear") or median(closed, "blink") <= median(look, "blink"):
        problem = ("눈을 감았을 때의 값이 뜬 눈과 구분되지 않습니다.",
                   "'눈을 떠 주세요' 안내가 나올 때까지 눈을 계속 감고 있었는지 확인하고 다시 실행해 주세요.")

    if problem:
        append_log(args.user, calib, results, saved=False)
        print(f"\n{problem[0]} 보정값을 저장하지 않았습니다.\n{problem[1]}")
        return

    t = calib["tolerance"]
    print(f"\n  응시 허용 범위(자동 선택): 홍채 가로 ±{t['iris_h']}, 세로 ±{t['iris_v']}, 고개 ±{t['yaw']}°")

    print("\n── 판정 정확도 (보정값 적용 시) ───────────")
    print(f"  카메라 응시 중 → '응시'로 판정   : {results[0]:5.1f}%  (높을수록 좋음)")
    print(f"  눈 감은 동안 → '눈 감음'으로 판정: {results[1]:5.1f}%  (높을수록 좋음)")
    print(f"  둘러보는 중  → '응시'로 오판정   : {results[2]:5.1f}%  (낮을수록 좋음)")
    print(f"  카메라 응시 중 → '눈 감음'으로 오판정: {results[3]:5.1f}%  (낮을수록 좋음)")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(calib, f, ensure_ascii=False, indent=2)
    append_log(args.user, calib, results, saved=True)
    print(f"\n보정값을 저장했습니다: {out_path}")


if __name__ == "__main__":
    main()
