import os
import logging
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# تنظیم لاگ‌ها
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ۱. ساخت یک سرور وب بسیار سبک با Flask برای پاسخ به UptimeRobot
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ۲. توابع ربات تلگرام
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! ربات با موفقیت فعال شد و آماده کار است.")

def main():
    # روشن کردن سرور وب در یک ترد مجزا
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    # دریافت توکن ربات
    TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

    # ساخت و اجرای ربات تلگرام
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    logging.info("ربات در حال اجرا است...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
