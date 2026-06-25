import logging
import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from handlers import (
    start, help_command, new_buttons, receive_buttons, view_buttons,
    delete_buttons, confirm_delete, settings, language_menu,
    language_callback, cancel, callback_handler, reset_script,
    process_user_message, handle_file, deep_link_handler,
    WAITING_FOR_BUTTONS
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# config.py အစား environment variable ကနေ ဖတ်တယ်
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable မသတ်မှတ်ရသေးပါ!")

def main():
    """Bot ကိုစတင်မောင်းနှင်ရန်"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation Handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("new", new_buttons),
            CallbackQueryHandler(callback_handler, pattern="^new$"),
        ],
        states={
            WAITING_FOR_BUTTONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_buttons),
                CommandHandler("done", receive_buttons),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # /start — deep_link_handler ကို start handler ထဲ ပေါင်းထည့်ထားတယ်
    # (နှစ်ခါ register လုပ်လို့မရ၊ start handler ထဲမှာ deep link check လုပ်ပါ)
    application.add_handler(CommandHandler("start", start))

    # Command Handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("view", view_buttons))
    application.add_handler(CommandHandler("delete", delete_buttons))
    application.add_handler(CommandHandler("confirm_delete", confirm_delete))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("language", language_menu))
    application.add_handler(CommandHandler("reset", reset_script))
    application.add_handler(conv_handler)

    # Callback Query Handlers (specific pattern ကို အရင်ထည့်)
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Main Message Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_message))

    # File Handler
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO,
        handle_file
    ))

    logger.info("Bot စတင်မောင်းနှင်နေပါပြီ...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
