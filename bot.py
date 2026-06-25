import os
import re
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from pymongo import MongoClient, DESCENDING
import asyncio

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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
    rows = [[InlineKeyboardButton(f"📥 {b['label']} ရယူရန်", url=b['url'])] for b in buttons]
    return InlineKeyboardMarkup(rows)

# ── Command Functions ─────────────────────────────────────────────────────
async def cmd_help(u, c): await u.message.reply_text("အသုံးပြုနည်းအပြည့်အစုံ...")
async def cmd_post(u, c): 
    uid = u.effective_user.id
    if not is_admin(uid): return
    sessions[uid] = {"caption": "", "caption_type": "text", "file_id": None, "buttons": []}
    await u.message.reply_text("Caption ပို့ပါ:")
    return WAIT_CAPTION

async def recv_caption(u, c): 
    # ... (သင်ပေးထားတဲ့ logic အတိုင်း) ...
    return WAIT_CONFIRM_A

async def recv_confirm_a(u, c): return WAIT_LINKS
async def recv_links(u, c): return WAIT_LINKS
async def cmd_done(u, c): return ConversationHandler.END
async def _send_preview(bot, cid, sess, kb): pass 
async def cmd_preview(u, c): pass
async def cmd_send(u, c): pass
async def cmd_cancel(u, c): return ConversationHandler.END
async def cmd_history(u, c): pass
async def cmd_stats(u, c): pass
async def cmd_addadmin(u, c): pass
async def cmd_deladmin(u, c): pass
async def cmd_listadmin(u, c): pass
async def handle_file(u, c): pass
async def cmd_start(u, c): pass

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
    # ... (ကျန်တဲ့ handlers များ) ...

    logger.info("Bot စတင်ပြီ...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
