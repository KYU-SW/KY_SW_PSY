# 7단계 Telegram 알림 설정 도우미
#   python telegram_setup.py           -> 봇에게 메시지를 보낸 사람·단체방의 Chat ID 목록
#   python telegram_setup.py --test    -> .env의 모든 수신자에게 테스트 알림 전송
#   python telegram_setup.py --call    -> 실제 호출 알림 문구로 전송
#
# 먼저 .env에 TELEGRAM_BOT_TOKEN을 넣고, 알림 받을 사람이 봇에게 아무 메시지나 보내 둔다.
# (단체방이면 봇을 방에 초대한 뒤 방에서 /start 를 보낸다)
import argparse
import sys

import requests

from output.notifier import API_URL, Notifier, load_settings


def list_chats(token):
    r = requests.get(API_URL.format(token=token, method="getUpdates"), timeout=10)
    data = r.json()
    if not data.get("ok"):
        print(f"토큰이 올바르지 않습니다: {data.get('description', r.status_code)}")
        return
    chats = {}
    for update in data["result"]:
        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
            chats[chat["id"]] = (chat.get("type"), name)
    if not chats:
        print("아직 봇에게 메시지를 보낸 사람이 없습니다.")
        print("알림 받을 사람이 Telegram에서 봇을 찾아 '시작(/start)'을 누른 뒤 다시 실행하세요.")
        return
    print("봇에게 메시지를 보낸 대화:")
    for cid, (kind, name) in chats.items():
        print(f"  Chat ID {cid:>15}   {'단체방' if kind != 'private' else '개인'}   {name}")
    print("\n알림 받을 Chat ID를 .env의 TELEGRAM_CHAT_IDS= 뒤에 쉼표로 이어서 적으세요.")


def main():
    parser = argparse.ArgumentParser(description="OpticCall Telegram 알림 설정")
    parser.add_argument("--test", action="store_true", help="테스트 알림 전송")
    parser.add_argument("--call", action="store_true", help="호출 알림 문구로 전송")
    args = parser.parse_args()

    token, chat_ids, bed = load_settings()
    if not token:
        print(".env에 TELEGRAM_BOT_TOKEN이 없습니다. .env.example을 복사해 .env를 만들고 토큰을 넣으세요.")
        sys.exit(1)

    if not (args.test or args.call):
        list_chats(token)
        return

    if not chat_ids:
        print(".env에 TELEGRAM_CHAT_IDS가 없습니다. 먼저 python telegram_setup.py 로 Chat ID를 확인하세요.")
        sys.exit(1)
    notifier = Notifier()
    if args.call:
        notifier.notify_call()
    else:
        notifier.send_text(f"✅ OpticCall 알림 테스트\n침상: {bed}\n이 메시지가 보이면 설정이 끝난 것입니다.")
    result = notifier.wait_results(1)
    if result and result[0].ok:
        print(f"보냄: {len(result[0].sent)}명 / 실패: {len(result[0].failed)}명")
    else:
        print("아무에게도 보내지 못했습니다. 위의 실패 이유를 확인하세요.")


if __name__ == "__main__":
    main()
