import logging
import asyncio
import os
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

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable မသတ်မှတ်ရသေးပါ!")

async def main():
    application = Application.builder().token(BOT_TOKEN).build()

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

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("view", view_buttons))
    application.add_handler(CommandHandler("delete", delete_buttons))
    application.add_handler(CommandHandler("confirm_delete", confirm_delete))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("language", language_menu))
    application.add_handler(CommandHandler("reset", reset_script))
    application.add_handler(conv_handler)

    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_message))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO,
        handle_file
    ))

    logger.info("Bot စတင်မောင်းနှင်နေပါပြီ...")

    async with application:
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()
        await application.updater.stop()
        await application.stop()

if __name__ == "__main__":
    asyncio.run(main())
