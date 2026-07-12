import os
import logging
from telegram.ext import ApplicationBuilder, JobQueue
from handlers import button_handler, cmd_start, handle_text_input, error_handler, cmd_loginlink, cmd_tv, cmd_reload, cmd_addluot, cmd_addcode, cmd_ref, cmd_msg, cmd_notify
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

# Cấu hình log
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("NetflixBot")

def main():
    # Lấy Token từ biến môi trường trên Render
    token = os.environ.get("BOT_TOKEN")
    
    if not token:
        logger.error("Lỗi: Chưa thiết lập BOT_TOKEN trên Render!")
        return

    # Khởi tạo ứng dụng bot
    application = ApplicationBuilder().token(token).build()

    # Đăng ký các Command Handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("loginlink", cmd_loginlink))
    application.add_handler(CommandHandler("tv", cmd_tv))
    application.add_handler(CommandHandler("reload", cmd_reload))
    application.add_handler(CommandHandler("addluot", cmd_addluot))
    application.add_handler(CommandHandler("addcode", cmd_addcode))
    application.add_handler(CommandHandler("ref", cmd_ref))
    application.add_handler(CommandHandler("msg", cmd_msg))
    application.add_handler(CommandHandler("notify", cmd_notify))

    # Đăng ký các Callback & Message Handlers
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Đăng ký error handler
    application.add_error_handler(error_handler)

    logger.info("Bot đang khởi chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()

