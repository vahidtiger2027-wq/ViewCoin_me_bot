import os
import telebot
from telebot import types
from flask import Flask, request
import psycopg2
from psycopg2.extras import RealDictCursor
from database import init_db

TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ساخت جداول دیتابیس در صورت عدم وجود
try:
    init_db()
except Exception as e:
    print(f"Database Init Error: {e}")

def get_db_connection():
    return psycopg2.connect(os.environ.get('DATABASE_URL'), sslmode='require')

def get_setting(key):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = %s;", (key,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else ""

def get_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s;", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💎 جمع آوری سکه رایگان"),
        types.KeyboardButton("💻 حساب کاربری"),
        types.KeyboardButton("👥 جذب زیر مجموعه"),
        types.KeyboardButton("📥 ثبت تبلیغ ویو گیر و ممبر گیر"),
        types.KeyboardButton("👨‍💻🛍 فروشگاه"),
        types.KeyboardButton("💰 انتقال سکه"),
        types.KeyboardButton("💎 انتقال الماس"),
        types.KeyboardButton("🎲 قرعه کشی")
    )
    return markup

def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ تنظیم سفارشات ویو", callback_data="adm_view_order"),
        types.InlineKeyboardButton("⚙️ تنظیم سفارش ممبر", callback_data="adm_member_order"),
        types.InlineKeyboardButton("💳 تنظیم شماره کارت", callback_data="adm_card"),
        types.InlineKeyboardButton("🌐 تنظیم درگاه پرداخت", callback_data="adm_gateway"),
        types.InlineKeyboardButton("🎁 تنظیم سکه و الماس روزانه", callback_data="adm_daily"),
        types.InlineKeyboardButton("👥 تنظیم سکه زیرمجموعه", callback_data="adm_ref"),
        types.InlineKeyboardButton("🔒 تنظیم اسپانسر جوین اجباری", callback_data="adm_sponsor"),
        types.InlineKeyboardButton("⏳ تنظیم ماندگاری و جریمه لفت", callback_data="adm_penalty"),
        types.InlineKeyboardButton("📊 آمار کاربران", callback_data="adm_stats")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    username = message.from_user.username or "بدون آیدی"
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username) 
        VALUES (%s, %s) 
        ON CONFLICT (user_id) DO UPDATE SET username = %s;
    """, (user_id, username, username))
    conn.commit()
    cur.close()
    conn.close()

    welcome_text = get_setting('welcome_msg')
    bot.send_message(user_id, f"{welcome_text}\n\nبه منوی اصلی خوش آمدید:", reply_markup=main_keyboard())

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(message.chat.id, "🛠 **به پنل مدیریت خوش آمدید:**", reply_markup=admin_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💻 حساب کاربری")
def user_account(message):
    u = get_user(message.chat.id)
    if not u:
        return
    
    msg = f"💻 **مشخصات حساب کاربری شما:**\n\n"
    msg += f"👤 نام کاربری: @{u['username']}\n" if u['username'] != "بدون آیدی" else "👤 نام کاربری: ندارد\n"
    msg += f"🆔 آیدی عددی: `{u['user_id']}`\n"
    msg += f"🎁 هدیه مدیریت: {u['gifts_received']}\n"
    msg += f"👁 بازدیدهای شما: {u['total_views']}\n"
    msg += f"👁 بازدیدهای امروز: {u['today_views']}\n"
    msg += f"🏆 جوایز قرعه‌کشی: {u['lottery_wins']}\n"
    msg += f"👥 تعداد زیرمجموعه‌ها: {u['referrals_count']}\n"
    msg += f"💰 موجودی سکه: {u['coins']}\n"
    msg += f"💎 موجودی الماس: {u['diamonds']}\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📥 ثبت تبلیغ ویو گیر و ممبر گیر")
def order_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👁 ثبت تبلیغ ویوگیر", callback_data="order_view_menu"),
        types.InlineKeyboardButton("👥 ثبت تبلیغ ممبر گیر", callback_data="order_member_menu")
    )
    bot.send_message(message.chat.id, "لطفاً نوع سفارش خود را انتخاب کنید:", reply_markup=markup)

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + TOKEN)
    return "Bot is running online!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
