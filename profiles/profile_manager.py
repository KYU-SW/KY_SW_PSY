# 사용자별 설정 불러오기 · 저장 · 범위 검증
#   python -m profiles.profile_manager --user friend01                    -> 현재 설정 보기
#   python -m profiles.profile_manager --user friend01 --set first_gaze_sec=3
import argparse
import json
import os

import config

USERS_FILE = f"{config.PROFILE_DIR}/users.json"


def _load_all():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f) or {}


def validate_dwell(key, value):
    """응시 시간 값을 검사하고 0.5초 단위로 맞춘 값을 돌려준다. 잘못되면 ValueError."""
    if key not in config.DWELL_DEFAULTS:
        raise ValueError(f"알 수 없는 설정: {key} (가능: {', '.join(config.DWELL_DEFAULTS)})")
    value = float(value)
    if not config.DWELL_MIN_SEC <= value <= config.DWELL_MAX_SEC:
        raise ValueError(f"{key}는 {config.DWELL_MIN_SEC}~{config.DWELL_MAX_SEC}초 사이여야 합니다: {value}")
    step = config.DWELL_STEP_SEC
    return round(round(value / step) * step, 2)


def load_profile(user=None):
    """사용자의 응시 시간 설정. 저장된 값이 없거나 잘못되면 기본값을 쓴다."""
    profile = dict(config.DWELL_DEFAULTS)
    saved = _load_all().get(user, {}) if user else {}
    for key, value in saved.items():
        try:
            profile[key] = validate_dwell(key, value)
        except ValueError as e:
            print(f"[설정 무시] {user}: {e}")
    return profile


def set_dwell(user, key, value):
    """사용자의 응시 시간 하나를 검사한 뒤 저장하고, 저장된 값을 돌려준다."""
    value = validate_dwell(key, value)
    users = _load_all()
    users.setdefault(user, {})[key] = value
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    return value


def main():
    parser = argparse.ArgumentParser(description="사용자별 응시 시간 설정")
    parser.add_argument("--user", required=True)
    parser.add_argument("--set", action="append", default=[], metavar="이름=초",
                        help="예) first_gaze_sec=3  (여러 번 사용 가능)")
    args = parser.parse_args()
    for item in args.set:
        key, _, value = item.partition("=")
        try:
            print(f"저장: {key} = {set_dwell(args.user, key.strip(), value)}초")
        except ValueError as e:
            print(f"오류: {e}")
    print(f"\n[{args.user}] 응시 시간 설정")
    labels = {"first_gaze_sec": "1차 응시 (질문 시작)", "confirm_gaze_sec": "2차 응시 (호출 확정)",
              "cancel_close_sec": "눈 감기 (호출 취소)"}
    for key, value in load_profile(args.user).items():
        print(f"  {labels[key]:<16} {value}초")


if __name__ == "__main__":
    main()
