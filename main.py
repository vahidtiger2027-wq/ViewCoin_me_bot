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

# ----------------------------------------------------
# تابع بررسی و افزودن ستون‌های ناقص به دیتابیس
# ----------------------------------------------------
def patch_database():
    conn = database.get_connection()
    cursor = conn.cursor()
    columns_to_add = [
        ("spent_coins", "INTEGER DEFAULT 0"),
        ("spent_diamonds", "INTEGER DEFAULT 0"),
        ("views_done", "INTEGER DEFAULT 0"),
        ("joins_done", "INTEGER DEFAULT 0"),
        ("rewards_received", "INTEGER DEFAULT 0"),
        ("referral_commission", "INTEGER DEFAULT 0")
    ]
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass  # اگر ستون از قبل وجود داشت، خطا را نادیده بگیر
    conn.commit()
    conn.close()

# ----------------------------------------------------
# منوی اصلی ربات
# ----------------------------------------------------
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 هدیه روزانه", "👥 جذب زیرمجموعه")
    markup.add("👤 حساب کاربری")
    return markup

# ----------------------------------------------------
# دستور استارت (همراه با سیستم زیرمجموعه‌گیری)
# ----------------------------------------------------
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

# ----------------------------------------------------
# 📌 دکمه ۳: حساب کاربری
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "👤 حساب کاربری")
def account_handler(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "کاربر"
    
    conn = database.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as ref_count FROM users WHERE referrer_id = ?", (user_id,))
    ref_res = cursor.fetchone()
    ref_count = ref_res['ref_count'] if ref_res else 0
    
    conn.close()

    if user_row:
        user = dict(user_row)
        coins = user.get('coins', 0)
        diamonds = user.get('diamonds', 0)
        tickets = user.get('tickets', 0)
        spent_coins = user.get('spent_coins', 0) or 0
        spent_diamonds = user.get('spent_diamonds', 0) or 0
        views_done = user.get('views_done', 0) or 0
        joins_done = user.get('joins_done', 0) or 0
        rewards_received = user.get('rewards_received', 0) or 0
        referral_commission = user.get('referral_commission', 0) or 0

        text = (
            f"👤 **حساب کاربری شما**\n\n"
            f"👤 **نام:** {first_name}\n"
            f"🆔 **آیدی عددی:** `{user_id}`\n\n"
            f"🟡 **موجودی سکه:** {coins}\n"
            f"💎 **موجودی الماس:** {diamonds}\n"
            f"🎟 **تعداد بلیت‌های قرعه‌کشی:** {tickets}\n\n"
            f"💸 **سکه‌های خرج‌شده:** {spent_coins}\n"
            f"💎 **الماس‌های خرج‌شده:** {spent_diamonds}\n\n"
            f"👁 **بازدیدهای شما:** {views_done}\n"
            f"➕ **جوین‌های شما:** {joins_done}\n"
            f"🎁 **جوایز دریافتی:** {rewards_received}\n\n"
            f"👥 **تعداد زیرمجموعه‌ها:** {ref_count} نفر\n"
            f"💰 **پورسانت زیرمجموعه‌گیری:** {referral_commission} سکه"
        )
        bot.send_message(user_id, text, parse_mode="Markdown")
# ----------------------------------------------------
# 📌 دکمه ۴: ثبت تبلیغ (ویوگیر و ممبرگیر)
# ----------------------------------------------------
user_ad_data = {}  # ذخیره موقت داده‌های ثبت تبلیغ

@bot.message_handler(func=lambda msg: msg.text == "📥 ثبت تبلیغ")
def ad_menu_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_view = types.InlineKeyboardButton("👁 ثبت تبلیغ ویوگیر", callback_data="add_view_ad")
    btn_member = types.InlineKeyboardButton("📢 ثبت تبلیغ ممبرگیر", callback_data="add_member_ad")
    markup.add(btn_view, btn_member)
    bot.send_message(message.chat.id, "لطفاً نوع تبلیغ مورد نظر خود را انتخاب کنید:", reply_markup=markup)

# --- بخش ویوگیر ---
@bot.callback_query_handler(func=lambda call: call.data == "add_view_ad")
def view_packages_callback(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    packages = [
        ("۴۰ سکه 👈 ۴۰ ویو", "pkg_view_40_40"),
        ("۵۰ سکه 👈 ۵۰ ویو", "pkg_view_50_50"),
        ("۱۰۰ سکه 👈 ۱۰۰ ویو", "pkg_view_100_100"),
        ("۲۰۰ سکه 👈 ۲۰۰ ویو", "pkg_view_200_200")
    ]
    for text, cd in packages:
        markup.add(types.InlineKeyboardButton(text, callback_data=cd))
    
    bot.edit_message_text("بسته ویوگیر مورد نظر را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pkg_view_"))
def process_view_package(call):
    _, _, cost, views = call.data.split("_")
    cost, views = int(cost), int(views)
    user_id = call.from_user.id

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    user_coins = cursor.fetchone()['coins']
    conn.close()

    if user_coins < cost:
        bot.answer_callback_query(call.id, f"❌ موجودی سکه کافی نیست! (نیازمند {cost} سکه)", show_alert=True)
        return

    user_ad_data[user_id] = {'type': 'view', 'cost': cost, 'target': views}
    msg = bot.send_message(call.message.chat.id, "📌 لطفاً پست مورد نظر خود را (متن، عکس، ویدیو، لینک و...) فوروارد یا ارسال کنید:")
    bot.register_next_step_handler(msg, receive_view_post)

def receive_view_post(message):
    user_id = message.from_user.id
    if user_id not in user_ad_data:
        return

    user_ad_data[user_id]['message_id'] = message.message_id
    user_ad_data[user_id]['chat_id'] = message.chat.id

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ تأیید و ثبت پست", callback_data="confirm_view_ad"))
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_ad"))

    bot.reply_to(message, "آیا از ثبت این پست اطمینان دارید؟", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_view_ad")
def confirm_view_ad_callback(call):
    user_id = call.from_user.id
    data = user_ad_data.get(user_id)
    if not data:
        return

    # کسر سکه
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins - ?, spent_coins = spent_coins + ? WHERE user_id = ?", (data['cost'], data['cost'], user_id))
    conn.commit()
    conn.close()

    bot_info = bot.get_me()
    view_channel = database.get_setting("view_channel") or "@ViewCoin_me_bot"

    # دکمه‌های شیشه‌ای زیر پست در کانال ویو
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_back = types.InlineKeyboardButton("🔄 برگشت به ربات", url=f"https://t.me/{bot_info.username}")
    btn_turbo = types.InlineKeyboardButton("⚡ توربو", callback_data="turbo_view")
    btn_claim = types.InlineKeyboardButton("👁 ثبت بازدید", callback_data="claim_view")
    markup.add(btn_claim)
    markup.add(btn_back, btn_turbo)

    try:
        bot.copy_message(view_channel, data['chat_id'], data['message_id'], reply_markup=markup)
        bot.edit_message_text("🎉 پست شما با موفقیت ثبت شد و به کانال ارسال گردید!", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ خطا در ارسال به کانال ({view_channel}). لطفاً مطمئن شوید ربات در کانال ادمین است.", call.message.chat.id, call.message.message_id)

    del user_ad_data[user_id]

# --- بخش ممبرگیر ---
@bot.callback_query_handler(func=lambda call: call.data == "add_member_ad")
def member_packages_callback(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    packages = [
        ("۲۰ سکه 👈 ۱۰ ممبر", "pkg_mem_20_10"),
        ("۴۰ سکه 👈 ۲۰ ممبر", "pkg_mem_40_20"),
        ("۶۰ سکه 👈 ۳۰ ممبر", "pkg_mem_60_30"),
        ("۸۰ سکه 👈 ۴۰ ممبر", "pkg_mem_80_40"),
        ("۱۰۰ سکه 👈 ۵۰ ممبر", "pkg_mem_100_50")
    ]
    for text, cd in packages:
        markup.add(types.InlineKeyboardButton(text, callback_data=cd))
    
    bot.edit_message_text("بسته ممبرگیر مورد نظر را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pkg_mem_"))
def process_member_package(call):
    _, _, cost, members = call.data.split("_")
    cost, members = int(cost), int(members)
    user_id = call.from_user.id

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    user_coins = cursor.fetchone()['coins']
    conn.close()

    if user_coins < cost:
        bot.answer_callback_query(call.id, f"❌ موجودی سکه کافی نیست! (نیازمند {cost} سکه)", show_alert=True)
        return

    user_ad_data[user_id] = {'type': 'member', 'cost': cost, 'target': members}
    msg = bot.send_message(call.message.chat.id, "📌 لطفاً پست یا بنر تبلیغاتی همراه با لینک کانال خود را بفرستید:")
    bot.register_next_step_handler(msg, receive_member_post)

def receive_member_post(message):
    user_id = message.from_user.id
    if user_id not in user_ad_data:
        return

    user_ad_data[user_id]['message_id'] = message.message_id
    user_ad_data[user_id]['chat_id'] = message.chat.id

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ تأیید و ثبت لینک", callback_data="confirm_member_ad"))
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_ad"))

    bot.reply_to(message, "آیا از ثبت این تبلیغ ممبرگیر اطمینان دارید؟", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_member_ad")
def confirm_member_ad_callback(call):
    user_id = call.from_user.id
    data = user_ad_data.get(user_id)
    if not data:
        return

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins - ?, spent_coins = spent_coins + ? WHERE user_id = ?", (data['cost'], data['cost'], user_id))
    conn.commit()
    conn.close()

    bot_info = bot.get_me()
    member_channel = database.get_setting("member_channel") or "@ViewCoin_me_bot"

    # دکمه‌های شیشه‌ای زیر پست در کانال ممبرگیر
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_join = types.InlineKeyboardButton("📢 جوین در کانال", callback_data="join_channel_target")
    btn_diamond = types.InlineKeyboardButton("💎 دریافت الماس", callback_data="claim_member_diamond")
    btn_back = types.InlineKeyboardButton("🔄 بازگشت به ربات", url=f"https://t.me/{bot_info.username}")
    markup.add(btn_join, btn_diamond)
    markup.add(btn_back)

    try:
        bot.copy_message(member_channel, data['chat_id'], data['message_id'], reply_markup=markup)
        bot.edit_message_text("🎉 تبلیغ ممبرگیر شما با موفقیت ثبت شد و به کانال ارسال گردید!", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ خطا در ارسال به کانال ({member_channel}). لطفاً مطمئن شوید ربات در کانال ادمین است.", call.message.chat.id, call.message.message_id)

    del user_ad_data[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "cancel_ad")
def cancel_ad_callback(call):
    user_id = call.from_user.id
    if user_id in user_ad_data:
        del user_ad_data[user_id]
    bot.edit_message_text("❌ ثبت تبلیغ لغو شد.", call.message.chat.id, call.message.message_id)
# ----------------------------------------------------
# اجرای ربات

# ----------------------------------------------------

if __name__ == "__main__":
    database.init_db()
    patch_database()  # ستون‌های جدید دیتابیس را بررسی و اضافه می‌کند
    keep_alive()
    print("ربات روشن شد...")
    bot.infinity_polling()
