import os
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

WAITING_FOR_BUTTONS = 1
WAITING_FOR_PHOTO = 2

ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# Session storage
# {admin_id: {"links": [...], "photo": file_id}}
session = {}

def is_admin(user_id):
    return user_id == ADMIN_ID

def parse_deep_link(text):
    """
    Input:  "🔗 သင်၏ Deep Link အဆင်သင့်ဖြစ်ပါပြီ။ https://t.me/bot?start=xxx filename.mp4"
    Output: {"name": "filename", "url": "https://t.me/bot?start=xxx"}
    """
    # URL ထုတ်
    url_match = re.search(r'(https://t\.me/\S+)', text)
    if not url_match:
        return None
    url = url_match.group(1)

    # Filename ထုတ် (URL ပြီးနောက်မှာ)
    after_url = text[url_match.end():].strip()
    if after_url:
        # Extension ဖြုတ်
        filename = re.sub(r'\.\w{2,4}$', '', after_url)
        # Episode နဲ့ title ပဲ ယူ (49.Days.2011.S01EP19 -> 49.Days.2011.S01EP19)
        name = filename.strip()
    else:
        name = url.split("start=")[-1] if "start=" in url else "File"

    return {"name": name, "url": url}

# ==================== START ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if context.args:
        deep_link = context.args[0]
        await update.message.reply_text(f"🔗 Deep Link: `{deep_link}`", parse_mode="Markdown")
        return
    if is_admin(user_id):
        await update.message.reply_text(
            "👋 Admin မင်္ဂလာပါ!\n\n"
            "📌 အသုံးပြုနည်း:\n"
            "1️⃣ Deep link တွေ ပို့ပါ (တစ်ခုချင်း ဒါမှမဟုတ် တစ်ဆက်တည်း)\n"
            "2️⃣ /done ရိုက်ပြီး ပုံပို့ပါ\n"
            "3️⃣ Bot က post တည်ဆောက်ပေးမယ်\n\n"
            "/reset - အားလုံး ပယ်ဖျက်"
        )
    else:
        await update.message.reply_text("👋 မင်္ဂလာပါ!")

async def deep_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

# ==================== ADMIN: RECEIVE DEEP LINKS ====================

async def process_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin သာ အသုံးပြုနိုင်သည်။")
        return

    text = update.message.text

    # Deep link message ဖြစ်လျှင်
    if "t.me/" in text:
        parsed = parse_deep_link(text)
        if not parsed:
            await update.message.reply_text("⚠️ Deep link မတွေ့ပါ။")
            return

        if user_id not in session:
            session[user_id] = {"links": [], "photo": None}

        session[user_id]["links"].append(parsed)
        count = len(session[user_id]["links"])
        await update.message.reply_text(
            f"✅ [{count}] `{parsed['name']}` ထည့်ပြီး\n"
            f"🔗 {parsed['url']}\n\n"
            f"ထပ်ပို့နိုင်တယ် ဒါမှမဟုတ် /done ရိုက်ပြီး ပုံပို့ပါ။",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "💬 Deep link ပို့ပါ ဒါမှမဟုတ် /done ရိုက်ပြီး ပုံပို့ပါ။\n/reset - အားလုံးပယ်ဖျက်"
        )

# ==================== ADMIN: /done → WAITING FOR PHOTO ====================

async def new_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /new command — manual button add (optional flow)
    """
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    await update.message.reply_text(
        "➕ Format: `Button နာမည် | https://link.com`\nပြီးရင် /done ရိုက်ပါ။",
        parse_mode="Markdown"
    )
    return WAITING_FOR_BUTTONS

async def receive_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    # /done ဆိုရင် photo ခံရမယ်
    if update.message.text and update.message.text.startswith("/done"):
        links = session.get(user_id, {}).get("links", [])
        if not links:
            await update.message.reply_text("⚠️ Deep link တစ်ခုမှ မရှိသေးပါ။")
            return ConversationHandler.END
        await update.message.reply_text(
            f"✅ {len(links)} ခု ရပြီ။\nအခု ပုံပို့ပါ။ (Post cover image)"
        )
        return WAITING_FOR_PHOTO

    text = update.message.text
    if "|" not in text:
        await update.message.reply_text("❌ Format: `Button နာမည် | https://link.com`", parse_mode="Markdown")
        return WAITING_FOR_BUTTONS

    parts = text.split("|", 1)
    btn_text = parts[0].strip()
    btn_url = parts[1].strip()
    if not btn_url.startswith("http"):
        await update.message.reply_text("❌ URL မှားနေတယ်။ https:// နဲ့ စရမယ်။")
        return WAITING_FOR_BUTTONS

    if user_id not in session:
        session[user_id] = {"links": [], "photo": None}
    session[user_id]["links"].append({"name": btn_text, "url": btn_url})
    count = len(session[user_id]["links"])
    await update.message.reply_text(
        f"✅ [{count}] `{btn_text}` ထည့်ပြီး။ ထပ်ထည့်နိုင်တယ် ဒါမှမဟုတ် /done ရိုက်ပါ။",
        parse_mode="Markdown"
    )
    return WAITING_FOR_BUTTONS

# ==================== ADMIN: RECEIVE PHOTO → BUILD POST ====================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    links = session.get(user_id, {}).get("links", [])

    # Photo ဆိုရင် post တည်ဆောက်
    if update.message.photo:
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""

        if not links:
            await update.message.reply_text("⚠️ Deep link မရှိသေးပါ။ အရင် deep link ပို့ပါ။")
            return

        # Button တွေ တည်ဆောက် (တစ်ကြောင်းကို ၂ ခု စီ)
        keyboard = []
        row = []
        for i, link in enumerate(links):
            btn = InlineKeyboardButton(link["name"], url=link["url"])
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_photo(
            photo=photo,
            caption=caption if caption else None,
            reply_markup=reply_markup
        )

        await update.message.reply_text(
            f"✅ Post တည်ဆောက်ပြီး! Button {len(links)} ခု ပါတယ်။\n/reset - အသစ်စတင်"
        )

        # Session clear
        session.pop(user_id, None)
        return

    # Video/Document ဆိုရင် deep link ထုတ်ပေး
    file_name = ""
    if update.message.document:
        file_name = update.message.document.file_name or "file"
    elif update.message.video:
        file_name = update.message.video.file_name or "video"
    elif update.message.audio:
        file_name = update.message.audio.file_name or "audio"
    else:
        file_name = "file"

    await update.message.reply_text(
        f"📎 ဖိုင်ရရှိပြီ: `{file_name}`\n\n"
        "⚠️ Deep link ထုတ်ဖို့ မင်းရဲ့ file sender bot ကနေ deep link ကို ဒီ bot ဆီ ပို့ပေးပါ။",
        parse_mode="Markdown"
    )

# ==================== /done COMMAND (outside conversation) ====================

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    links = session.get(user_id, {}).get("links", [])
    if not links:
        await update.message.reply_text("⚠️ Deep link တစ်ခုမှ မရှိသေးပါ။")
        return
    await update.message.reply_text(
        f"✅ {len(links)} ခု ရပြီ။\nအခု ပုံပို့ပါ။ (Post cover image)"
    )

# ==================== OTHER COMMANDS ====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    await update.message.reply_text(
        "📖 *အသုံးပြုနည်း*\n\n"
        "1️⃣ File sender bot က deep link တွေ ဒီ bot ဆီ ပို့\n"
        "2️⃣ /done ရိုက်ပြီး ပုံပို့\n"
        "3️⃣ Bot က button တွေနဲ့ post ထုတ်ပေးမယ်\n\n"
        "/reset - အားလုံးပယ်ဖျက်",
        parse_mode="Markdown"
    )

async def view_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    links = session.get(user_id, {}).get("links", [])
    if not links:
        await update.message.reply_text("📋 Deep link မရှိသေးပါ။")
        return
    text = "📋 *လက်ရှိ links:*\n\n"
    for i, link in enumerate(links, 1):
        text += f"{i}. `{link['name']}`\n{link['url']}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def delete_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    links = session.get(user_id, {}).get("links", [])
    if not links:
        await update.message.reply_text("🗑 ဖျက်စရာ မရှိပါ။")
        return
    keyboard = [[InlineKeyboardButton(f"🗑 {l['name']}", callback_data=f"del_{i}")] for i, l in enumerate(links)]
    keyboard.append([InlineKeyboardButton("❌ မဖျက်တော့ဘူး", callback_data="cancel_delete")])
    await update.message.reply_text("ဘယ်ဟာ ဖျက်မလဲ?", reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    await update.message.reply_text("⚙️ Setting မရှိသေးပါ။")

async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    await update.message.reply_text("🌐 Language setting မရှိသေးပါ။")

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def reset_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    session.pop(user_id, None)
    await update.message.reply_text("🔄 အားလုံး reset ပြီး။ အသစ်စတင်နိုင်ပါပြီ။")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    await update.message.reply_text("❌ ပယ်ဖျက်လိုက်ပြီ။")
    return ConversationHandler.END

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("del_"):
        try:
            idx = int(data.replace("del_", ""))
            links = session.get(user_id, {}).get("links", [])
            if 0 <= idx < len(links):
                removed = links.pop(idx)
                await query.edit_message_text(f"✅ `{removed['name']}` ဖျက်ပြီး။", parse_mode="Markdown")
        except (ValueError, IndexError):
            pass
    elif data == "cancel_delete":
        await query.edit_message_text("❌ ပယ်ဖျက်လိုက်ပြီ။")
