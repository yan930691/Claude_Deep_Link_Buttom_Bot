import os
import re
import logging
import asyncio
import threading
from datetime import datetime, timezone
from flask import Flask, request as flask_request
from telegram import Update
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
PORT         = int(os.environ.get("PORT", 8080))

# ── MongoDB ───────────────────────────────────────────────────────────────
client      = MongoClient(MONGO_URI)
db          = client["tgbot"]
col_admins  = db["admins"]
col_posts   = db["posts"]
col_links   = db["links"]
col_files   = db["files"]

# ── Admin check ───────────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    count = col_admins.count_documents({"user_id": user_id})
    return count > 0

# ── Flask Server (Render အတွက်) ──────────────────────────────────────────
app_flask = Flask(__name__)
@app_flask.route('/')
def index(): return "Bot is running"

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)

# ── Handlers & States ─────────────────────────────────────────────────────
WAIT_CAPTION, WAIT_CONFIRM_A, WAIT_LINKS = range(3)
sessions: dict = {}

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("Bot စတင်ပြီ။")
async def cmd_help(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("အသုံးပြုနည်း...")

async def cmd_post(u: Update, c: ContextTypes.DEFAULT_TYPE): 
    uid = u.effective_user.id
    if not is_admin(uid): return
    sessions[uid] = {"caption": "", "caption_type": "text", "file_id": None, "buttons": []}
    await u.message.reply_text("Caption ပို့ပေးပါ:")
    return WAIT_CAPTION

async def recv_caption(u, c): return WAIT_CONFIRM_A
async def recv_confirm_a(u, c): return WAIT_LINKS
async def recv_links(u, c): return WAIT_LINKS
async def cmd_done(u, c): return ConversationHandler.END
async def cmd_cancel(u, c): return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    # ConversationHandler Definition
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

    # Adding Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(conv)

    # Flask Thread
    threading.Thread(target=run_flask, daemon=True).start()

    logger.info("Bot စတင်ပါပြီ...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
