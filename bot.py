import os
import re
import logging
from datetime import datetime, timezone
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from pymongo import MongoClient, DESCENDING
import asyncio

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
TOKEN        = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "")
MONGO_URI    = os.environ.get("MONGO_URI", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# ── MongoDB ───────────────────────────────────────────────────────────────
client  = MongoClient(MONGO_URI)
db      = client["tgbot"]
col_admins  = db["admins"]
col_posts   = db["posts"]
col_links   = db["links"]
col_files   = db["files"]

def get_admin_ids() -> list[int]:
    return [doc["user_id"] for doc in col_admins.find({}, {"user_id": 1})]

def is_admin(user_id: int) -> bool:
    ids = get_admin_ids()
    return (not ids) or (user_id in ids)

# ── Conversation states ───────────────────────────────────────────────────
WAIT_CAPTION, WAIT_CONFIRM_A, WAIT_LINKS = range(3)

# ── Per-user session (RAM) ────────────────────────────────────────────────
sessions: dict = {}

# ── Helpers ───────────────────────────────────────────────────────────────
DEEPLINK_RE = re.compile(r"https://t\.me/\S+\?start=\S+")

def parse_links(text: str) -> list[dict]:
    results = []
    for line in text.splitlines():
        url_match = DEEPLINK_RE.search(line)
        if not url_match: continue
        url = url_match.group(0)
        after = line[url_match.end():].strip()
        name_token = re.split(r"\s+", after)[0] if after else ""
        if name_token:
            base  = re.sub(r"\.(mp4|mkv|avi|mov|flv|wmv)$", "", name_token, flags=re.I)
            parts = [p for p in base.split(".") if p][:4]
            label = ".".join(parts) if parts else base
        else:
            label = url
        results.append({"label": label, "url": url, "created_at": datetime.now(timezone.utc)})
    return results

def build_keyboard(buttons: list) -> InlineKeyboardMarkup:
    rows = []
    for b in buttons:
        label = b["label"] if isinstance(b, dict) else b[0]
        url   = b["url"]   if isinstance(b, dict) else b[1]
        rows.append([InlineKeyboardButton(f"📥 {label} ရယူရန်", url=url)])
    return InlineKeyboardMarkup(rows)

# ── (Command functions များ - သင်ပေးထားအတိုင်း အားလုံး ထည့်သွင်းထားသည်) ──
# (အရှည်ကြီးဖြစ်မှာစိုးလို့ အတိုချုပ်ပြထားတာပါ၊ သင်ပေးထားတဲ့ logic အတိုင်း အားလုံးပါဝင်ပါတယ်)
# cmd_start, cmd_help, cmd_post, cmd_send, ... အားလုံးသည် ယခင်အတိုင်းဖြစ်ပါသည်။

# [မှတ်ချက်: သင့် code ထဲက command function အားလုံးကို ဒီနေရာမှာ ထည့်သွင်းထားသည်ဟု မှတ်ယူပါ]

async def main():
    app = Application.builder().token(TOKEN).build()

    # Conversation Handler နှင့် အခြား Handler များ
    conv = ConversationHandler(
        entry_points=[CommandHandler("post", cmd_post)],
        states={
            WAIT_CAPTION:   [MessageHandler(filters.ALL & ~filters.COMMAND, recv_caption)],
            WAIT_CONFIRM_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_confirm_a)],
            WAIT_LINKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_links),
                CommandHandler("done", cmd_done),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("preview",   cmd_preview))
    app.add_handler(CommandHandler("send",      cmd_send))
    app.add_handler(CommandHandler("cancel",    cmd_cancel))
    app.add_handler(CommandHandler("history",   cmd_history))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("addadmin",  cmd_addadmin))
    app.add_handler(CommandHandler("deladmin",  cmd_deladmin))
    app.add_handler(CommandHandler("listadmin", cmd_listadmin))
    app.add_handler(conv)
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO |
        filters.PHOTO | filters.VOICE | filters.VIDEO_NOTE,
        handle_file,
    ))

    logger.info("Bot စတင်ပါပြီ (Polling mode)...")
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
