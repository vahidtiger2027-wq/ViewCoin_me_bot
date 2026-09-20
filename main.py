import os
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# دریافت مقادیر حساس از Variableهای Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")  # آدرس اتوماتیک رندر

# ساخت اپلیکیشن Flask جهت پینگ و وب‌هوک
app = Flask(__name__)

# تعریف ساختار ربات تلگرام
ptb_app = Application.builder().token(BOT_TOKEN).build()

# ----------------- هندلرهای تلگرام -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیام خوش‌آمدگویی و منوی اصلی"""
    user_name = update.effective_user.first_name
    
    keyboard = [
        [InlineKeyboardButton("💰 دریافت سکه", callback_data="get_coins")],
        [
            InlineKeyboardButton("📢 ممبر اجباری", callback_data="forced_member"),
            InlineKeyboardButton("👁 ویو اجباری", callback_data="forced_view")
        ],
        [
            InlineKeyboardButton("🚀 ثبت سفارش", callback_data="order"),
            InlineKeyboardButton("👤 حساب کاربری", callback_data="profile")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"سلام {user_name} عزیز! 👋\n\nبه ربات ممبرگیر و ویوگیر خوش آمدید.\nلطفاً از دکمه‌های زیر استفاده کنید:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های شیشه‌ای"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "get_coins":
        await query.edit_message_text("💰 بخش دریافت سکه:\nجهت دریافت سکه باید در کانال‌های تبلیغ شده عضو شوید یا از پست‌ها بازدید کنید.")
    elif data == "forced_member":
        await query.edit_message_text("📢 کانال‌های اجباری:\nلطفاً برای فعال‌سازی امکانات ربات، در کانال‌های اسپانسر عضو شده و روی دکمه تایید کلیک کنید.")
    elif data == "forced_view":
        await query.edit_message_text("👁 بازدید اجباری:\nپست‌های مشخص شده را بازدید کنید تا سکه ویو دریافت کنید.")
    elif data == "profile":
        await query.edit_message_text("👤 **حساب کاربری شما**:\n\n🪙 سکه ممبر: 0\n👁 سکه ویو: 0\n🆔 شناسه کاربری: " + str(query.from_user.id))
    elif data == "order":
        await query.edit_message_text("🚀 بخش ثبت سفارش:\nتعداد ممبر یا ویو مدنظر خود را مشخص کنید.")

# افزودن هندلرها به برنامه‌ی تلگرام
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(button_handler))

# ----------------- روت‌های Flask برای Render -----------------

@app.route('/')
def home():
    """روت اصلی جهت پینگ زدن توسط UptimeRobot"""
    return "Bot is alive and running!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت آپدیت‌ها از تلگرام"""
    if request.method == 'POST':
        asyncio.run(ptb_app.process_update(
            Update.de_json(request.get_json(force=True), ptb_app.bot)
        ))
        return "OK", 200

# ----------------- راه‌اندازی و تنظیم Webhook -----------------

async def setup_webhook():
    webhook_url = f"{RENDER_URL}/webhook"
    await ptb_app.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to: {webhook_url}")

if __name__ == '__main__':
    # مقداردهی اولیه ربات و وب‌هوک
    asyncio.run(ptb_app.initialize())
    asyncio.run(setup_webhook())
    
    # اجرا روی پورتی که Render مشخص می‌کند
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
