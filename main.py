import os
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import config
import database
import keyboards

# وب‌سرور ساده برای متصل نگه داشتن Render
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

# بررسی عضویت کاربر در کانال‌های اسپانسر
def check_sponsorship(user_id):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT link FROM sponsors")
    sponsors = cursor.fetchall()
    conn.close()

    not_joined = []
    for sp in sponsors:
        link = sp['link']
        chat_id = link.split('/')[-1]
        if not chat_id.startswith('@'):
            chat_id = '@' + chat_id
            
        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append((link, chat_id))
        except Exception:
            pass

    return not_joined

# تابع ارسال منو و پیام خوش‌آمدگویی
def send_welcome_menu(user_id):
    is_admin = user_id in config.ADMIN_IDS
    welcome_text = database.get_setting("welcome_message") or "به ربات خوش آمدید!"
    markup = keyboards.main_menu_keyboard(is_admin=is_admin)
    bot.send_message(user_id, welcome_text, reply_markup=markup)

# هندلر دستور /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = None
    
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
        
        if referrer_id:
            ref_coin = int(database.get_setting("referral_coin") or 0)
            ref_diamond = int(database.get_setting("referral_diamond") or 0)
            
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

    not_joined = check_sponsorship(user_id)
    if not_joined:
        markup = types.InlineKeyboardMarkup()
        for idx, (link, _) in enumerate(not_joined, 1):
            markup.add(types.InlineKeyboardButton(f"📢 عضویت در کانال {idx}", url=link))
        
        markup.add(types.InlineKeyboardButton("✅ عضو شدم / تایید", callback_data="check_join"))
        
        bot.send_message(
            user_id, 
            "⚠️ جهت استفاده از امکانات ربات، ابتدا باید در کانال‌های زیر عضو شوید:", 
            reply_markup=markup
        )
        return

    send_welcome_menu(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = call.from_user.id
    not_joined = check_sponsorship(user_id)
    
    if not_joined:
        bot.answer_callback_query(call.id, "❌ شما هنوز در تمام کانال‌ها عضو نشده‌اید!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome_menu(user_id)

# --- 1. حساب کاربری ---
@bot.message_handler(func=lambda msg: msg.text == "👤 حساب کاربری")
def profile_handler(message):
    user_id = message.from_user.id
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins, diamonds, tickets FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as ref_count FROM users WHERE referrer_id = ?", (user_id,))
    ref_count = cursor.fetchone()['ref_count']
    conn.close()

    if user:
        text = (
            f"👤 **حساب کاربری شما**\n\n"
            f"🆔 شناسه عددی: `{user_id}`\n"
            f"🟡 سکه‌ها: {user['coins']}\n"
            f"💎 الماس‌ها: {user['diamonds']}\n"
            f"🎟 بلیت‌های قرعه‌کشی: {user['tickets']}\n"
            f"👥 تعداد زیرمجموعه‌ها: {ref_count} نفر"
        )
        bot.send_message(user_id, text, parse_mode="Markdown")

# --- 2. زیرمجموعه‌گیری ---
@bot.message_handler(func=lambda msg: msg.text == "👥 زیرمجموعه‌گیری")
def referral_handler(message):
    user_id = message.from_user.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    ref_coin = database.get_setting("referral_coin") or "0"
    ref_diamond = database.get_setting("referral_diamond") or "0"

    text = (
        f"👥 **سیستم زیرمجموعه‌گیری**\n\n"
        f"با دعوت دوستان خود به ربات، پاداش دریافت کنید!\n\n"
        f"🎁 **پاداش هر دعوت:**\n"
        f"🟡 {ref_coin} سکه\n"
        f"💎 {ref_diamond} الماس\n\n"
        f"🔗 **لینک اختصاصی شما:**\n`{ref_link}`"
    )
    bot.send_message(user_id, text, parse_mode="Markdown")

# --- 3. هدیه روزانه ---
@bot.message_handler(func=lambda msg: msg.text == "🎁 هدیه روزانه")
def daily_reward_handler(message):
    user_id = message.from_user.id
    daily_coin = int(database.get_setting("daily_coin") or 100)
    daily_diamond = int(database.get_setting("daily_diamond") or 5)

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET coins = coins + ?, diamonds = diamonds + ? 
        WHERE user_id = ?
    """, (daily_coin, daily_diamond, user_id))
    conn.commit()
    conn.close()

    bot.send_message(
        user_id, 
        f"🎉 **هدیه روزانه دریافت شد!**\n\n"
        f"🟡 {daily_coin} سکه\n"
        f"💎 {daily_diamond} الماس\n"
        f"به حساب شما اضافه شد."
    )

# --- 4. انتقال سکه و الماس ---
@bot.message_handler(func=lambda msg: msg.text == "🔄 انتقال سکه و الماس")
def transfer_start(message):
    msg = bot.send_message(
        message.chat.id, 
        "🔄 جهت انتقال، لطفاً اطلاعات را به صورت زیر ارسال کنید:\n\n"
        "فرمت ارسال:\n"
        "`نوع شناسه مقدار`\n\n"
        "مثال برای انتقال ۱۰ سکه:\n"
        "`coin 123456789 10`\n\n"
        "مثال برای انتقال ۵ الماس:\n"
        "`diamond 123456789 5`",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_inline_keyboard()
    )

# پردازش متنی انتقال
@bot.message_handler(func=lambda msg: msg.text and (msg.text.startswith("coin ") or msg.text.startswith("diamond ")))
def process_transfer(message):
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "❌ فرمت وارد شده اشتباه است.")
        return

    asset_type, target_id_str, amount_str = parts[0], parts[1], parts[2]

    if not target_id_str.isdigit() or not amount_str.isdigit():
        bot.reply_to(message, "❌ شناسه و مقدار باید عدد باشند.")
        return

    target_id = int(target_id_str)
    amount = int(amount_str)
    sender_id = message.from_user.id

    if sender_id == target_id:
        bot.reply_to(message, "❌ نمی‌توانید به حساب خودتان انتقال دهید!")
        return

    if amount <= 0:
        bot.reply_to(message, "❌ مقدار انتقال باید بیشتر از صفر باشد.")
        return

    conn = database.get_connection()
    cursor = conn.cursor()
    
    # بررسی وجود مقصد
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (target_id,))
    if not cursor.fetchone():
        bot.reply_to(message, "❌ کاربر مقصد در ربات یافت نشد.")
        conn.close()
        return

    # بررسی موجودی مبدا
    column = "coins" if asset_type == "coin" else "diamonds"
    cursor.execute(f"SELECT {column} FROM users WHERE user_id = ?", (sender_id,))
    sender_balance = cursor.fetchone()[column]

    if sender_balance < amount:
        bot.reply_to(message, "❌ موجودی شما برای این انتقال کافی نیست.")
        conn.close()
        return

    # انجام انتقال
    cursor.execute(f"UPDATE users SET {column} = {column} - ? WHERE user_id = ?", (amount, sender_id))
    cursor.execute(f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    asset_title = "سکه" if asset_type == "coin" else "الماس"
    bot.reply_to(message, f"✅ با موفقیت {amount} {asset_title} به کاربر `{target_id}` منتقل شد.", parse_mode="Markdown")
    
    try:
        bot.send_message(target_id, f"🎁 کاربر `{sender_id}` مقدار {amount} {asset_title} به حساب شما واریز کرد!", parse_mode="Markdown")
    except Exception:
        pass

# انصراف از عملیات
@bot.callback_query_handler(func=lambda call: call.data == "cancel_action")
def cancel_callback(call):
    bot.answer_callback_query(call.id, "عملیات لغو شد.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == "__main__":
    database.init_db()
    keep_alive()
    print("ربات روشن و فعال شد...")
    bot.infinity_polling()
