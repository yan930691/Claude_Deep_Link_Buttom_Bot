import os
import re
import logging
import hashlib
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# States
WAITING_FOR_BUTTONS = 1
WAITING_FOR_PHOTO = 2
POST_WAITING_PHOTO = 10
POST_WAITING_CAPTION = 11
POST_WAITING_CONFIRM = 12
POST_WAITING_FILES = 13  # ဖိုင်တွေ ပို့တဲ့ state

# ENV
ADMIN_IDS = set()
for _id in os.environ.get("ADMIN_ID", "").split(","):
    _id = _id.strip()
    if _id.isdigit():
        ADMIN_IDS.add(int(_id))

BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip().lstrip("@")
TELEGRAPH_TOKEN = os.environ.get("TELEGRAPH_TOKEN", "")

# Storage
session = {}       # {user_id: {photo, caption, links[]}}
pending_files = {} # {user_id: [{short_id, name}]}
file_store = {}    # {short_id: {file_id, file_type, name}}

def is_admin(user_id):
    return user_id in ADMIN_IDS

def make_short_id(file_id):
    return hashlib.md5(file_id.encode()).hexdigest()[:12]

def make_deep_link(short_id):
    return f"https://t.me/{BOT_USERNAME}?start={short_id}"

def clean_filename(name):
    name = re.sub(r'\.(mkv|mp4|avi|mov|wmv|flv|zip|rar)$', '', name, flags=re.IGNORECASE)
    # Series — S01EP19 → "S1 EP19 ရယူရန်"
    ep_match = re.search(r'S(\d+)\s*EP?(\d+)', name, re.IGNORECASE)
    if ep_match:
        s = int(ep_match.group(1))
        ep = int(ep_match.group(2))
        return f"S{s} EP{ep} ရယူရန်"
    # Movie — title နဲ့ ခုနှစ်ပဲ ယူ
    name = re.sub(r'\.(NF|WEB|WEBRip|WEB-DL|BluRay|HDTV|DVDRip|AMZN|DSNP|HULU|1080p|720p|480p|INTERNAL|REPACK|PROPER).*$', '', name, flags=re.IGNORECASE)
    year_match = re.search(r'^(.+?\d{4})', name)
    if year_match:
        title = year_match.group(1).replace('.', ' ').strip()
    else:
        title = name.replace('.', ' ').strip()
    return f"{title} ရယူရန်"

def sort_links(links):
    def sort_key(link):
        name = link["name"]
        m = re.search(r'S(\d+)\s*EP?(\d+)', name, re.IGNORECASE)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        m2 = re.search(r'EP?(\d+)', name, re.IGNORECASE)
        if m2:
            return (0, int(m2.group(1)))
        return (999, name)
    return sorted(links, key=sort_key)

def build_keyboard(links, extra_buttons=None):
    sorted_links = sort_links(links)
    keyboard = []
    row = []
    for link in sorted_links:
        row.append(InlineKeyboardButton(link["name"], url=link["url"]))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    if extra_buttons:
        for btn in extra_buttons:
            keyboard.append([btn])
    return keyboard

def init_session(user_id):
    session[user_id] = {"photo": None, "caption": "", "links": []}

async def create_telegraph_page(title, content):
    """Telegraph page တည်ဆောက်"""
    if not TELEGRAPH_TOKEN:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.telegra.ph/createPage",
                json={
                    "access_token": TELEGRAPH_TOKEN,
                    "title": title,
                    "content": [{"tag": "p", "children": [content]}],
                    "return_content": False
                }
            )
            data = resp.json()
            if data.get("ok"):
                return data["result"]["url"]
    except Exception as e:
        logger.error(f"Telegraph error: {e}")
    return None

# ==================== /start ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id

    if context.args:
        short_id = context.args[0]
        stored = file_store.get(short_id)
        if stored:
            caption = stored.get("name", "")
            try:
                if stored["file_type"] == "video":
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=stored["file_id"],
                        caption=caption
                    )
                elif stored["file_type"] == "audio":
                    await context.bot.send_audio(
                        chat_id=update.effective_chat.id,
                        audio=stored["file_id"],
                        caption=caption
                    )
                else:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=stored["file_id"],
                        caption=caption
                    )
            except Exception as e:
                logger.error(f"File send error: {e}")
                await update.message.reply_text("⚠️ ဖိုင် ပြန်ပို့တာ မအောင်မြင်ပါ။")
        else:
            await update.message.reply_text("⚠️ ဖိုင် မတွေ့ပါ။ Bot restart ဖြစ်သွားနိုင်တယ်။")
        return

    if is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("📝 Post တည်ဆောက်", callback_data="menu_post")],
            [InlineKeyboardButton("📋 Links ကြည့်", callback_data="menu_view"),
             InlineKeyboardButton("🗑 Links ဖျက်", callback_data="menu_delete")],
            [InlineKeyboardButton("🔄 Reset", callback_data="menu_reset")],
        ]
        await update.message.reply_text(
            "👑 *Admin Menu*\n\n"
            "📌 /post — Post တည်ဆောက်\n"
            "📌 ဖိုင်တိုင်း ပို့ → Deep link အလိုအလျောက်ထွက်\n"
            "/help — အကူအညီ",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("👋 မင်္ဂလာပါ!")

async def deep_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

# ==================== /post FLOW ====================

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = None
    if update.effective_user:
        user_id = update.effective_user.id
    if not user_id or not is_admin(user_id):
        if update.callback_query:
            await update.callback_query.answer("❌ Admin သာ အသုံးပြုနိုင်သည်။")
        else:
            await update.message.reply_text("❌ Admin သာ အသုံးပြုနိုင်သည်။")
        return ConversationHandler.END

    init_session(user_id)

    msg = "🖼 Post အတွက် *ပုံပို့ပါ*"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")
    return POST_WAITING_PHOTO

async def post_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return POST_WAITING_PHOTO
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("❌ ပုံပဲ ပို့ပါ။")
        return POST_WAITING_PHOTO
    session[user_id]["photo"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "📝 *ဇာတ်ညွှန်း ပို့ပါ*\n\n"
        "ကြိမ်ထပ် ပို့နိုင်တယ်။ ပြီးရင် /captdone ရိုက်ပါ။",
        parse_mode="Markdown"
    )
    return POST_WAITING_CAPTION

async def post_receive_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return POST_WAITING_CAPTION
    user_id = update.effective_user.id

    if update.message.text and update.message.text.startswith("/captdone"):
        caption = session[user_id].get("caption", "").strip()
        preview = caption if caption else "(ဇာတ်ညွှန်း မထည့်ထားပါ)"
        keyboard = [[InlineKeyboardButton("✅  a  — အတည်ပြု", callback_data="post_confirm_caption")]]
        # Preview ကို truncate လုပ်ပြ
        preview_show = preview[:500] + "..." if len(preview) > 500 else preview
        await update.message.reply_text(
            f"📋 *ဇာတ်ညွှန်း Preview:*\n\n{preview_show}\n\n'a' နှိပ်ပြီး အတည်ပြုပါ။",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return POST_WAITING_CONFIRM

    text = update.message.text or ""
    if session[user_id]["caption"]:
        session[user_id]["caption"] += "\n" + text
    else:
        session[user_id]["caption"] = text
    await update.message.reply_text("✅ ထည့်ပြီး။ ဆက်ပို့နိုင်တယ် ဒါမှမဟုတ် /captdone ရိုက်ပါ။")
    return POST_WAITING_CAPTION

async def post_confirm_and_wait_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'a' နှိပ်ပြီးနောက် ဖိုင်တွေ ပို့ဖို့ စောင့်"""
    if not update.effective_user:
        return POST_WAITING_FILES
    user_id = update.effective_user.id
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "✅ ဇာတ်ညွှန်း အတည်ပြုပြီ။\n\n"
        "🎬 *ဖိုင်တွေ ပို့ပါ*\n"
        "Bot က deep link အလိုအလျောက် ထုတ်ပြီး button ထည့်ပေးမယ်။\n\n"
        "ပြီးရင် /done ရိုက်ပါ။",
        parse_mode="Markdown"
    )
    return POST_WAITING_FILES

async def post_receive_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """POST_WAITING_FILES state မှာ ဖိုင်လက်ခံပြီး button ထည့်"""
    if not update.effective_user:
        return POST_WAITING_FILES
    user_id = update.effective_user.id

    # /done ဆိုရင် post ထုတ်
    if update.message and update.message.text and update.message.text.startswith("/done"):
        links = session.get(user_id, {}).get("links", [])
        if not links:
            await update.message.reply_text("⚠️ ဖိုင် တစ်ခုမှ မပို့ရသေးပါ။")
            return POST_WAITING_FILES

        photo = session[user_id]["photo"]
        caption = session[user_id]["caption"].strip()

        # Caption 1024 ထက်ကျော်ရင် Telegraph တင်
        extra_buttons = []
        if len(caption) > 1024:
            # Title ထုတ် (ပထမ line)
            title = caption.split("\n")[0][:100]
            telegraph_url = await create_telegraph_page(title, caption)
            caption_short = caption[:1020] + "..."
            if telegraph_url:
                extra_buttons.append(
                    InlineKeyboardButton("📖 ဇာတ်ညွှန်းအပြည့်အစုံဖတ်ရန်", url=telegraph_url)
                )
        else:
            caption_short = caption

        keyboard = build_keyboard(links, extra_buttons=extra_buttons)

        await update.message.reply_photo(
            photo=photo,
            caption=caption_short if caption_short else None,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.message.reply_text(
            f"✅ Post တည်ဆောက်ပြီး! Button {len(links)} ခု ပါတယ်။\n\n/post — Post အသစ်"
        )
        session.pop(user_id, None)
        return ConversationHandler.END

    # ဖိုင် ပို့လာရင် deep link ထုတ်ပြီး button ထည့်
    if update.message:
        file_id = None
        file_name = "file"
        file_type = "document"

        if update.message.document:
            file_id = update.message.document.file_id
            file_name = update.message.document.file_name or "file"
            file_type = "document"
        elif update.message.video:
            file_id = update.message.video.file_id
            file_name = update.message.video.file_name or "video.mp4"
            file_type = "video"
        elif update.message.audio:
            file_id = update.message.audio.file_id
            file_name = update.message.audio.file_name or "audio"
            file_type = "audio"
        elif update.message.text:
            await update.message.reply_text("💬 ဖိုင်ပို့ပါ ဒါမှမဟုတ် /done ရိုက်ပါ။")
            return POST_WAITING_FILES
        else:
            return POST_WAITING_FILES

        short_id = make_short_id(file_id)
        button_name = clean_filename(file_name)
        file_store[short_id] = {"file_id": file_id, "file_type": file_type, "name": button_name}
        deep_link = make_deep_link(short_id)

        # အလိုအလျောက် session ထဲ ထည့်
        session[user_id]["links"].append({"name": button_name, "url": deep_link})
        count = len(session[user_id]["links"])

        await update.message.reply_text(
            f"✅ [{count}] *{button_name}*\n"
            "ဖိုင်ထပ်ပို့နိုင်တယ် ဒါမှမဟုတ် /done ရိုက်ပြီး post ထုတ်ပါ။",
            parse_mode="Markdown"
        )
    return POST_WAITING_FILES

# ==================== FILE HANDLER (conversation ပြင်) ====================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if update.message.photo:
        await update.message.reply_text("ℹ️ ပုံ ရရှိပြီ။ Post တည်ဆောက်ဖို့ /post ရိုက်ပါ။")
        return

    file_id = None
    file_name = "file"
    file_type = "document"

    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name or "file"
        file_type = "document"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_name = update.message.video.file_name or "video.mp4"
        file_type = "video"
    elif update.message.audio:
        file_id = update.message.audio.file_id
        file_name = update.message.audio.file_name or "audio"
        file_type = "audio"
    else:
        await update.message.reply_text("📎 ဖိုင် မသိပါ။")
        return

    short_id = make_short_id(file_id)
    button_name = clean_filename(file_name)
    file_store[short_id] = {"file_id": file_id, "file_type": file_type, "name": button_name}
    deep_link = make_deep_link(short_id)

    if user_id not in pending_files:
        pending_files[user_id] = []
    pending_files[user_id].append({"short_id": short_id, "name": button_name})

    await update.message.reply_text(
        f"✅ *Deep Link ထွက်ပြီ!*\n\n"
        f"📁 `{file_name}`\n"
        f"🔘 {button_name}\n\n"
        f"🔗 သင်၏ Deep Link အဆင်သင့်ဖြစ်ပါပြီ။ {deep_link} {file_name}",
        parse_mode="Markdown"
    )

# ==================== OTHER COMMANDS ====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if is_admin(user_id):
        await update.message.reply_text(
            "📖 *Admin အသုံးပြုနည်း*\n\n"
            "*Post တည်ဆောက်နည်း (နည်းလမ်း ၂):*\n"
            "1️⃣ /post → ပုံပို့\n"
            "2️⃣ ဇာတ်ညွှန်းပို့ → /captdone\n"
            "3️⃣ 'a' နှိပ် confirm\n"
            "4️⃣ ဖိုင်တွေ ပို့ → Bot က deep link + button အလိုအလျောက်ထည့်\n"
            "5️⃣ /done → Post ထွက်\n\n"
            "🔹 Conversation ပြင်မှာ ဖိုင်ပို့ → Deep link သီးသန့်ထွက်မယ်\n\n"
            "*Commands:*\n"
            "/post — Post အသစ်\n"
            "/view — Links ကြည့်\n"
            "/delete — Link ဖျက်\n"
            "/reset — Reset\n"
            "/cancel — ပယ်ဖျက်",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("👋 မင်္ဂလာပါ!")

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
    keyboard = [
        [InlineKeyboardButton(f"🗑 {l['name']}", callback_data=f"del|{i}")]
        for i, l in enumerate(links)
    ]
    keyboard.append([InlineKeyboardButton("❌ မဖျက်တော့ဘူး", callback_data="cancel_delete")])
    await update.message.reply_text("ဘယ်ဟာ ဖျက်မလဲ?", reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    await update.message.reply_text("⚙️ /help ကြည့်ပါ။")

async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def new_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await post_command(update, context)

async def receive_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await post_receive_files(update, context)

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def process_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    await update.message.reply_text("💬 /post နဲ့ post တည်ဆောက်နိုင်တယ်။\n/help — အကူအညီ")

# ==================== CALLBACK HANDLER ====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "menu_post":
        pass

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
            keyboard = [
                [InlineKeyboardButton(f"🗑 {l['name']}", callback_data=f"del|{i}")]
                for i, l in enumerate(links)
            ]
            keyboard.append([InlineKeyboardButton("❌ မဖျက်တော့ဘူး", callback_data="cancel_delete")])
            await query.message.reply_text("ဘယ်ဟာ ဖျက်မလဲ?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_reset":
        session.pop(user_id, None)
        await query.edit_message_text("🔄 Reset ပြီး။ /post နဲ့ အသစ်စတင်နိုင်ပါပြီ။")

    elif data.startswith("add|"):
        try:
            idx = int(data.split("|")[1])
            files = pending_files.get(user_id, [])
            if 0 <= idx < len(files):
                f = files[idx]
                deep_link = make_deep_link(f["short_id"])
                if user_id not in session:
                    init_session(user_id)
                session[user_id]["links"].append({"name": f["name"], "url": deep_link})
                count = len(session[user_id]["links"])
                await query.edit_message_text(
                    f"✅ [{count}] *{f['name']}* ထည့်ပြီ။\n\n"
                    "/post — Post တည်ဆောက်\n/view — Links ကြည့်",
                    parse_mode="Markdown"
                )
        except (ValueError, IndexError):
            pass

    elif data.startswith("del|"):
        try:
            idx = int(data.split("|")[1])
            links = session.get(user_id, {}).get("links", [])
            if 0 <= idx < len(links):
                removed = links.pop(idx)
                await query.edit_message_text(
                    f"✅ *{removed['name']}* ဖျက်ပြီး။",
                    parse_mode="Markdown"
                )
        except (ValueError, IndexError):
            pass

    elif data == "cancel_delete":
        await query.edit_message_text("❌ ပယ်ဖျက်လိုက်ပြီ။")
