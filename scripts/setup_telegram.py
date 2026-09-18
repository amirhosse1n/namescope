from __future__ import annotations

import os


def main() -> None:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError as exc:
        raise SystemExit("Install Telegram support first: python -m pip install -r requirements-telegram.txt") from exc

    api_id = os.getenv("TELEGRAM_API_ID") or input("Telegram API ID: ").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("Telegram API hash: ").strip()
    if not api_id.isdigit() or not api_hash:
        raise SystemExit("A numeric Telegram API ID and API hash are required. Create them at my.telegram.org.")

    print("This one-time login creates a reusable Telegram StringSession. Treat it like a password.")
    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session = client.session.save()

    print("\nAdd the following value to TELEGRAM_SESSION in your local .env file:\n")
    print(session)
    print("\nDo not commit or share this session string.")


if __name__ == "__main__":
    main()
