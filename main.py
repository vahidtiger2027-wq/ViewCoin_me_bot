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

# منوی اصلی ربات (شامل هدیه روزانه و جذب زیرمجموعه)
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("حصاب کاربری 🎁 هدیه روزانه", "👥 جذب زیرمجموعه")
    return markup

# دستور استارت (همراه با سیستم زیرمجموعه‌گیری)
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = None
    
    # بررسی لینک دعوت
    if len(args) > 1 and args[1].isdigit():
        possible_ref = int(args[1])
        if possible_ref != user_id:
            referrer_id = possible_ref

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user_exists = cursor.fetchone()

    if not user_exists:
        cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()
        
        # اعطای پاداش به فرد دعوت‌کننده
        if referrer_id:
            ref_coin = int(database.get_setting("referral_coin") or 200)
            ref_diamond = int(database.get_setting("referral_diamond") or 50)
            
            cursor.execute("""
                UPDATE users 
                SET coins = coins + ?, diamonds = diamonds + ? 
                WHERE user_id = ?
            """, (ref_coin, ref_diamond, referrer_id))
            conn.commit()
            
            try:
                bot.send_message(
                    referrer_id, 
                    f"🎉 کاربر جدیدی با لینک شما وارد ربات شد!\n"
                    f"🎁 پاداش شما: {ref_coin} سکه و {ref_diamond} الماس"
                )
            except Exception:
                pass

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

# ----------------------------------------------------
# 📌 دکمه ۲: جذب زیرمجموعه
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "👥 جذب زیرمجموعه")
def referral_handler(message):
    user_id = message.from_user.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    ref_coin = database.get_setting("referral_coin") or "200"
    ref_diamond = database.get_setting("referral_diamond") or "50"

    text = (
        f"👥 **سیستم جذب زیرمجموعه**\n\n"
        f"با دعوت دوستان خود به ربات، سکه و الماس رایگان دریافت کنید!\n\n"
        f"🎁 **پاداش هر دعوت:**\n"
        f"🟡 {ref_coin} سکه\n"
        f"💎 {ref_diamond} الماس\n\n"
        f"🔗 **لینک اختصاصی شما:**\n`{ref_link}`"
    )
    bot.send_message(user_id, text, parse_mode="Markdown")

if __name__ == "__main__":
    database.init_db()
    keep_alive()
    print("ربات روشن شد...")
    bot.infinity_polling()

