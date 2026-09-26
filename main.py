import os
import logging
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request
import telebot
from telebot import types

logging.basicConfig(level=logging.INFO)

# دریافت متغیرهای محیطی
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

# حافظه موقت برای وضعیت کاربران (State Management)
user_states = {}
user_data_temp = {}

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    if not DATABASE_URL:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    
    # جدول کاربران
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            coins INT DEFAULT 0,
            gems INT DEFAULT 0,
            invites INT DEFAULT 0,
            views_total INT DEFAULT 0,
            views_today INT DEFAULT 0,
            last_daily TIMESTAMP,
            lottery_prizes INT DEFAULT 0,
            lottery_tickets INT DEFAULT 0,
            referrer_id BIGINT
        );
    ''')
    
    # جدول تنظیمات سیستم
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(50) PRIMARY KEY,
            value TEXT
        );
    ''')
    
    # مقداردهی اولیه تنظیمات پیش‌فرض
    default_settings = {
        'card_number': 'تنظیم نشده',
        'gateway_link': 'تنظیم نشده',
        'daily_coins': '20',
        'daily_gems': '20',
        'sub_coins': '200',
        'sub_gems': '50',
        'gift_coins': '0',
        'lottery_active': 'false',
        'lottery_duration': 'none',
        'forced_channel': '',
        'welcome_msg': 'سلام! به ربات ممبرگیر و ویوگیر خوش آمدید.',
        'mandatory_days': '3',
        'penalty_gems': '2'
    }
    for k, v in default_settings.items():
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING;", (k, v))
        
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    logging.error(f"Error initializing DB: {e}")

def get_setting(key):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = %s;", (key,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else ''

def set_setting(key, val):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s;", (key, str(val), str(val)))
    conn.commit()
    cur.close()
    conn.close()

def get_user(user_id, username=None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s;", (user_id,))
    user = cur.fetchone()
    if not user:
        cur.execute(
            "INSERT INTO users (user_id, username, coins, gems) VALUES (%s, %s, 0, 0) RETURNING *;",
            (user_id, username)
        )
        user = cur.fetchone()
        conn.commit()
    elif username and user['username'] != username:
        cur.execute("UPDATE users SET username = %s WHERE user_id = %s;", (username, user_id))
        conn.commit()
    cur.close()
    conn.close()
    return user

def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(types.KeyboardButton("💎 جمع آوری سکه رایگان"), types.KeyboardButton("👤 حساب کاربری"))
    markup.add(types.KeyboardButton("🐳 ثبت تبلیغ ویو گیر و ممبر گیر"), types.KeyboardButton("👥 جذب زیر مجموعه"))
    markup.add(types.KeyboardButton("🏪 فروشگاه"), types.KeyboardButton("💰 انتقال سکه"))
    markup.add(types.KeyboardButton("💎 انتقال الماس"), types.KeyboardButton("🎲 قرعه کشی"))
    
    if ADMIN_ID and user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("⚙️ پنل مدیریت"))
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # بررسی زیرمجموعه‌گیری
    args = message.text.split()
    get_user(user_id, username)
    
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT referrer_id FROM users WHERE user_id = %s;", (user_id,))
            res = cur.fetchone()
            if res and res[0] is None:
                cur.execute("UPDATE users SET referrer_id = %s WHERE user_id = %s;", (ref_id, user_id))
                sub_coins = int(get_setting('sub_coins'))
                sub_gems = int(get_setting('sub_gems'))
                cur.execute("UPDATE users SET coins = coins + %s, gems = gems + %s, invites = invites + 1 WHERE user_id = %s;", (sub_coins, sub_gems, ref_id))
                conn.commit()
                bot.send_message(ref_id, f"🎉 کاربر جدید با لینک شما وارد شد!\n+{sub_coins} سکه و +{sub_gems} الماس دریافت کردید.")
            cur.close()
            conn.close()

    welcome_text = get_setting('welcome_msg')
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard(user_id))

@bot.message_handler(func=lambda message: True, content_types=['text', 'photo'])
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text or ""
    state = user_states.get(user_id)

    # ۱۰. بخش مدیریت و تنظیمات ادمین
    if state and state.startswith("admin_set_"):
        key_map = {
            "admin_set_card": "card_number",
            "admin_set_gateway": "gateway_link",
            "admin_set_daily_coins": "daily_coins",
            "admin_set_daily_gems": "daily_gems",
            "admin_set_sub_coins": "sub_coins",
            "admin_set_sub_gems": "sub_gems",
            "admin_set_gift": "gift_coins",
            "admin_set_welcome": "welcome_msg",
            "admin_set_days": "mandatory_days",
            "admin_set_penalty": "penalty_gems"
        }
        set_key = key_map.get(state)
        if set_key:
            set_setting(set_key, text)
            bot.send_message(message.chat.id, f"✅ مقدار جدید با موفقیت ذخیره شد: {text}")
            user_states.pop(user_id, None)
            return

    # ۱. روزانه سکه رایگان
    if text == "💎 جمع آوری سکه رایگان":
        user = get_user(user_id)
        now = datetime.now()
        last = user['last_daily']
        if last and (now - last).total_seconds() < 86400:
            bot.send_message(message.chat.id, "❌ شما هدیه روزانه امروز را دریافت کرده‌اید. فردا دوباره تلاش کنید!")
        else:
            d_coins = int(get_setting('daily_coins'))
            d_gems = int(get_setting('daily_gems'))
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE users SET coins = coins + %s, gems = gems + %s, last_daily = %s WHERE user_id = %s;", (d_coins, d_gems, now, user_id))
            conn.commit()
            cur.close()
            conn.close()
            bot.send_message(message.chat.id, f"🎉 هدیه روزانه دریافت شد:\n💰 {d_coins} سکه\n💎 {d_gems} الماس")

    # ۲. حساب کاربر
    elif text == "👤 حساب کاربری":
        user = get_user(user_id, message.from_user.username)
        username_str = f"@{user['username']}" if user['username'] else "ندارد"
        msg = (
            f"💻 **حساب کاربری مشخصات**\n\n"
            f"🆔 نام کاربری: {username_str}\n"
            f"🔢 شناسه کاربری: `{user['user_id']}`\n"
            f"🎁 هدیه مدیریت: {get_setting('gift_coins')}\n"
            f"👁 بازدیدهای شما: {user['views_total']}\n"
            f"📅 بازدیدهای امروز: {user['views_today']}\n"
            f"🏆 جوایز: {user['lottery_prizes']}\n"
            f"👥 تعداد زیرمجموعه‌ها: {user['invites']}\n"
            f"💰 موجودی سکه شما: {user['coins']}\n"
            f"💎 موجودی الماس شما: {user['gems']}"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    # ۳. زیرمجموعه‌گیری
    elif text == "👥 جذب زیر مجموعه":
        sub_c = get_setting('sub_coins')
        sub_g = get_setting('sub_gems')
        bot_info = bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (
            f"👥 **جذب زیر مجموعه**\n\n"
            f"با دعوت هر دوست {sub_c} سکه ویوگیر و {sub_g} الماس ممبرگیر دریافت کنید!\n\n"
            f"🔗 لینک اختصاصی شما:\n`{link}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    # ۴. ثبت تبلیغ
    elif text == "🐳 ثبت تبلیغ ویو گیر و ممبر گیر":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("👁 ثبت تبلیغ ویوگیر", callback_data="add_view_ad"),
            types.InlineKeyboardButton("👥 ثبت تبلیغ ممبرگیر", callback_data="add_member_ad")
        )
        bot.send_message(message.chat.id, "لطفاً نوع سفارش خود را انتخاب کنید:", reply_markup=markup)

    # ۵. فروشگاه
    elif text == "🏪 فروشگاه":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("👁 خرید سکه ویوگیر", callback_data="shop_coins"),
            types.InlineKeyboardButton("💎 خرید الماس ممبرگیر", callback_data="shop_gems")
        )
        bot.send_message(message.chat.id, "👨‍💻🛍️ **فروشگاه**\nلطفاً بخش مورد نظر را انتخاب کنید:", reply_markup=markup, parse_mode="Markdown")

    # ۶. انتقال سکه
    elif text == "💰 انتقال سکه":
        user_states[user_id] = "transfer_coin_target"
        bot.send_message(message.chat.id, "آیدی عددی اکانت مورد نظر را وارد کنید:")

    elif state == "transfer_coin_target":
        if text.isdigit():
            user_data_temp[user_id] = {'target': int(text)}
            user_states[user_id] = "transfer_coin_amount"
            bot.send_message(message.chat.id, "مقدار سکه انتقالی را وارد کنید:")
        else:
            bot.send_message(message.chat.id, "لطفاً یک آیدی عددی معتبر وارد کنید.")

    elif state == "transfer_coin_amount":
        if text.isdigit():
            amt = int(text)
            target = user_data_temp[user_id]['target']
            user = get_user(user_id)
            if user['coins'] >= amt:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE users SET coins = coins - %s WHERE user_id = %s;", (amt, user_id))
                cur.execute("UPDATE users SET coins = coins + %s WHERE user_id = %s;", (amt, target))
                conn.commit()
                cur.close()
                conn.close()
                bot.send_message(message.chat.id, "✅ انتقال با موفقیت انجام شد.")
                bot.send_message(target, f"🎁 مبلغ {amt} سکه از طرف کاربر `{user_id}` به حساب شما واریز شد.")
            else:
                bot.send_message(message.chat.id, "❌ موجودی سکه شما کافی نیست.")
            user_states.pop(user_id, None)

    # ۷. انتقال الماس
    elif text == "💎 انتقال الماس":
        user_states[user_id] = "transfer_gem_target"
        bot.send_message(message.chat.id, "آیدی عددی اکانت مورد نظر را وارد کنید:")

    elif state == "transfer_gem_target":
        if text.isdigit():
            user_data_temp[user_id] = {'target': int(text)}
            user_states[user_id] = "transfer_gem_amount"
            bot.send_message(message.chat.id, "مقدار الماس انتقالی را وارد کنید:")
        else:
            bot.send_message(message.chat.id, "لطفاً یک آیدی عددی معتبر وارد کنید.")

    elif state == "transfer_gem_amount":
        if text.isdigit():
            amt = int(text)
            target = user_data_temp[user_id]['target']
            user = get_user(user_id)
            if user['gems'] >= amt:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE users SET gems = gems - %s WHERE user_id = %s;", (amt, user_id))
                cur.execute("UPDATE users SET gems = gems + %s WHERE user_id = %s;", (amt, target))
                conn.commit()
                cur.close()
                conn.close()
                bot.send_message(message.chat.id, "✅ انتقال الماس با موفقیت انجام شد.")
                bot.send_message(target, f"🎁 تعداد {amt} الماس از طرف کاربر `{user_id}` به حساب شما واریز شد.")
            else:
                bot.send_message(message.chat.id, "❌ موجودی الماس شما کافی نیست.")
            user_states.pop(user_id, None)

    # ۸. قرعه کشی
    elif text == "🎲 قرعه کشی":
        msg = (
            "🎲 **به قرعه کشی ربات خوش آمدید**\n\n"
            "برای ورود در قرعه کشی ربات بزرگ ممبرگیر و ویوگیر باید از ربات خرید کنید و بلیت شانس دریافت کنید:\n\n"
            "💳 ۵۰.۰۰۰ تومان خرید = ۲ بلیت\n"
            "💳 ۱۰۰.۰۰۰ تومان خرید = ۴ بلیت\n"
            "💳 ۲۰۰.۰۰۰ تومان خرید = ۶ بلیت\n"
            "💳 ۵۰۰.۰۰۰ تومان خرید = ۱۰ بلیت\n"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏪 ورود به فروشگاه", callback_data="shop_coins"))
        bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

    # ۹. پنل مدیریت
    elif text == "⚙️ پنل مدیریت" and user_id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💳 تنظیم شماره کارت", callback_data="admin_card"),
            types.InlineKeyboardButton("💱 تنظیم درگاه پرداخت", callback_data="admin_gateway"),
            types.InlineKeyboardButton("🎁 تنظیم سکه/الماس روزانه", callback_data="admin_daily"),
            types.InlineKeyboardButton("👥 تنظیم جایزه زیرمجموعه", callback_data="admin_sub"),
            types.InlineKeyboardButton("✉️ تنظیم پیام خوشامدگویی", callback_data="admin_welcome"),
            types.InlineKeyboardButton("🔒 تنظیم روز جوین اجباری و جریمه", callback_data="admin_mandatory"),
            types.InlineKeyboardButton("📊 آمار کاربران", callback_data="admin_stats")
        )
        bot.send_message(message.chat.id, "⚙️ **پنل مدیریت**\nلطفاً بخش مورد نظر را انتخاب کنید:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id

    if call.data == "shop_coins":
        card_num = get_setting('card_number')
        gw = get_setting('gateway_link')
        msg = (
            f"👁 **خرید سکه ویو گیر**\n\n"
            f"🔹 ۲۰.۰۰۰ سکه = ۵۰.۰۰۰ تومان\n"
            f"🔹 ۴۰.۰۰۰ سکه = ۱۰۰.۰۰۰ تومان\n"
            f"🔹 ۵۰.۰۰۰ سکه = ۱۵۰.۰۰۰ تومان\n"
            f"🔹 ۲۰۰.۰۰۰ سکه = ۲۰۰.۰۰۰ تومان\n\n"
            f"💳 **شماره کارت:** `{card_num}`\n"
            f"🌐 **لینک درگاه:** {gw}\n\n"
            f"پس از واریز کارت به کارت، عکس رسید را جهت تایید ارسال کنید."
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "shop_gems":
        card_num = get_setting('card_number')
        gw = get_setting('gateway_link')
        msg = (
            f"💎 **خرید الماس ممبرگیر**\n\n"
            f"🔹 ۱۰۰ الماس = ۲۵.۰۰۰ تومان\n"
            f"🔹 ۲۵۰ الماس = ۵۰.۰۰۰ تومان\n"
            f"🔹 ۵۰۰ الماس = ۱۰۰.۰۰۰ تومان\n"
            f"🔹 ۱۰۰۰ الماس = ۲۰۰.۰۰۰ تومان\n"
            f"🔹 ۴۰۰۰ الماس = ۸۰۰.۰۰۰ تومان\n\n"
            f"💳 **شماره کارت:** `{card_num}`\n"
            f"🌐 **لینک درگاه:** {gw}\n\n"
            f"پس از واریز کارت به کارت، عکس رسید را جهت تایید ارسال کنید."
        )
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    # دسترسی‌های مدیریتی callback
    elif call.data == "admin_card" and user_id == ADMIN_ID:
        user_states[user_id] = "admin_set_card"
        bot.send_message(call.message.chat.id, "لطفاً شماره کارت جدید را وارد کنید:")

    elif call.data == "admin_gateway" and user_id == ADMIN_ID:
        user_states[user_id] = "admin_set_gateway"
        bot.send_message(call.message.chat.id, "لطفاً لینک یا آیدی درگاه پرداخت جدید را وارد کنید:")

    elif call.data == "admin_daily" and user_id == ADMIN_ID:
        user_states[user_id] = "admin_set_daily_coins"
        bot.send_message(call.message.chat.id, "مقدار سکه روزانه را وارد کنید:")

    elif call.data == "admin_sub" and user_id == ADMIN_ID:
        user_states[user_id] = "admin_set_sub_coins"
        bot.send_message(call.message.chat.id, "مقدار سکه زیرمجموعه‌گیری را وارد کنید:")

    elif call.data == "admin_welcome" and user_id == ADMIN_ID:
        user_states[user_id] = "admin_set_welcome"
        bot.send_message(call.message.chat.id, "متن خوشامدگویی جدید را وارد کنید:")

    elif call.data == "admin_mandatory" and user_id == ADMIN_ID:
        user_states[user_id] = "admin_set_days"
        bot.send_message(call.message.chat.id, "تعداد روز جوین اجباری را وارد کنید:")

    elif call.data == "admin_stats" and user_id == ADMIN_ID:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users;")
        total_users = cur.fetchone()[0]
        cur.close()
        conn.close()
        bot.send_message(call.message.chat.id, f"📊 **آمار سیستم:**\n\n👤 تعداد کل کاربران: {total_users}", parse_mode="Markdown")

# وب‌هوک
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
