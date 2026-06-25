import logging
import asyncio
import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from handlers import (
    start, help_command, post_command, post_receive_photo, post_receive_caption,
    post_receive_links, view_buttons, delete_buttons, confirm_delete,
    settings, language_menu, language_callback, cancel, callback_handler,
    reset_script, process_user_message, handle_file, deep_link_handler,
    done_command, new_buttons, receive_buttons,
    WAITING_FOR_BUTTONS, WAITING_FOR_PHOTO,
    POST_WAITING_PHOTO, POST_WAITING_CAPTION, POST_WAITING_CONFIRM, POST_WAITING_LINKS
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN မသတ်မှတ်ရသေးပါ!")

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Bot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

async def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()

    # /post conversation flow
    post_handler = ConversationHandler(
        entry_points=[
            CommandHandler("post", post_command),
        ],
        states={
            POST_WAITING_PHOTO: [
                MessageHandler(filters.PHOTO, post_receive_photo),
            ],
            POST_WAITING_CAPTION: [
                CommandHandler("captdone", post_receive_caption),
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_caption),
            ],
            POST_WAITING_CONFIRM: [
                CallbackQueryHandler(callback_handler, pattern="^post_confirm_caption$"),
            ],
            POST_WAITING_LINKS: [
                CommandHandler("done", post_receive_links),
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_links),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("view", view_buttons))
    application.add_handler(CommandHandler("delete", delete_buttons))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("reset", reset_script))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(post_handler)

    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_message))
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.ALL | filters.VIDEO | filters.AUDIO,
        handle_file
    ))

    logger.info("Bot စတင်မောင်းနှင်နေပါပြီ...")

    async with application:
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    asyncio.run(run_bot())
