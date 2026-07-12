import os
import logging
from telegram.ext import ApplicationBuilder
from handlers import setup_handlers  # Giả định bạn có hàm này trong handlers.py

# Cấu hình log
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def main():
    # Lấy Token từ biến môi trường trên Render (bảo mật hơn)[span_3](start_span)[span_3](end_span)
    token = os.environ.get("BOT_TOKEN")
    
    if not token:
        print("Lỗi: Chưa thiết lập biến môi trường BOT_TOKEN trên Render!")
        return

    # Khởi tạo ứng dụng bot[span_4](start_span)[span_4](end_span)
    application = ApplicationBuilder().token(token).build()

    # Thiết lập các lệnh và xử lý từ tệp handlers.py
    setup_handlers(application)

    print("Bot đang khởi chạy...")
    application.run_polling()

if __name__ == '__main__':
    main()
