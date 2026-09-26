import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request
import telebot
from telebot import types

# تنظیمات لوگ‌ها
logging.basicConfig(level=logging.INFO)

# دریافت متغیرهای محیطی از Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
ADMIN_ID = os.environ.get('ADMIN_ID')

if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        ADMIN_ID = None

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# اتصال به دیتابیس PostgreSQL
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# ساخت جداول دیتابیس
def init_db():
    if not DATABASE_URL:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            coins INT DEFAULT 0,
            gems INT DEFAULT 0,
            invites INT DEFAULT 0
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    logging.error(f"Error initializing DB: {e}")

# دریافت یا ساخت اطلاعات کاربر در دیتابیس
def get_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s;", (user_id,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (user_id, coins, gems, invites) VALUES (%s, 0, 0, 0) RETURNING *;", (user_id,))
        user = cur.fetchone()
        conn.commit()
    cur.close()
    conn.close()
    return user

# منوی اصلی ربات
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_profile = types.KeyboardButton("👤 حساب کاربری")
    btn_earn = types.KeyboardButton("💎 جمع آوری سکه رایگان")
    btn_order = types.KeyboardButton("🐳 ثبت تبلیغ ویو گیر و ممبر گیر")
    btn_sub = types.KeyboardButton("👥 جذب زیر مجموعه")
    btn_shop = types.KeyboardButton("🏪 فروشگاه")
    btn_transfer_coin = types.KeyboardButton("💰 انتقال سکه")
    btn_transfer_gem = types.KeyboardButton("💎 انتقال الماس")
    btn_lottery = types.KeyboardButton("🎲 قرعه کشی")

    markup.add(btn_profile, btn_earn)
    markup.add(btn_order, btn_sub)
    markup.add(btn_shop, btn_transfer_coin)
    markup.add(btn_transfer_gem, btn_lottery)

    # نمایش دکمه مدیریت فقط برای ادمین
    if ADMIN_ID and user_id == ADMIN_ID:
        btn_admin = types.KeyboardButton("⚙️ پنل مدیریت")
        markup.add(btn_admin)

    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    get_user(user_id)
    bot.send_message(
        message.chat.id,
        "سلام! به ربات ممبرگیر و ویوگیر خوش آمدید.\nلطفاً از گزینه‌های زیر استفاده کنید:",
        reply_markup=main_keyboard(user_id)
    )

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text

    if text == "👤 حساب کاربری":
        user = get_user(user_id)
        msg = (
            f"👤 **حساب کاربری**\n\n"
            f"🆔 شناسه: `{user['user_id']}`\n"
            f"💰 موجودی سکه: {user['coins']}\n"
            f"💎 موجودی الماس: {user['gems']}\n"
            f"👥 تعداد زیرمجموعه‌ها: {user['invites']}"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "💎 جمع آوری سکه رایگان":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👁 دیدن پست و دریافت سکه", callback_data="get_coin_view"))
        bot.send_message(message.chat.id, "جهت دریافت سکه رایگان یکی از روش‌های زیر را انتخاب کنید:", reply_markup=markup)

    elif text == "🐳 ثبت تبلیغ ویو گیر و ممبر گیر":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("👁 ثبت تبلیغ ویوگیر", callback_data="order_view"),
            types.InlineKeyboardButton("👥 ثبت تبلیغ ممبرگیر", callback_data="order_member")
        )
        bot.send_message(message.chat.id, "لطفاً نوع سفارش خود را انتخاب کنید:", reply_markup=markup)

    elif text == "⚙️ پنل مدیریت" and user_id == ADMIN_ID:
        bot.send_message(message.chat.id, "⚙️ **به پنل مدیریت خوش آمدید!**\nامکانات مدیریتی آماده استفاده است.")

    else:
        bot.send_message(message.chat.id, "دستور انتخاب‌شده پردازش شد.", reply_markup=main_keyboard(user_id))

# مسیر دریافت وب‌هوک
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://' + request.host + '/' + BOT_TOKEN)
    return "Webhook set successfully!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
