import os
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# States
WAITING_FOR_BUTTONS = 1
WAITING_FOR_PHOTO = 2
POST_WAITING_PHOTO = 10
POST_WAITING_CAPTION = 11
POST_WAITING_CONFIRM = 12
POST_WAITING_LINKS = 13

ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# Session: {user_id: {photo, caption, links: []}}
session = {}

def is_admin(user_id):
    return user_id == ADMIN_ID

def parse_deep_link(text):
    url_match = re.search(r'(https://t\.me/\S+)', text)
    if not url_match:
        return None
    url = url_match.group(1)
    after_url = text[url_match.end():].strip()
    if after_url:
        # Extension ဖြုတ်၊ quality tag တွေဖြုတ် (NF.WEB-DL1080p စသည်)
        filename = re.sub(r'\.(mkv|mp4|avi|mov|wmv|flv)$', '', after_url, flags=re.IGNORECASE)
        # S01EP19 အထိပဲ ယူ
        ep_match = re.search(r'^(.+?S\d+EP?\d+)', filename, re.IGNORECASE)
        if ep_match:
            name = ep_match.group(1).replace('.', ' ').strip()
        else:
            name = filename.replace('.', ' ').strip()
    else:
        name = "File"
    return {"name": name, "url": url}

def build_keyboard(links):
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
    return keyboard

# ===================== /start =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if context.args:
        await update.message.reply_text(f"🔗 Deep Link: `{context.args[0]}`", parse_mode="Markdown")
        return
    if is_admin(user_id):
        await show_admin_menu(update)
    else:
        await update.message.reply_text("👋 မင်္ဂလာပါ!")

async def deep_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def show_admin_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("📝 Post တည်ဆောက်", callback_data="menu_post")],
        [InlineKeyboardButton("📋 Links ကြည့်", callback_data="menu_view"),
         InlineKeyboardButton("🗑 Links ဖျက်", callback_data="menu_delete")],
        [InlineKeyboardButton("🔄 Reset", callback_data="menu_reset")],
    ]
    await update.message.reply_text(
        "👑 *Admin Menu*\n\nဘာလုပ်မလဲ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ===================== /post FLOW =====================

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Admin သာ အသုံးပြုနိုင်သည်။")
        return
    session[user_id] = {"photo": None, "caption": "", "links": []}
    await update.message.reply_text("🖼 Post အတွက် *ပုံပို့ပါ*", parse_mode="Markdown")
    return POST_WAITING_PHOTO

async def post_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("❌ ပုံပဲ ပို့ပါ။")
        return POST_WAITING_PHOTO
    session[user_id]["photo"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "📝 *ဇာတ်ညွှန်း (Caption) ပို့ပါ*\n\nများများပို့နိုင်တယ်။ ပြီးရင် /captdone ရိုက်ပါ။",
        parse_mode="Markdown"
    )
    return POST_WAITING_CAPTION

async def post_receive_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id

    if update.message.text and update.message.text == "/captdone":
        caption = session[user_id].get("caption", "")
        keyboard = [[InlineKeyboardButton("✅ a - ဇာတ်ညွှန်း အတည်ပြု", callback_data="post_confirm_caption")]]
        await update.message.reply_text(
            f"📋 *ဇာတ်ညွှန်း:*\n\n{caption}\n\n'a' နှိပ်၍ အတည်ပြုပါ။",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return POST_WAITING_CONFIRM

    # Caption ထည့်
    text = update.message.text or ""
    if session[user_id]["caption"]:
        session[user_id]["caption"] += "\n" + text
    else:
        session[user_id]["caption"] = text
    await update.message.reply_text("✅ ထည့်ပြီး။ ဆက်ပို့နိုင်တယ် ဒါမှမဟုတ် /captdone ရိုက်ပါ။")
    return POST_WAITING_CAPTION

async def post_receive_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id

    if update.message.text and update.message.text == "/done":
        links = session.get(user_id, {}).get("links", [])
        if not links:
            await update.message.reply_text("⚠️ Link တစ်ခုမှ မရှိသေးပါ။")
            return POST_WAITING_LINKS

        # Post တည်ဆောက်
        photo = session[user_id]["photo"]
        caption = session[user_id]["caption"]
        keyboard = build_keyboard(links)

        sent = await update.message.reply_photo(
            photo=photo,
            caption=caption if caption else None,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.message.reply_text(
            f"✅ Post တည်ဆောက်ပြီး!\n🔘 Button {len(links)} ခု ပါတယ်။\n\n/post - Post အသစ်\n/reset - Reset",
        )
        session.pop(user_id, None)
        return ConversationHandler.END

    text = update.message.text or ""
    if "t.me/" in text:
        parsed = parse_deep_link(text)
        if parsed:
            session[user_id]["links"].append(parsed)
            count = len(session[user_id]["links"])
            await update.message.reply_text(
                f"✅ [{count}] *{parsed['name']}*\n🔗 {parsed['url']}\n\nထပ်ပို့နိုင်တယ် ဒါမှမဟုတ် /done ရိုက်ပါ။",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ Deep link မတွေ့ပါ။")
    else:
        await update.message.reply_text(
            "💬 Deep link ပို့ပါ ဒါမှမဟုတ် /done ရိုက်ပြီး post ထုတ်ပါ။"
        )
    return POST_WAITING_LINKS

# ===================== OTHER COMMANDS =====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if is_admin(user_id):
        await update.message.reply_text(
            "📖 *Admin Commands*\n\n"
            "/post - Post အသစ်တည်ဆောက်\n"
            "/view - Link များကြည့်\n"
            "/delete - Link ဖျက်\n"
            "/reset - အားလုံး reset\n"
            "/cancel - ပယ်ဖျက်\n\n"
            "📌 ဖိုင်တိုင်း ပို့ရင် deep link အလိုအလျောက် ထုတ်ပေးမယ်",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("👋 မင်္ဂလာပါ!")

async def new_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await post_command(update, context)

async def receive_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await post_receive_links(update, context)

async def view_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    links = session.get(user_id, {}).get("links", [])
    if not links:
        await update.message.reply_text("📋 Link မရှိသေးပါ။")
        return
    text = "📋 *လက်ရှိ Links:*\n\n"
    for i, link in enumerate(links, 1):
        text += f"{i}. *{link['name']}*\n{link['url']}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def delete_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
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
    await show_admin_menu(update)

async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def reset_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    session.pop(user_id, None)
    await update.message.reply_text("🔄 Reset ပြီး။ /post နဲ့ အသစ်စတင်နိုင်ပါပြီ။")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    session.pop(user_id, None)
    await update.message.reply_text("❌ ပယ်ဖျက်လိုက်ပြီ။")
    return ConversationHandler.END

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    links = session.get(user_id, {}).get("links", [])
    if not links:
        await update.message.reply_text("⚠️ Link မရှိသေးပါ။")
        return
    await update.message.reply_text(f"✅ Link {len(links)} ခု ရပြီ။")

# ===================== FILE HANDLER (any file → deep link) =====================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    file_name = ""
    file_id = ""
    if update.message.document:
        file_name = update.message.document.file_name or "file"
        file_id = update.message.document.file_id
    elif update.message.video:
        file_name = update.message.video.file_name or "video.mp4"
        file_id = update.message.video.file_id
    elif update.message.audio:
        file_name = update.message.audio.file_name or "audio"
        file_id = update.message.audio.file_id
    else:
        await update.message.reply_text("📎 ဖိုင် မသိပါ။")
        return

    await update.message.reply_text(
        f"📎 ဖိုင်ရရှိပြီ: `{file_name}`\n\n"
        f"🆔 File ID: `{file_id}`\n\n"
        "⚠️ Deep link ထုတ်ဖို့ file sender bot ကနေ deep link ဒီ bot ဆီ ပို့ပေးပါ။",
        parse_mode="Markdown"
    )

# ===================== MESSAGE HANDLER =====================

async def process_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    await update.message.reply_text(
        "💬 /post နဲ့ post တည်ဆောက်နိုင်တယ်။\n/help - အကူအညီ"
    )

# ===================== CALLBACK HANDLER =====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "menu_post":
        if user_id not in session:
            session[user_id] = {"photo": None, "caption": "", "links": []}
        else:
            session[user_id] = {"photo": None, "caption": "", "links": []}
        await query.message.reply_text("🖼 Post အတွက် *ပုံပို့ပါ*", parse_mode="Markdown")
        context.user_data["state"] = POST_WAITING_PHOTO

    elif data == "menu_view":
        links = session.get(user_id, {}).get("links", [])
        if not links:
            await query.message.reply_text("📋 Link မရှိသေးပါ။")
        else:
            text = "📋 *လက်ရှိ Links:*\n\n"
            for i, link in enumerate(links, 1):
                text += f"{i}. *{link['name']}*\n{link['url']}\n\n"
            await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "menu_delete":
        links = session.get(user_id, {}).get("links", [])
        if not links:
            await query.message.reply_text("🗑 ဖျက်စရာ မရှိပါ။")
        else:
            keyboard = [[InlineKeyboardButton(f"🗑 {l['name']}", callback_data=f"del_{i}")] for i, l in enumerate(links)]
            keyboard.append([InlineKeyboardButton("❌ မဖျက်တော့ဘူး", callback_data="cancel_delete")])
            await query.message.reply_text("ဘယ်ဟာ ဖျက်မလဲ?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_reset":
        session.pop(user_id, None)
        await query.edit_message_text("🔄 Reset ပြီး။")

    elif data == "post_confirm_caption":
        await query.edit_message_text(
            "✅ ဇာတ်ညွှန်း အတည်ပြုပြီ။\n\n🔗 Deep link တွေ ပို့ပါ။\nပြီးရင် /done ရိုက်ပါ။"
        )
        if user_id not in session:
            session[user_id] = {"photo": None, "caption": "", "links": []}
        context.user_data["state"] = POST_WAITING_LINKS

    elif data.startswith("del_"):
        try:
            idx = int(data.replace("del_", ""))
            links = session.get(user_id, {}).get("links", [])
            if 0 <= idx < len(links):
                removed = links.pop(idx)
                await query.edit_message_text(f"✅ *{removed['name']}* ဖျက်ပြီး။", parse_mode="Markdown")
        except (ValueError, IndexError):
            pass

    elif data == "cancel_delete":
        await query.edit_message_text("❌ ပယ်ဖျက်လိုက်ပြီ။")
