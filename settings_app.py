# OpticCall 설정 화면
#   python settings_app.py
#
# 명령어나 .env 파일을 직접 고치지 않고 간호사·보호자가 창에서 설정을 바꾼다.
#   - 카메라 주소 (DroidCam IP 또는 장치 번호) + 연결 확인
#   - 침상 이름, Telegram 봇 토큰·알림 받을 사람 + Chat ID 찾기·테스트 알림
#   - 환자(사용자)별 응시·확정·취소 시간 (2~10초, 0.5초 단위)
#   - [저장하고 시작] -> 새 창에서 OpticCall 실행
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import requests

import config
from input.camera_stream import check_reachable
from output.notifier import API_URL, Notifier
from profiles import profile_manager

COMMON = "(공통 기준)"
DWELL_LABELS = {
    "first_gaze_sec": "1차 응시 (질문 시작)",
    "confirm_gaze_sec": "2차 응시 (호출 확정)",
    "cancel_close_sec": "눈 감기 (호출 취소)",
}
ENV_KEYS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS", "BED_LABEL", "CAMERA_SOURCE"]


# ── .env 읽기·쓰기 (주석과 순서는 그대로 두고 값만 바꾼다) ──────────
def read_env(path=config.ENV_FILE):
    values = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#"):
                    values[key.strip()] = value.strip()
    return values


def update_env(updates, path=config.ENV_FILE):
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        key, sep, _ = line.partition("=")
        key = key.strip()
        if sep and not key.startswith("#") and key in updates:
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def users_list():
    return sorted(profile_manager._load_all().keys())


def run_command(user=None, window=True):
    """OpticCall 실행 명령. 실행 파일이면 자기 자신을 --run 으로 다시 부른다."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--run"]
    else:
        cmd = [sys.executable, os.path.join(config.BASE_DIR, "main.py")]
    if user:
        cmd += ["--user", user]
    if not window:
        cmd.append("--no-window")
    return cmd + ["--pause"]


class SettingsApp:
    def __init__(self, root):
        self.root = root
        root.title("OpticCall 설정")
        root.resizable(False, False)
        style = ttk.Style(root)
        for name in ("TLabel", "TButton", "TCheckbutton", "TLabelframe.Label"):
            style.configure(name, font=("맑은 고딕", 10))
        style.configure("Title.TLabel", font=("맑은 고딕", 14, "bold"))
        style.configure("Hint.TLabel", font=("맑은 고딕", 9), foreground="#666")

        env = read_env()
        self.has_token = bool(env.get("TELEGRAM_BOT_TOKEN"))
        pad = {"padx": 10, "pady": 4}
        ttk.Label(root, text="OpticCall 설정", style="Title.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        # 카메라
        cam = ttk.LabelFrame(root, text=" 카메라 ")
        cam.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        ttk.Label(cam, text="카메라 주소").grid(row=0, column=0, sticky="w", **pad)
        self.camera = tk.StringVar(value=env.get("CAMERA_SOURCE", ""))
        ttk.Entry(cam, textvariable=self.camera, width=24).grid(row=0, column=1, sticky="w", **pad)
        ttk.Button(cam, text="연결 확인", command=self.check_camera).grid(row=0, column=2, **pad)
        self.camera_state = ttk.Label(cam, text="", style="Hint.TLabel")
        self.camera_state.grid(row=1, column=1, columnspan=2, sticky="w", padx=10)
        ttk.Label(cam, text="DroidCam 앱에 보이는 IP (예: 10.22.9.230), USB·웹캠이면 장치 번호 (예: 1)",
                  style="Hint.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))

        # 알림
        tg = ttk.LabelFrame(root, text=" 알림 (Telegram) ")
        tg.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        ttk.Label(tg, text="침상 이름").grid(row=0, column=0, sticky="w", **pad)
        self.bed = tk.StringVar(value=env.get("BED_LABEL", ""))
        ttk.Entry(tg, textvariable=self.bed, width=24).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(tg, text="봇 토큰").grid(row=1, column=0, sticky="w", **pad)
        self.token = tk.StringVar()
        ttk.Entry(tg, textvariable=self.token, width=24, show="•").grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(tg, text="설정됨 (바꿀 때만 입력)" if self.has_token else "없음 - BotFather 토큰 입력",
                  style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=10)
        ttk.Label(tg, text="받을 사람 Chat ID").grid(row=2, column=0, sticky="w", **pad)
        self.chat_ids = tk.StringVar(value=env.get("TELEGRAM_CHAT_IDS", ""))
        ttk.Entry(tg, textvariable=self.chat_ids, width=24).grid(row=2, column=1, sticky="w", **pad)
        ttk.Button(tg, text="Chat ID 찾기", command=self.find_chats).grid(row=2, column=2, **pad)
        ttk.Label(tg, text="여러 명이면 쉼표로 구분. 받을 사람이 봇에서 '시작'을 누른 뒤 [Chat ID 찾기]",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", padx=10)
        ttk.Button(tg, text="테스트 알림 보내기", command=self.test_alert).grid(row=4, column=1, sticky="w", **pad)
        self.tg_state = ttk.Label(tg, text="", style="Hint.TLabel")
        self.tg_state.grid(row=4, column=2, sticky="w", padx=10)

        # 환자별 응시 시간
        dw = ttk.LabelFrame(root, text=" 환자별 응시 시간 ")
        dw.grid(row=3, column=0, sticky="ew", padx=12, pady=6)
        ttk.Label(dw, text="환자(사용자)").grid(row=0, column=0, sticky="w", **pad)
        self.user = tk.StringVar(value=COMMON)
        self.user_box = ttk.Combobox(dw, textvariable=self.user, values=[COMMON] + users_list(), width=22)
        self.user_box.grid(row=0, column=1, sticky="w", **pad)
        self.user_box.bind("<<ComboboxSelected>>", lambda e: self.load_user())
        self.user_box.bind("<FocusOut>", lambda e: self.load_user())
        self.user_box.bind("<Return>", lambda e: self.load_user())
        self.dwell = {}
        self.spins = []
        for i, (key, label) in enumerate(DWELL_LABELS.items(), start=1):
            ttk.Label(dw, text=label).grid(row=i, column=0, sticky="w", **pad)
            var = tk.StringVar()
            cell = ttk.Frame(dw)
            cell.grid(row=i, column=1, sticky="w", **pad)
            spin = ttk.Spinbox(cell, textvariable=var, from_=config.DWELL_MIN_SEC, to=config.DWELL_MAX_SEC,
                               increment=config.DWELL_STEP_SEC, width=6, format="%.1f")
            spin.pack(side="left")
            ttk.Label(cell, text="초").pack(side="left", padx=(6, 0))
            self.dwell[key] = var
            self.spins.append(spin)
        self.dwell_hint = ttk.Label(dw, text="", style="Hint.TLabel")
        self.dwell_hint.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))
        self.load_user()

        # 실행
        bottom = ttk.Frame(root)
        bottom.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 12))
        self.window = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text="영상 창 보기", variable=self.window).pack(side="left")
        ttk.Button(bottom, text="저장하고 시작", command=self.save_and_start).pack(side="right", padx=(6, 0))
        ttk.Button(bottom, text="저장", command=self.save).pack(side="right")

    # ── 환자별 응시 시간 ─────────────────────────────────
    def current_user(self):
        name = self.user.get().strip()
        return None if name in ("", COMMON) else name

    def load_user(self):
        user = self.current_user()
        profile = profile_manager.load_profile(user)
        for key, var in self.dwell.items():
            var.set(f"{profile[key]:.1f}")
        state = "disabled" if user is None else "normal"
        for spin in self.spins:
            spin.configure(state=state)
        if user is None:
            self.dwell_hint.configure(text="공통 기준은 기본값(3.5초). 환자 이름을 입력하면 그 환자만 따로 바꿀 수 있습니다.")
        elif user not in users_list():
            self.dwell_hint.configure(text=f"'{user}' 새 환자 - 저장하면 만들어집니다.")
        else:
            self.dwell_hint.configure(text=f"'{user}' 환자의 설정입니다.")

    # ── 확인 버튼들 (오래 걸릴 수 있어서 뒤에서 하고 결과만 표시) ─────
    def background(self, work, done):
        def run():
            result = work()
            self.root.after(0, lambda: done(result))
        threading.Thread(target=run, daemon=True).start()

    def check_camera(self):
        value = self.camera.get().strip() or "0"
        source = config.parse_camera_source(value)
        self.camera_state.configure(text="확인 중...")
        self.background(lambda: check_reachable(source),
                        lambda r: self.camera_state.configure(
                            text=("✅ 연결됨: " if r[0] else "❌ ") + (str(source) if r[0] else r[1])))

    def token_value(self):
        return self.token.get().strip() or read_env().get("TELEGRAM_BOT_TOKEN", "")

    def find_chats(self):
        token = self.token_value()
        if not token:
            messagebox.showwarning("OpticCall", "봇 토큰을 먼저 입력하세요.")
            return

        def work():
            try:
                data = requests.get(API_URL.format(token=token, method="getUpdates"), timeout=10).json()
            except (requests.RequestException, ValueError) as e:
                return f"텔레그램 서버에 연결할 수 없습니다 ({type(e).__name__})", {}
            if not data.get("ok"):
                return f"봇 토큰이 올바르지 않습니다 ({data.get('description', '')})", {}
            chats = {}
            for update in data["result"]:
                msg = update.get("message") or update.get("my_chat_member") or {}
                chat = msg.get("chat")
                if chat:
                    name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
                    chats[str(chat["id"])] = name
            return None, chats

        self.background(work, self.show_chats)

    def show_chats(self, result):
        error, chats = result
        if error:
            messagebox.showerror("OpticCall", error)
            return
        if not chats:
            messagebox.showinfo("OpticCall", "아직 봇에게 메시지를 보낸 사람이 없습니다.\n"
                                             "알림 받을 사람이 Telegram에서 봇을 찾아 '시작'을 누른 뒤 다시 눌러 주세요.")
            return
        current = [c.strip() for c in self.chat_ids.get().split(",") if c.strip()]
        win = tk.Toplevel(self.root)
        win.title("알림 받을 사람 선택")
        win.transient(self.root)
        ttk.Label(win, text="봇에게 메시지를 보낸 사람입니다. 알림 받을 사람을 고르세요.").pack(anchor="w", padx=12, pady=(12, 6))
        picks = {}
        for cid, name in chats.items():
            var = tk.BooleanVar(value=cid in current)
            ttk.Checkbutton(win, text=f"{name}  (Chat ID {cid})", variable=var).pack(anchor="w", padx=20)
            picks[cid] = var

        def apply():
            chosen = [c for c in current if c not in picks] + [c for c, v in picks.items() if v.get()]
            self.chat_ids.set(",".join(chosen))
            win.destroy()
        ttk.Button(win, text="적용", command=apply).pack(anchor="e", padx=12, pady=12)

    def test_alert(self):
        token = self.token_value()
        ids = [c.strip() for c in self.chat_ids.get().split(",") if c.strip()]
        if not (token and ids):
            messagebox.showwarning("OpticCall", "봇 토큰과 받을 사람 Chat ID를 먼저 입력하세요.")
            return
        bed = self.bed.get().strip() or "침상 미지정"
        notifier = Notifier(token, ids, bed)
        self.tg_state.configure(text="보내는 중...")

        def work():
            notifier.send_text(f"✅ OpticCall 알림 테스트\n침상: {bed}\n이 메시지가 보이면 설정이 끝난 것입니다.")
            r = notifier.wait_results(1, timeout=30)
            return r[0] if r else None

        def done(r):
            if r and r.ok:
                text = f"✅ {len(r.sent)}명에게 보냄" + (f", {len(r.failed)}명 실패" if r.failed else "")
            else:
                text = "❌ " + ("; ".join(why for _, why in r.failed) if r else "응답 없음")
            self.tg_state.configure(text=text)
        self.background(work, done)

    # ── 저장 · 시작 ───────────────────────────────────────
    def save(self, quiet=False):
        ids = [c.strip() for c in self.chat_ids.get().split(",") if c.strip()]
        bad = [c for c in ids if not c.lstrip("-").isdigit()]
        if bad:
            messagebox.showerror("OpticCall", f"Chat ID는 숫자여야 합니다: {', '.join(bad)}")
            return False
        user = self.current_user()
        values = {}
        if user:
            try:
                values = {k: profile_manager.validate_dwell(k, v.get()) for k, v in self.dwell.items()}
            except ValueError:
                messagebox.showerror("OpticCall", f"응시 시간은 {config.DWELL_MIN_SEC:g}~{config.DWELL_MAX_SEC:g}초 사이로 입력하세요.")
                return False
        updates = {"CAMERA_SOURCE": self.camera.get().strip(), "BED_LABEL": self.bed.get().strip(),
                   "TELEGRAM_CHAT_IDS": ",".join(ids)}
        if self.token.get().strip():
            updates["TELEGRAM_BOT_TOKEN"] = self.token.get().strip()
        update_env(updates)
        for key, value in values.items():
            profile_manager.set_dwell(user, key, value)
        if self.token.get().strip():
            self.has_token = True
            self.token.set("")
        self.user_box.configure(values=[COMMON] + users_list())
        self.load_user()
        if not quiet:
            messagebox.showinfo("OpticCall", "저장했습니다.")
        return True

    def save_and_start(self):
        if not self.save(quiet=True):
            return
        cmd = run_command(self.current_user(), self.window.get())
        subprocess.Popen(cmd, cwd=config.BASE_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.root.destroy()


def sharp_text():
    """화면 배율(125%, 150%)에서 글자가 흐릿하게 보이지 않게 한다."""
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def main():
    sharp_text()
    if getattr(sys, "frozen", False):        # 실행 파일이면 설정 화면 뒤의 검은 창을 숨긴다
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    root = tk.Tk()
    SettingsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
