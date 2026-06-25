# bot.py
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from config import BOT_TOKEN
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

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("view", view_buttons))
    application.add_handler(CommandHandler("delete", delete_buttons))
    application.add_handler(CommandHandler("confirm_delete", confirm_delete))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("language", language_menu))
    application.add_handler(CommandHandler("reset", reset_script))
    application.add_handler(conv_handler)

    # Deep Link Handler
    application.add_handler(CommandHandler("start", deep_link_handler))

    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))

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
