import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_BUTTONS = 1

# Language storage (user_id -> lang)
user_languages = {}

# Button storage (user_id -> list of {text, url})
user_buttons = {}

# ==================== LANGUAGE HELPERS ====================

def get_lang(user_id):
    return user_languages.get(user_id, "mm")

def t(user_id, mm_text, en_text):
    return mm_text if get_lang(user_id) == "mm" else en_text

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)

    # Deep link check
    if context.args:
        deep_link = context.args[0]
        await update.message.reply_text(
            t(user_id,
              f"🔗 Deep Link ရရှိပြီ: `{deep_link}`",
              f"🔗 Deep Link received: `{deep_link}`"),
            parse_mode="Markdown"
        )
        return

    keyboard = [
        [InlineKeyboardButton(t(user_id, "➕ Button အသစ်", "➕ New Button"), callback_data="new")],
        [InlineKeyboardButton(t(user_id, "📋 Button များကြည့်", "📋 View Buttons"), callback_data="view")],
        [InlineKeyboardButton(t(user_id, "🗑 Button ဖျက်", "🗑 Delete Button"), callback_data="delete")],
        [InlineKeyboardButton(t(user_id, "⚙️ ဆက်တင်", "⚙️ Settings"), callback_data="settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        t(user_id,
          "👋 မင်္ဂလာပါ!\nDeep Link Button Bot ထဲကို ကြိုဆိုပါတယ်။\nဘာလုပ်မလဲ?",
          "👋 Welcome to Deep Link Button Bot!\nWhat would you like to do?"),
        reply_markup=reply_markup
    )

async def deep_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This is handled inside start() above
    pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        t(user_id,
          "📖 *အသုံးပြုနည်း*\n\n"
          "/start - Bot စတင်\n"
          "/new - Button အသစ်ဆောက်\n"
          "/view - Button များကြည့်\n"
          "/delete - Button ဖျက်\n"
          "/settings - ဆက်တင်\n"
          "/language - ဘာသာစကားပြောင်း\n"
          "/reset - အားလုံး reset\n"
          "/cancel - ပယ်ဖျက်",
          "📖 *Commands*\n\n"
          "/start - Start bot\n"
          "/new - Create new button\n"
          "/view - View buttons\n"
          "/delete - Delete button\n"
          "/settings - Settings\n"
          "/language - Change language\n"
          "/reset - Reset all\n"
          "/cancel - Cancel"),
        parse_mode="Markdown"
    )

# ==================== NEW BUTTON FLOW ====================

async def new_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        t(user_id,
          "➕ Button အသစ်ဆောက်မယ်။\n\nFormat: `Button စာသား | https://link.com`\nပြီးရင် /done လိုက်ရိုက်ပါ။",
          "➕ Create new button.\n\nFormat: `Button text | https://link.com`\nType /done when finished."),
        parse_mode="Markdown"
    )
    return WAITING_FOR_BUTTONS

async def receive_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if update.message.text == "/done":
        buttons = user_buttons.get(user_id, [])
        if not buttons:
            await update.message.reply_text(
                t(user_id, "⚠️ Button တစ်ခုမှ မရှိသေးပါ။", "⚠️ No buttons added yet.")
            )
            return WAITING_FOR_BUTTONS

        # Build inline keyboard
        keyboard = []
        for btn in buttons:
            keyboard.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            t(user_id, "✅ Button များ တည်ဆောက်ပြီးပါပြီ:", "✅ Buttons created:"),
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    # Parse input
    text = update.message.text
    if "|" not in text:
        await update.message.reply_text(
            t(user_id,
              "❌ Format မှားနေတယ်။ `Button နာမည် | https://link.com` အနေနဲ့ ရိုက်ပါ။",
              "❌ Wrong format. Please use `Button name | https://link.com`"),
            parse_mode="Markdown"
        )
        return WAITING_FOR_BUTTONS

    parts = text.split("|", 1)
    btn_text = parts[0].strip()
    btn_url = parts[1].strip()

    if not btn_url.startswith("http"):
        await update.message.reply_text(
            t(user_id, "❌ URL မှားနေတယ်။ https:// နဲ့ စရမယ်။", "❌ Invalid URL. Must start with https://")
        )
        return WAITING_FOR_BUTTONS

    if user_id not in user_buttons:
        user_buttons[user_id] = []
    user_buttons[user_id].append({"text": btn_text, "url": btn_url})

    await update.message.reply_text(
        t(user_id,
          f"✅ `{btn_text}` ထည့်ပြီးပါပြီ။ ထပ်ထည့်နိုင်တယ် ဒါမှမဟုတ် /done ရိုက်ပါ။",
          f"✅ `{btn_text}` added. Add more or type /done."),
        parse_mode="Markdown"
    )
    return WAITING_FOR_BUTTONS

# ==================== VIEW / DELETE ====================

async def view_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    buttons = user_buttons.get(user_id, [])

    if not buttons:
        await update.message.reply_text(
            t(user_id, "📋 Button မရှိသေးပါ။", "📋 No buttons yet.")
        )
        return

    keyboard = [[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        t(user_id, "📋 မင်းရဲ့ Button များ:", "📋 Your buttons:"),
        reply_markup=reply_markup
    )

async def delete_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    buttons = user_buttons.get(user_id, [])

    if not buttons:
        await update.message.reply_text(
            t(user_id, "🗑 ဖျက်စရာ Button မရှိပါ။", "🗑 No buttons to delete.")
        )
        return

    keyboard = []
    for i, btn in enumerate(buttons):
        keyboard.append([InlineKeyboardButton(f"🗑 {btn['text']}", callback_data=f"del_{i}")])
    keyboard.append([InlineKeyboardButton(t(user_id, "❌ မဖျက်တော့ဘူး", "❌ Cancel"), callback_data="cancel_delete")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        t(user_id, "ဘယ် Button ဖျက်မလဲ?", "Which button to delete?"),
        reply_markup=reply_markup
    )

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        try:
            idx = int(context.args[0])
            buttons = user_buttons.get(user_id, [])
            if 0 <= idx < len(buttons):
                removed = buttons.pop(idx)
                await update.message.reply_text(
                    t(user_id, f"✅ `{removed['text']}` ဖျက်ပြီးပါပြီ။", f"✅ `{removed['text']}` deleted."),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(t(user_id, "❌ မတွေ့ပါ။", "❌ Not found."))
        except ValueError:
            await update.message.reply_text(t(user_id, "❌ မှားနေတယ်။", "❌ Invalid."))

# ==================== SETTINGS / LANGUAGE ====================

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton(t(user_id, "🌐 ဘာသာစကားပြောင်း", "🌐 Change Language"), callback_data="language")],
        [InlineKeyboardButton(t(user_id, "🔄 Reset လုပ်", "🔄 Reset All"), callback_data="reset")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        t(user_id, "⚙️ ဆက်တင်", "⚙️ Settings"),
        reply_markup=reply_markup
    )

async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("🇲🇲 မြန်မာ", callback_data="lang_mm")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        t(user_id, "🌐 ဘာသာစကားရွေးပါ:", "🌐 Select language:"),
        reply_markup=reply_markup
    )

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = query.data.replace("lang_", "")
    user_languages[user_id] = lang

    if lang == "mm":
        await query.edit_message_text("✅ ဘာသာစကား မြန်မာ သို့ ပြောင်းပြီးပါပြီ။")
    else:
        await query.edit_message_text("✅ Language changed to English.")

async def reset_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_buttons.pop(user_id, None)
    await update.message.reply_text(
        t(user_id, "🔄 Button အားလုံး reset ပြီးပါပြီ။", "🔄 All buttons have been reset.")
    )

# ==================== CANCEL ====================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        t(user_id, "❌ ပယ်ဖျက်လိုက်ပါပြီ။", "❌ Cancelled.")
    )
    return ConversationHandler.END

# ==================== CALLBACK HANDLER ====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "new":
        await query.message.reply_text(
            t(user_id,
              "➕ Button အသစ်ဆောက်မယ်။\n\nFormat: `Button စာသား | https://link.com`\nပြီးရင် /done လိုက်ရိုက်ပါ။",
              "➕ Create new button.\n\nFormat: `Button text | https://link.com`\nType /done when finished."),
            parse_mode="Markdown"
        )

    elif data == "view":
        buttons = user_buttons.get(user_id, [])
        if not buttons:
            await query.message.reply_text(t(user_id, "📋 Button မရှိသေးပါ။", "📋 No buttons yet."))
        else:
            keyboard = [[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                t(user_id, "📋 မင်းရဲ့ Button များ:", "📋 Your buttons:"),
                reply_markup=reply_markup
            )

    elif data == "delete":
        buttons = user_buttons.get(user_id, [])
        if not buttons:
            await query.message.reply_text(t(user_id, "🗑 ဖျက်စရာ Button မရှိပါ။", "🗑 No buttons to delete."))
        else:
            keyboard = []
            for i, btn in enumerate(buttons):
                keyboard.append([InlineKeyboardButton(f"🗑 {btn['text']}", callback_data=f"del_{i}")])
            keyboard.append([InlineKeyboardButton(t(user_id, "❌ မဖျက်တော့ဘူး", "❌ Cancel"), callback_data="cancel_delete")])
            await query.message.reply_text(
                t(user_id, "ဘယ် Button ဖျက်မလဲ?", "Which button to delete?"),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data.startswith("del_"):
        try:
            idx = int(data.replace("del_", ""))
            buttons = user_buttons.get(user_id, [])
            if 0 <= idx < len(buttons):
                removed = buttons.pop(idx)
                await query.edit_message_text(
                    t(user_id, f"✅ `{removed['text']}` ဖျက်ပြီးပါပြီ။", f"✅ `{removed['text']}` deleted."),
                    parse_mode="Markdown"
                )
        except (ValueError, IndexError):
            await query.edit_message_text(t(user_id, "❌ မှားနေတယ်။", "❌ Error."))

    elif data == "cancel_delete":
        await query.edit_message_text(t(user_id, "❌ ပယ်ဖျက်လိုက်ပါပြီ။", "❌ Cancelled."))

    elif data == "settings":
        keyboard = [
            [InlineKeyboardButton(t(user_id, "🌐 ဘာသာစကားပြောင်း", "🌐 Change Language"), callback_data="language")],
            [InlineKeyboardButton(t(user_id, "🔄 Reset လုပ်", "🔄 Reset All"), callback_data="reset")],
        ]
        await query.edit_message_text(
            t(user_id, "⚙️ ဆက်တင်", "⚙️ Settings"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "language":
        keyboard = [
            [InlineKeyboardButton("🇲🇲 မြန်မာ", callback_data="lang_mm")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        ]
        await query.edit_message_text(
            t(user_id, "🌐 ဘာသာစကားရွေးပါ:", "🌐 Select language:"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "reset":
        user_buttons.pop(user_id, None)
        await query.edit_message_text(
            t(user_id, "🔄 Button အားလုံး reset ပြီးပါပြီ။", "🔄 All buttons have been reset.")
        )

# ==================== MESSAGE / FILE HANDLERS ====================

async def process_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        t(user_id,
          "💬 Command တစ်ခု ရွေးပါ။ /help နဲ့ အသုံးပြုနည်းကြည့်နိုင်တယ်။",
          "💬 Please use a command. Type /help to see available commands.")
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        t(user_id,
          "📎 ဖိုင်ရရှိပြီ။ ဒီ bot မှာ ဖိုင်လက်ခံမှု support မပါသေးပါ။",
          "📎 File received. File handling is not supported in this bot yet.")
    )
