import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# تنظیمات ثبت لوگ‌ها
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# توابع پاسخگویی به دستورات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_user.first_name
    await update.message.reply_text(
        f"سلام {user_first_name} عزیز!\n"
        "به ربات خوش آمدید. ربات با موفقیت روی سرور آنلاین شد."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("این یک ربات نمونه است که به‌روزرسانی شده است.")

def main():
    # دریافت توکن از متغیرهای محیطی Render یا قرار دادن مستقیم توکن
    TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

    # ساخت برنامه با ساختار جدید async
    application = ApplicationBuilder().token(TOKEN).build()

    # ثبت دستورات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # اجرای ربات با مدیریت استاندارد حلقه رویدادها (Event Loop)
    logging.info("ربات روشن شد و آماده دریافت پیام است...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
