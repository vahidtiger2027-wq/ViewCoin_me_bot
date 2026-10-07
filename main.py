import os
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import config
import database

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

bot = telebot.TeleBot(config.BOT_TOKEN)

# منوی اصلی ربات
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 هدیه روزانه")
    return markup

# دستور استارت
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    
    # ثبت کاربر در دیتابیس در صورت جدید بودن
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    conn.close()

    bot.send_message(user_id, "به ربات خوش آمدید! لطفاً از منوی زیر استفاده کنید:", reply_markup=get_main_menu())

# ----------------------------------------------------
# 📌 دکمه ۱: هدیه روزانه
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "🎁 هدیه روزانه")
def daily_reward_handler(message):
    user_id = message.from_user.id
    daily_coin = int(database.get_setting("daily_coin") or 100)
    daily_diamond = int(database.get_setting("daily_diamond") or 5)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins + ?, diamonds = diamonds + ? WHERE user_id = ?", (daily_coin, daily_diamond, user_id))
    conn.commit()
    conn.close()

    bot.send_message(user_id, f"🎉 **هدیه روزانه دریافت شد!**\n\n🟡 {daily_coin} سکه\n💎 {daily_diamond} الماس\nبه حساب شما اضافه شد.", parse_mode="Markdown")

if __name__ == "__main__":
    database.init_db()
    keep_alive()
    print("ربات روشن شد...")
    bot.infinity_polling()
# ---------- تنظیمات دکمه جذب زیرمجموعه ----------
LINK_VIEW_CHANNEL = "https://t.me/view_sin_channel"     # لینک ویو گیر چنل
LINK_MEMBER_CHANNEL = "https://t.me/my_member_man"      # لینک ممبر گیر چنل
LINK_BOT = "https://t.me/ViewCoin_me_bot"               # لینک ربات ویو گیر ممبر گیر

REWARD_COINS = "۳۰۰"      # سکه به ازای هر نفر
REWARD_DIAMONDS = "۵۰"    # الماس به ازای هر نفر

RECRUIT_TEXT = f"""
🎯 جذب زیرمجموعه

🔗 ویو گیر چنل:
{LINK_VIEW_CHANNEL}

🔗 ممبر گیر چنل:
{LINK_MEMBER_CHANNEL}

🤖 ربات ویو گیر و ممبر گیر:
{LINK_BOT}

🎁 جوایز معرفی هر نفر:
🪙 سکه: {REWARD_COINS}
💎 الماس: {REWARD_DIAMONDS}
"""

# ---------- دکمه: جذب زیرمجموعه ----------
@bot.message_handler(func=lambda m: m.text == "💰 جذب زیرمجموعه")
def recruit_menu(message):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("👁 ویو گیر چنل", url=LINK_VIEW_CHANNEL))
    markup.add(telebot.types.InlineKeyboardButton("👥 ممبر گیر چنل", url=LINK_MEMBER_CHANNEL))
    markup.add(telebot.types.InlineKeyboardButton("🤖 ربات ویو گیر ممبر گیر", url=LINK_BOT))
    bot.send_message(message.chat.id, RECRUIT_TEXT, reply_markup=markup)
