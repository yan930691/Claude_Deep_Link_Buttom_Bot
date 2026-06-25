import os
import re
import logging
import asyncio
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from pymongo import MongoClient

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
TOKEN        = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "")
MONGO_URI    = os.environ.get("MONGO_URI", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# ── MongoDB ───────────────────────────────────────────────────────────────
client      = MongoClient(MONGO_URI)
db          = client["tgbot"]
col_admins  = db["admins"]
col_posts   = db["posts"]
col_links   = db["links"]
col_files   = db["files"]

# ── Admin check ───────────────────────────────────────────────────────────
def get_admin_ids() -> list[int]:
    return [doc["user_id"] for doc in col_admins.find({}, {"user_id": 1})]

def is_admin(user_id: int) -> bool:
    ids = get_admin_ids()
    return (not ids) or (user_id in ids)

# ── Conversation states ───────────────────────────────────────────────────
WAIT_CAPTION, WAIT_CONFIRM_A, WAIT_LINKS = range(3)
sessions: dict = {}

# ── Helpers ───────────────────────────────────────────────────────────────
DEEPLINK_RE = re.compile(r"https://t\.me/\S+\?start=\S+")

def parse_links(text: str) -> list[dict]:
    results = []
    for line in text.splitlines():
        url_match = DEEPLINK_RE.search(line)
        if not url_match: continue
        url = url_match.group(0)
        results.append({"label": url, "url": url, "created_at": datetime.now(timezone.utc)})
    return results

# ── Command Functions ─────────────────────────────────────────────────────
async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("Bot စတင်ပြီ။")
async def cmd_help(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("အသုံးပြုနည်း...")

async def cmd_post(u: Update, c: ContextTypes.DEFAULT_TYPE): 
    uid = u.effective_user.id
    if not is_admin(uid): return
    sessions[uid] = {"caption": "", "caption_type": "text", "file_id": None, "buttons": []}
    await u.message.reply_text("Caption ပို့ပေးပါ:")
    return WAIT_CAPTION

async def recv_caption(u: Update, c: ContextTypes.DEFAULT_TYPE): return WAIT_CONFIRM_A
async def recv_confirm_a(u: Update, c: ContextTypes.DEFAULT_TYPE): return WAIT_LINKS
async def recv_links(u: Update, c: ContextTypes.DEFAULT_TYPE): return WAIT_LINKS
async def cmd_done(u: Update, c: ContextTypes.DEFAULT_TYPE): return ConversationHandler.END
async def cmd_cancel(u: Update, c: ContextTypes.DEFAULT_TYPE): return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────
async def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("post", cmd_post)],
        states={
            WAIT_CAPTION: [MessageHandler(filters.ALL & ~filters.COMMAND, recv_caption)],
            WAIT_CONFIRM_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_confirm_a)],
            WAIT_LINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_links), CommandHandler("done", cmd_done)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(conv)

    logger.info("Bot စတင်ပါပြီ...")
    # Render အတွက် အရေးကြီး: close_loop=False ကို သုံးပေးခြင်း
    await app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    asyncio.run(main())
