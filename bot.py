import os
import re
import logging
from datetime import datetime, timezone
from flask import Flask, request as flask_request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from pymongo import MongoClient, DESCENDING
import asyncio
import threading

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
TOKEN        = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "")
PORT         = int(os.environ.get("PORT", 8080))
MONGO_URI    = os.environ.get("MONGO_URI", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")  # e.g. WZNmoviefilsend_bot

# ── MongoDB ───────────────────────────────────────────────────────────────
client  = MongoClient(MONGO_URI)
db      = client["tgbot"]
col_admins  = db["admins"]    # { user_id, username, added_at }
col_posts   = db["posts"]     # { caption, caption_type, file_id, buttons, sent_at, channel_id }
col_links   = db["links"]     # { label, url, created_at }
col_files   = db["files"]     # { file_id, file_name, file_type, deeplink, uploaded_by, created_at }

def get_admin_ids() -> list[int]:
    return [doc["user_id"] for doc in col_admins.find({}, {"user_id": 1})]

def is_admin(user_id: int) -> bool:
    ids = get_admin_ids()
    return (not ids) or (user_id in ids)

# ── Conversation states ───────────────────────────────────────────────────
WAIT_CAPTION, WAIT_CONFIRM_A, WAIT_LINKS = range(3)

# ── Per-user session (RAM) ────────────────────────────────────────────────
sessions: dict = {}

# ── Flask keep-alive ──────────────────────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def health():
    return "✅ Bot အလုပ်လုပ်နေပါသည်", 200

@flask_app.route("/health")
def health2():
    return "OK", 200

# ── Helpers ───────────────────────────────────────────────────────────────
DEEPLINK_RE = re.compile(r"https://t\.me/\S+\?start=\S+")

def parse_links(text: str) -> list[dict]:
    results = []
    for line in text.splitlines():
        url_match = DEEPLINK_RE.search(line)
        if not url_match:
            continue
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


# ── /help ─────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *အသုံးပြုနည်း*\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "▶️ *Post တည်ဆောက်ရန်:*\n"
        "1. /post ရိုက်\n"
        "2. Caption (ဇာတ်ညွှန်း / ရုပ်ပုံ / ဗီဒီယို) ပို့\n"
        "3. `a` ရိုက်\n"
        "4. Deep Link များ ပို့\n"
        "5. /done → Preview\n"
        "6. /send → Channel ပို့\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "▶️ *Deep Link ပုံစံ:*\n"
        "`🔗 ... https://t.me/BOT?start=XXX  File.mp4`\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "▶️ *Admin Commands:*\n"
        "/addadmin `userID` — Admin ထည့်\n"
        "/deladmin `userID` — Admin ဖျက်\n"
        "/listadmin — Admin စာရင်း\n"
        "/history — Post မှတ်တမ်း (နောက်ဆုံး ၁၀)\n"
        "/stats — Bot စာရင်းအင်း",
        parse_mode="Markdown",
    )


# ── /post ─────────────────────────────────────────────────────────────────
async def cmd_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ အသုံးပြုနိုင်ပါသည်။")
        return ConversationHandler.END

    sessions[uid] = {"caption": "", "caption_type": "text", "file_id": None, "buttons": []}
    await update.message.reply_text(
        "📝 *Caption ပို့ပါ:*\n\n"
        "ဇာတ်ကား info၊ ရုပ်ပုံ၊ ဗီဒီယို စသည် ပို့နိုင်သည်။",
        parse_mode="Markdown",
    )
    return WAIT_CAPTION


async def recv_caption(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    sess = sessions[uid]

    if msg.photo:
        sess["caption_type"] = "photo"
        sess["file_id"]      = msg.photo[-1].file_id
        sess["caption"]      = msg.caption or ""
    elif msg.video:
        sess["caption_type"] = "video"
        sess["file_id"]      = msg.video.file_id
        sess["caption"]      = msg.caption or ""
    elif msg.document:
        sess["caption_type"] = "document"
        sess["file_id"]      = msg.document.file_id
        sess["caption"]      = msg.caption or ""
    else:
        sess["caption_type"] = "text"
        sess["caption"]      = msg.text or ""

    await update.message.reply_text(
        "✅ Caption သိမ်းပြီး!\n\n"
        "ယခု `a` တစ်လုံး ရိုက်ပါ။",
        parse_mode="Markdown",
    )
    return WAIT_CONFIRM_A


async def recv_confirm_a(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if (update.message.text or "").strip().lower() != "a":
        await update.message.reply_text("⚠️ `a` တစ်လုံးသာ ရိုက်ပါ။", parse_mode="Markdown")
        return WAIT_CONFIRM_A

    await update.message.reply_text(
        "🔗 *Deep Link များ ပို့ပါ:*\n\n"
        "တစ်ကြိမ်တည်း သို့မဟုတ် တစ်ခုချင်း ပို့နိုင်သည်။\n"
        "ပြီးရင် /done ရိုက်ပါ။",
        parse_mode="Markdown",
    )
    return WAIT_LINKS


async def recv_links(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    text   = update.message.text or ""
    parsed = parse_links(text)

    if not parsed:
        await update.message.reply_text(
            "⚠️ Deep Link မတွေ့ပါ။\nပုံစံ: `https://t.me/BOT?start=XXX`\n"
            "ဆက်ပို့ သို့ /done ရိုက်ပါ။",
            parse_mode="Markdown",
        )
        return WAIT_LINKS

    sessions[uid]["buttons"].extend(parsed)
    # Save each link to DB too
    if parsed:
        col_links.insert_many(parsed)

    count = len(sessions[uid]["buttons"])
    await update.message.reply_text(
        f"✅ Link {len(parsed)} ခု ထည့်ပြီး! (စုစုပေါင်း {count} ခု)\n"
        "ဆက်ပို့ သို့ /done ရိုက်ပါ။"
    )
    return WAIT_LINKS


# ── /done ─────────────────────────────────────────────────────────────────
async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in sessions or not sessions[uid].get("buttons"):
        await update.message.reply_text("⚠️ Link မရှိသေးပါ။ /post မှ စတင်ပါ။")
        return ConversationHandler.END

    sess     = sessions[uid]
    keyboard = build_keyboard(sess["buttons"])

    await update.message.reply_text(
        f"👁 *Preview:*  Button {len(sess['buttons'])} ခု\n\n"
        "✅ Channel ပို့ရန်: /send\n"
        "❌ ပယ်ဖျက်ရန်: /cancel",
        parse_mode="Markdown",
    )
    await _send_preview(ctx.bot, uid, sess, keyboard)
    return ConversationHandler.END


async def _send_preview(bot, chat_id, sess, keyboard):
    try:
        ctype = sess.get("caption_type", "text")
        cap   = sess.get("caption") or None
        fid   = sess.get("file_id")
        if ctype == "photo":
            await bot.send_photo(chat_id, fid, caption=cap, reply_markup=keyboard)
        elif ctype == "video":
            await bot.send_video(chat_id, fid, caption=cap, reply_markup=keyboard)
        elif ctype == "document":
            await bot.send_document(chat_id, fid, caption=cap, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, text=cap or "🎬 ဇာတ်ကားများ ရယူရန်:", reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(chat_id, f"Preview error: {e}")


# ── /preview ──────────────────────────────────────────────────────────────
async def cmd_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in sessions or not sessions[uid].get("buttons"):
        await update.message.reply_text("⚠️ Post မရှိသေးပါ။ /post မှ စတင်ပါ။")
        return
    sess = sessions[uid]
    await _send_preview(ctx.bot, uid, sess, build_keyboard(sess["buttons"]))


# ── /send ─────────────────────────────────────────────────────────────────
async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ ပို့နိုင်ပါသည်။")
        return
    if uid not in sessions or not sessions[uid].get("buttons"):
        await update.message.reply_text("⚠️ Post မရှိသေးပါ။ /post မှ စတင်ပါ။")
        return
    if not CHANNEL_ID:
        await update.message.reply_text("⚠️ CHANNEL_ID မသတ်မှတ်ရသေးပါ။")
        return

    sess     = sessions[uid]
    keyboard = build_keyboard(sess["buttons"])

    try:
        await _send_preview(ctx.bot, CHANNEL_ID, sess, keyboard)

        # Save post to MongoDB
        col_posts.insert_one({
            "caption":      sess.get("caption", ""),
            "caption_type": sess.get("caption_type", "text"),
            "file_id":      sess.get("file_id"),
            "buttons":      sess["buttons"],
            "channel_id":   CHANNEL_ID,
            "sent_by":      uid,
            "sent_at":      datetime.now(timezone.utc),
        })

        await update.message.reply_text(
            f"✅ Channel သို့ Post တင်ပြီး!\n"
            f"Button {len(sess['buttons'])} ခု ပါဝင်သည်။\n\n"
            "📊 /stats — စာရင်းကြည့်\n"
            "📋 /history — မှတ်တမ်းကြည့်\n"
            "🆕 Post အသစ်: /post"
        )
        sessions.pop(uid, None)

    except Exception as e:
        await update.message.reply_text(f"❌ ပို့မရပါ: {e}")


# ── /cancel ───────────────────────────────────────────────────────────────
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ ပယ်ဖျက်ပြီး။\nPost အသစ်: /post")
    return ConversationHandler.END


# ── /history ──────────────────────────────────────────────────────────────
async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ ကြည့်နိုင်ပါသည်။")
        return

    posts = list(col_posts.find().sort("sent_at", DESCENDING).limit(10))
    if not posts:
        await update.message.reply_text("📭 Post မှတ်တမ်း မရှိသေးပါ။")
        return

    lines = ["📋 *နောက်ဆုံး Post မှတ်တမ်း (၁၀)*\n━━━━━━━━━━━━━━━━━━"]
    for i, p in enumerate(posts, 1):
        sent = p.get("sent_at")
        date = sent.strftime("%Y-%m-%d %H:%M") if sent else "—"
        cap  = (p.get("caption") or "")[:40] or "(ရုပ်ပုံ/ဗီဒီယို)"
        btns = len(p.get("buttons", []))
        lines.append(f"{i}. `{date}`\n   📝 {cap}\n   🔘 Button {btns} ခု")

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


# ── /stats ────────────────────────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ ကြည့်နိုင်ပါသည်။")
        return

    total_posts  = col_posts.count_documents({})
    total_links  = col_links.count_documents({})
    total_admins = col_admins.count_documents({})
    total_files  = col_files.count_documents({})

    await update.message.reply_text(
        "📊 *Bot စာရင်းအင်း*\n\n"
        f"📮 Post စုစုပေါင်း  : `{total_posts}`\n"
        f"🔗 Link စုစုပေါင်း  : `{total_links}`\n"
        f"📁 File စုစုပေါင်း  : `{total_files}`\n"
        f"👤 Admin အရေအတွက် : `{total_admins}`\n",
        parse_mode="Markdown",
    )


# ── /addadmin ─────────────────────────────────────────────────────────────
async def cmd_addadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ ထည့်နိုင်ပါသည်။")
        return

    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "⚠️ ပုံစံ: `/addadmin 123456789`\n"
            "User ID ရှာရန်: @userinfobot",
            parse_mode="Markdown",
        )
        return

    new_id = int(args[0])
    if col_admins.find_one({"user_id": new_id}):
        await update.message.reply_text(f"ℹ️ `{new_id}` သည် Admin ရှိပြီးဖြစ်သည်။", parse_mode="Markdown")
        return

    col_admins.insert_one({"user_id": new_id, "added_by": uid, "added_at": datetime.now(timezone.utc)})
    await update.message.reply_text(f"✅ `{new_id}` ကို Admin ထည့်ပြီး!", parse_mode="Markdown")


# ── /deladmin ─────────────────────────────────────────────────────────────
async def cmd_deladmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ ဖျက်နိုင်ပါသည်။")
        return

    args = ctx.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("⚠️ ပုံစံ: `/deladmin 123456789`", parse_mode="Markdown")
        return

    del_id = int(args[0])
    result = col_admins.delete_one({"user_id": del_id})
    if result.deleted_count:
        await update.message.reply_text(f"✅ `{del_id}` ကို Admin မှ ဖျက်ပြီး!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ `{del_id}` သည် Admin မဟုတ်ပါ။", parse_mode="Markdown")


# ── /listadmin ────────────────────────────────────────────────────────────
async def cmd_listadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ Admin များသာ ကြည့်နိုင်ပါသည်။")
        return

    admins = list(col_admins.find({}, {"user_id": 1, "added_at": 1}))
    if not admins:
        await update.message.reply_text("📭 Admin မရှိသေးပါ။ (ENV ADMIN_IDS သုံး)")
        return

    lines = ["👤 *Admin စာရင်း*\n━━━━━━━━━━━━━━━━━━"]
    for i, a in enumerate(admins, 1):
        date = a.get("added_at", "").strftime("%Y-%m-%d") if a.get("added_at") else "—"
        lines.append(f"{i}. `{a['user_id']}` — {date}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── File Handler (Admin ပို့သမျှ file → deeplink ထုတ်) ─────────────────────
async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return  # Admin မဟုတ်ရင် ignore

    msg = update.message
    bot_username = BOT_USERNAME or ctx.bot.username

    # File type & info ရယူ
    if msg.document:
        file_id   = msg.document.file_id
        file_name = msg.document.file_name or "file"
        file_type = "document"
    elif msg.video:
        file_id   = msg.video.file_id
        file_name = msg.video.file_name or "video.mp4"
        file_type = "video"
    elif msg.audio:
        file_id   = msg.audio.file_id
        file_name = msg.audio.file_name or "audio.mp3"
        file_type = "audio"
    elif msg.photo:
        file_id   = msg.photo[-1].file_id
        file_name = "photo.jpg"
        file_type = "photo"
    elif msg.voice:
        file_id   = msg.voice.file_id
        file_name = "voice.ogg"
        file_type = "voice"
    elif msg.video_note:
        file_id   = msg.video_note.file_id
        file_name = "video_note.mp4"
        file_type = "video_note"
    else:
        return  # ဘာ file မှ မဟုတ်ရင် ignore

    # MongoDB မှာ file သိမ်း
    deeplink = f"https://t.me/{bot_username}?start={file_id}"
    col_files.update_one(
        {"file_id": file_id},
        {"$set": {
            "file_id":     file_id,
            "file_name":   file_name,
            "file_type":   file_type,
            "deeplink":    deeplink,
            "uploaded_by": uid,
            "created_at":  datetime.now(timezone.utc),
        }},
        upsert=True,
    )

    # WZNmoviefilsend_bot ပုံစံအတိုင်း deeplink message ပြန်ပေး
    await update.message.reply_text(
        f"🔗 သင်၏ Deep Link အဆင်သင့်ဖြစ်ပါပြီ။  "
        f"{deeplink}  {file_name}",
        quote=True,
    )


# ── /start → deeplink file ပြန်ပို့ ────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    uid  = update.effective_user.id

    # deeplink နဲ့ ဝင်လာရင် → file ပြန်ပို့
    if args:
        file_id = args[0]
        # DB မှာ ရှိသလား စစ်
        record = col_files.find_one({"file_id": file_id})
        ftype  = record["file_type"] if record else None

        try:
            if ftype == "document" or ftype is None:
                await ctx.bot.send_document(uid, document=file_id)
            elif ftype == "video":
                await ctx.bot.send_video(uid, video=file_id)
            elif ftype == "audio":
                await ctx.bot.send_audio(uid, audio=file_id)
            elif ftype == "photo":
                await ctx.bot.send_photo(uid, photo=file_id)
            elif ftype == "voice":
                await ctx.bot.send_voice(uid, voice=file_id)
            elif ftype == "video_note":
                await ctx.bot.send_video_note(uid, video_note=file_id)
            else:
                await ctx.bot.send_document(uid, document=file_id)
        except Exception as e:
            await update.message.reply_text(f"⚠️ ဖိုင် မတွေ့ပါ သို့မဟုတ် ဆော်ရီ error ဖြစ်သည်: {e}")
        return

    # deeplink မပါရင် → welcome message
    await update.message.reply_text(
        "👋 မင်္ဂလာပါ!\n\n"
        "🤖 *Link Button Maker Bot*\n\n"
        "Deep Link များကို Channel Post Button အဖြစ် ဖန်တီးပေးသည်။\n\n"
        "📌 *Commands:*\n"
        "/post — Post တည်ဆောက်\n"
        "/history — Post မှတ်တမ်း\n"
        "/stats — စာရင်းအင်း\n"
        "/addadmin — Admin ထည့်\n"
        "/deladmin — Admin ဖျက်\n"
        "/listadmin — Admin စာရင်း\n"
        "/help — အကူအညီ\n"
        "/cancel — ပယ်ဖျက်",
        parse_mode="Markdown",
    )


# ── Build & run ───────────────────────────────────────────────────────────
def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


async def main():
    app = Application.builder().token(TOKEN).build()

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

    # File handler — Admin ပို့သမျှ file → deeplink ထုတ် (conversation မဟုတ်ရင်)
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO |
        filters.PHOTO | filters.VOICE | filters.VIDEO_NOTE,
        handle_file,
    ))

    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Bot စတင်ပါပြီ (MongoDB ချိတ်ပြီး)...")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
