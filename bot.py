import os
import re
import logging
import asyncio
import threading
from flask import Flask
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
MONGO_URI    = os.environ.get("MONGO_URI", "")
PORT         = int(os.environ.get("PORT", 8080))

# ── MongoDB ───────────────────────────────────────────────────────────────
client      = MongoClient(MONGO_URI)
db          = client["tgbot"]
col_admins  = db["admins"]

def is_admin(user_id: int) -> bool:
    return col_admins.count_documents({"user_id": user_id}) > 0

# ── Flask Server ──────────────────────────────────────────────────────────
app_flask = Flask(__name__)
@app_flask.route('/')
def index(): return "Bot is running"

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)

# ── Handlers & States ─────────────────────────────────────────────────────
WAIT_CAPTION, WAIT_CONFIRM_A, WAIT_LINKS = range(3)

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("Bot စတင်ပြီ။")
async def cmd_help(u: Update, c: ContextTypes.DEFAULT_TYPE): await u.message.reply_text("အသုံးပြုနည်း...")
async def cmd_post(u: Update, c: ContextTypes.DEFAULT_TYPE): 
    if not is_admin(u.effective_user.id): return
    await u.message.reply_text("Caption ပို့ပေးပါ:")
    return WAIT_CAPTION

async def recv_caption(u, c): return WAIT_CONFIRM_A
async def recv_confirm_a(u, c): return WAIT_LINKS
async def recv_links(u, c): return WAIT_LINKS
async def cmd_done(u, c): return ConversationHandler.END
async def cmd_cancel(u, c): return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────
async def main():
    # Application ကို build လုပ်ခြင်း
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

    # Flask ကို Background မှာ run ခြင်း
    threading.Thread(target=run_flask, daemon=True).start()

    logger.info("Bot စတင်ပါပြီ...")
    
    # Render ပတ်ဝန်းကျင်အတွက် loop ကို မပိတ်စေရန် close_loop=False ကို သုံးထားသည်
    await app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
