"""Generate a Telethon StringSession for deployment.

Run this locally, complete Telegram's login prompts, and copy the printed
session string into Render as TELETHON_SESSION. Never commit the string.
"""

from telethon import TelegramClient
from telethon.sessions import StringSession


api_id = int(input("Telegram API ID: ").strip())
api_hash = input("Telegram API hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTELETHON_SESSION=")
    print(client.session.save())
    print("\nKeep this value secret. Anyone with it can use this Telegram account session.")
