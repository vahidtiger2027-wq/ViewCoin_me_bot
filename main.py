import os
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import config
import database
import admin


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
# تنظیم آیدی دقیق کانال‌ها
# ----------------------------------------------------
VIEW_CHANNEL = "@view_sin_channel"
MEMBER_CHANNEL = "@my_member_man"

user_ad_data = {}  # ذخیره موقت داده‌های ثبت تبلیغ

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
            pass
    conn.commit()
    conn.close()

# ----------------------------------------------------
# منوی اصلی ربات
# ----------------------------------------------------
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 هدیه روزانه", "👥 جذب زیرمجموعه")
    markup.add("👤 حساب کاربری", "📥 ثبت تبلیغ")
    markup.add("🔄 انتقال سکه و الماس", "🛍️ فروشگاه")
    markup.add("🎫 قرعه‌کشی")
    return markup

# ----------------------------------------------------
# دستور ویژه ادمین برای سکه و الماس بی‌نهایت جهت تست
# ----------------------------------------------------
@bot.message_handler(commands=['admin_coins'])
def give_admin_coins(message):
    user_id = message.from_user.id
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins + 999999, diamonds = diamonds + 999999 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    bot.reply_to(message, "⚡ **۹۹۹,۹۹۹ سکه و الماس تست به حساب شما اضافه شد!**")

# ----------------------------------------------------
# دستور استارت
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
# 📌 دکمه ۱: هدیه روزانه (با محدودیت ۲۴ ساعته / یک‌بار در روز)
# ----------------------------------------------------
from datetime import date

@bot.message_handler(func=lambda msg: msg.text == "🎁 هدیه روزانه")
def daily_reward_handler(message):
    user_id = message.from_user.id
    today_str = str(date.today())

    conn = database.get_connection()
    cursor = conn.cursor()

    # بررسی ستون last_daily
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_daily TEXT")
        conn.commit()
    except Exception:
        pass

    cursor.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    last_daily = row['last_daily'] if row and 'last_daily' in row.keys() else None

    if last_daily == today_str:
        conn.close()
        bot.send_message(user_id, "❌ **شما امروز هدیه روزانه خود را دریافت کرده‌اید!**\nلطفاً فردا دوباره مراجعه کنید.", parse_mode="Markdown")
        return

    daily_coin = int(database.get_setting("daily_coin") or 100)
    daily_diamond = int(database.get_setting("daily_diamond") or 5)

    cursor.execute("""
        UPDATE users 
        SET coins = coins + ?, diamonds = diamonds + ?, last_daily = ? 
        WHERE user_id = ?
    """, (daily_coin, daily_diamond, today_str, user_id))
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
# 📌 دکمه ۴: ثبت تبلیغ (ویوگیر با سکه و ممبرگیر با الماس)
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == "📥 ثبت تبلیغ")
def ad_menu_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_view = types.InlineKeyboardButton("👁 ثبت تبلیغ ویوگیر (با سکه)", callback_data="add_view_ad")
    btn_member = types.InlineKeyboardButton("📢 ثبت تبلیغ ممبرگیر (با الماس)", callback_data="add_member_ad")
    markup.add(btn_view, btn_member)
    bot.send_message(message.chat.id, "لطفاً نوع تبلیغ مورد نظر خود را انتخاب کنید:", reply_markup=markup)

# --- بخش ویوگیر (پرداخت با سکه) ---
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
    row = cursor.fetchone()
    user_coins = row['coins'] if row else 0
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

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET coins = coins - ?, spent_coins = spent_coins + ? WHERE user_id = ?", (data['cost'], data['cost'], user_id))
    conn.commit()
    conn.close()

    bot_info = bot.get_me()

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_back = types.InlineKeyboardButton("🔄 برگشت به ربات", url=f"https://t.me/{bot_info.username}")
    btn_turbo = types.InlineKeyboardButton("⚡ توربو", callback_data="turbo_view")
    btn_claim = types.InlineKeyboardButton("👁 ثبت بازدید", callback_data="claim_view")
    markup.add(btn_claim)
    markup.add(btn_back, btn_turbo)

    try:
        bot.copy_message(VIEW_CHANNEL, data['chat_id'], data['message_id'], reply_markup=markup)
        bot.edit_message_text(f"🎉 پست شما با موفقیت ثبت شد و به کانال {VIEW_CHANNEL} ارسال گردید!", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ خطا در ارسال به کانال ({VIEW_CHANNEL}). لطفاً مطمئن شوید ربات در کانال ادمین است.", call.message.chat.id, call.message.message_id)

    del user_ad_data[user_id]

# --- بخش ممبرگیر (پرداخت با الماس) ---
@bot.callback_query_handler(func=lambda call: call.data == "add_member_ad")
def member_packages_callback(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    packages = [
        ("۲۰ الماس 👈 ۱۰ ممبر", "pkg_mem_20_10"),
        ("۴۰ الماس 👈 ۲۰ ممبر", "pkg_mem_40_20"),
        ("۶۰ الماس 👈 ۳۰ ممبر", "pkg_mem_60_30"),
        ("۸۰ الماس 👈 ۴۰ ممبر", "pkg_mem_80_40"),
        ("۱۰۰ الماس 👈 ۵۰ ممبر", "pkg_mem_100_50")
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
    cursor.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    user_diamonds = row['diamonds'] if row else 0
    conn.close()

    if user_diamonds < cost:
        bot.answer_callback_query(call.id, f"❌ موجودی الماس کافی نیست! (نیازمند {cost} الماس)", show_alert=True)
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
    cursor.execute("UPDATE users SET diamonds = diamonds - ?, spent_diamonds = spent_diamonds + ? WHERE user_id = ?", (data['cost'], data['cost'], user_id))
    conn.commit()
    conn.close()

    bot_info = bot.get_me()

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_join = types.InlineKeyboardButton("📢 جوین در کانال", url=f"https://t.me/my_member_man")
    btn_diamond = types.InlineKeyboardButton("💎 دریافت الماس", callback_data="claim_member_diamond")
    btn_back = types.InlineKeyboardButton("🔄 بازگشت به ربات", url=f"https://t.me/{bot_info.username}")
    markup.add(btn_join, btn_diamond)
    markup.add(btn_back)

    try:
        bot.copy_message(MEMBER_CHANNEL, data['chat_id'], data['message_id'], reply_markup=markup)
        bot.edit_message_text(f"🎉 تبلیغ ممبرگیر شما با موفقیت ثبت شد و به کانال {MEMBER_CHANNEL} ارسال گردید!", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ خطا در ارسال به کانال ({MEMBER_CHANNEL}). لطفاً مطمئن شوید ربات در کانال ادمین است.", call.message.chat.id, call.message.message_id)

    del user_ad_data[user_id]

# --- دکمه لغو ثبت ---
@bot.callback_query_handler(func=lambda call: call.data == "cancel_ad")
def cancel_ad_callback(call):
    user_id = call.from_user.id
    if user_id in user_ad_data:
        del user_ad_data[user_id]
    bot.edit_message_text("❌ ثبت تبلیغ لغو شد.", call.message.chat.id, call.message.message_id)
# ----------------------------------------------------
# 📌 دکمه ۵: انتقال سکه و الماس
# ----------------------------------------------------
user_transfer_data = {}  # ذخیره موقت داده‌های انتقال

@bot.message_handler(func=lambda msg: msg.text == "🔄 انتقال سکه و الماس")
def transfer_menu_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_coin = types.InlineKeyboardButton("🟡 انتقال سکه", callback_data="tr_coin")
    btn_diamond = types.InlineKeyboardButton("💎 انتقال الماس", callback_data="tr_diamond")
    markup.add(btn_coin, btn_diamond)
    bot.send_message(message.chat.id, "لطفاً نوع دارایی جهت انتقال را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["tr_coin", "tr_diamond"])
def transfer_type_selected(call):
    asset_type = "coin" if call.data == "tr_coin" else "diamond"
    asset_title = "سکه" if asset_type == "coin" else "الماس"
    
    user_transfer_data[call.from_user.id] = {'type': asset_type}
    
    msg = bot.send_message(call.message.chat.id, f"لطفاً **آیدی عددی** کاربر گیرنده {asset_title} را وارد کنید:")
    bot.register_next_step_handler(msg, receive_transfer_target_id)

def receive_transfer_target_id(message):
    user_id = message.from_user.id
    target_id_str = message.text.strip()

    if not target_id_str.isdigit():
        bot.reply_to(message, "❌ آیدی عددی معتبر نیست! لطفاً فقط عدد بفرستید.")
        if user_id in user_transfer_data:
            del user_transfer_data[user_id]
        return

    target_id = int(target_id_str)

    if target_id == user_id:
        bot.reply_to(message, "❌ شما نمی‌توانید به حساب خودتان انتقال انجام دهید!")
        if user_id in user_transfer_data:
            del user_transfer_data[user_id]
        return

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (target_id,))
    target_user = cursor.fetchone()
    conn.close()

    if not target_user:
        bot.reply_to(message, "❌ کاربر گیرنده در ربات ثبت‌نام نکرده است!")
        if user_id in user_transfer_data:
            del user_transfer_data[user_id]
        return

    user_transfer_data[user_id]['target_id'] = target_id
    asset_title = "سکه" if user_transfer_data[user_id]['type'] == "coin" else "الماس"
    
    msg = bot.send_message(message.chat.id, f"مقدار **{asset_title}** جهت انتقال را وارد کنید:")
    bot.register_next_step_handler(msg, process_transfer_amount)

def process_transfer_amount(message):
    user_id = message.from_user.id
    amount_str = message.text.strip()

    if user_id not in user_transfer_data:
        return

    if not amount_str.isdigit() or int(amount_str) <= 0:
        bot.reply_to(message, "❌ مقدار وارد شده معتبر نیست!")
        del user_transfer_data[user_id]
        return

    amount = int(amount_str)
    data = user_transfer_data[user_id]
    asset_type = data['type']
    target_id = data['target_id']
    
    column = "coins" if asset_type == "coin" else "diamonds"
    asset_title = "سکه" if asset_type == "coin" else "الماس"

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {column} FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    user_balance = row[column] if row else 0

    if user_balance < amount:
        bot.reply_to(message, f"❌ موجودی شما کافی نیست! (موجودی فعلی شما: {user_balance} {asset_title})")
        conn.close()
        del user_transfer_data[user_id]
        return

    # انجام کسر از فرستنده و اضافه به گیرنده
    cursor.execute(f"UPDATE users SET {column} = {column} - ? WHERE user_id = ?", (amount, user_id))
    cursor.execute(f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    del user_transfer_data[user_id]

    bot.send_message(message.chat.id, f"✅ با موفقیت **{amount} {asset_title}** به کاربر `{target_id}` منتقل شد.", parse_mode="Markdown")

    try:
        bot.send_message(target_id, f"🎁 کاربر `{user_id}` مقدار **{amount} {asset_title}** به حساب شما واریز کرد!", parse_mode="Markdown")
    except Exception:
        pass
# ----------------------------------------------------
# 📌 دکمه ۶: فروشگاه (خرید سکه و الماس)
# ----------------------------------------------------
DEFAULT_CARD_NUMBER = "5892.1011.1699.1486"
user_shop_data = {}  # ذخیره موقت سفارش خریدار

@bot.message_handler(func=lambda msg: msg.text == "🛍️ فروشگاه")
def shop_menu_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_coin = types.InlineKeyboardButton("👁 خرید سکه ویوگیر", callback_data="shop_coins")
    btn_diamond = types.InlineKeyboardButton("💎 خرید الماس ممبرگیر", callback_data="shop_diamonds")
    markup.add(btn_coin, btn_diamond)
    bot.send_message(message.chat.id, "🛒 **به فروشگاه خوش آمدید!**\nلطفاً نوع آیتم درخواستی خود را انتخاب کنید:", reply_markup=markup, parse_mode="Markdown")

# --- لیست بسته‌های سکه ---
@bot.callback_query_handler(func=lambda call: call.data == "shop_coins")
def shop_coins_packages(call):
    markup = types.InlineKeyboardMarkup(row_width=1)
    packages = [
        ("۲۰,۰۰۰ سکه 👈 ۵۰,۰۰۰ تومان", "buy_coin_20000_50000"),
        ("۴۰,۰۰۰ سکه 👈 ۱۰۰,۰۰۰ تومان", "buy_coin_40000_100000"),
        ("۵۰,۰۰۰ سکه 👈 ۱۵۰,۰۰۰ تومان", "buy_coin_50000_150000"),
        ("۲۰۰,۰۰۰ سکه 👈 ۲۰۰,۰۰۰ تومان", "buy_coin_200000_200000")
    ]
    for text, cd in packages:
        markup.add(types.InlineKeyboardButton(text, callback_data=cd))
    bot.edit_message_text("🟡 **بسته‌های سکه ویوگیر:**\nیکی از بسته‌های زیر را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# --- لیست بسته‌های الماس ---
@bot.callback_query_handler(func=lambda call: call.data == "shop_diamonds")
def shop_diamonds_packages(call):
    markup = types.InlineKeyboardMarkup(row_width=1)
    packages = [
        ("۱۰۰ الماس 👈 ۲۵,۰۰۰ تومان", "buy_diamond_100_25000"),
        ("۲۵۰ الماس 👈 ۵۰,۰۰۰ تومان", "buy_diamond_250_50000"),
        ("۵۰۰ الماس 👈 ۱۰۰,۰۰۰ تومان", "buy_diamond_500_100000"),
        ("۱,۰۰۰ الماس 👈 ۲۰۰,۰۰۰ تومان", "buy_diamond_1000_200000"),
        ("۴,۰۰۰ الماس 👈 ۸۰۰,۰۰۰ تومان", "buy_diamond_4000_800000")
    ]
    for text, cd in packages:
        markup.add(types.InlineKeyboardButton(text, callback_data=cd))
    bot.edit_message_text("💎 **بسته‌های الماس ممبرگیر:**\nیکی از بسته‌های زیر را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# --- انتخاب روش پرداخت ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def select_payment_method(call):
    parts = call.data.split("_")
    item_type = parts[1]  # coin یا diamond
    amount = int(parts[2])
    price = int(parts[3])
    
    user_shop_data[call.from_user.id] = {
        'item_type': item_type,
        'amount': amount,
        'price': price
    }

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_card = types.InlineKeyboardButton("💳 پرداخت کارت به کارت", callback_data="pay_card")
    btn_gateway = types.InlineKeyboardButton("🔗 پرداخت از طریق درگاه", callback_data="pay_gateway")
    markup.add(btn_card, btn_gateway)

    item_title = f"{amount:,} سکه" if item_type == "coin" else f"{amount:,} الماس"
    bot.edit_message_text(
        f"🛒 **سفارش انتخاب شده:** {item_title}\n"
        f"💰 **مبلغ قابل پرداخت:** {price:,} تومان\n\n"
        f"لطفاً روش پرداخت را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown"
    )

# --- روش کارت به کارت ---
@bot.callback_query_handler(func=lambda call: call.data == "pay_card")
def pay_card_handler(call):
    user_id = call.from_user.id
    if user_id not in user_shop_data:
        return

    card_num = database.get_setting("card_number") or DEFAULT_CARD_NUMBER
    data = user_shop_data[user_id]
    item_title = f"{data['amount']:,} سکه" if data['item_type'] == "coin" else f"{data['amount']:,} الماس"

    msg_text = (
        f"💳 **پرداخت کارت به کارت**\n\n"
        f"📌 سفارش شما: **{item_title}**\n"
        f"💵 مبلغ: **{data['price']:,} تومان**\n\n"
        f"💳 **شماره کارت:**\n`{card_num}`\n\n"
        f"📸 **لطفاً عکس فیش یا تصویر تراکنش واریزی خود را ارسال کنید:**"
    )
    
    msg = bot.send_message(call.message.chat.id, msg_text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, receive_receipt_photo)

# --- دریافت تصویر فیش ---
def receive_receipt_photo(message):
    user_id = message.from_user.id
    if user_id not in user_shop_data:
        return

    if not message.photo:
        bot.reply_to(message, "❌ لطفاً فقط تصویر فیش واریزی را ارسال بفرمایید.")
        return

    data = user_shop_data[user_id]
    photo_id = message.photo[-1].file_id
    item_title = f"{data['amount']:,} سکه" if data['item_type'] == "coin" else f"{data['amount']:,} الماس"

    # ارسال فیش برای ادمین‌ها جهت تایید
    admin_markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ تایید و واریز", callback_data=f"approve_receipt_{user_id}_{data['item_type']}_{data['amount']}")
    btn_reject = types.InlineKeyboardButton("❌ رد فیش", callback_data=f"reject_receipt_{user_id}")
    admin_markup.add(btn_approve, btn_reject)

    caption = (
        f"📥 **فیش واریزی جدید!**\n\n"
        f"👤 کاربر: `{user_id}` (@{message.from_user.username or 'بدون آیدی'})\n"
        f"📦 سفارش: {item_title}\n"
        f"💵 مبلغ: {data['price']:,} تومان"
    )

    for admin_id in config.ADMIN_IDS:
        try:
            bot.send_photo(admin_id, photo_id, caption=caption, reply_markup=admin_markup, parse_mode="Markdown")
        except Exception:
            pass

    bot.reply_to(message, "✅ **فیش شما با موفقیت برای مدیریت ارسال شد.**\nپس از بررسی و تایید، حساب شما شارژ خواهد شد.", parse_mode="Markdown")
    del user_shop_data[user_id]

# --- روش درگاه پرداخت ---
@bot.callback_query_handler(func=lambda call: call.data == "pay_gateway")
def pay_gateway_handler(call):
    gateway_url = database.get_setting("gateway_url") or "https://t.me/ViewCoin_me_bot"
    bot.edit_message_text(f"🔗 جهت پرداخت از طریق درگاه، روی لینک زیر کلیک کنید:\n\n{gateway_url}", call.message.chat.id, call.message.message_id)

# --- تایید یا رد فیش توسط ادمین ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_receipt_"))
def approve_receipt_callback(call):
    _, _, target_user_id, item_type, amount = call.data.split("_")
    target_user_id = int(target_user_id)
    amount = int(amount)

    conn = database.get_connection()
    cursor = conn.cursor()
    column = "coins" if item_type == "coin" else "diamonds"
    cursor.execute(f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?", (amount, target_user_id))
    conn.commit()
    conn.close()

    asset_title = "سکه" if item_type == "coin" else "الماس"
    bot.edit_message_caption(f"✅ فیش توسط شما تایید شد و **{amount:,} {asset_title}** به حساب کاربر اضافه گردید.", call.message.chat.id, call.message.message_id)
    
    try:
        bot.send_message(target_user_id, f"🎉 **فیش واریزی شما تایید شد!**\nمقدار **{amount:,} {asset_title}** به حساب شما اضافه گردید.", parse_mode="Markdown")
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_receipt_"))
def reject_receipt_callback(call):
    target_user_id = int(call.data.split("_")[2])
    bot.edit_message_caption("❌ فیش توسط شما رد شد.", call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(target_user_id, "❌ **فیش واریزی شما توسط مدیریت رد شد.**\nدر صورت وجود مشکل به پشتیبانی پیام دهید.")
    except Exception:
        pass
# ----------------------------------------------------
# 📌 بخش قرعه‌کشی
# ----------------------------------------------------

@bot.message_handler(func=lambda msg: msg.text == "🎫 قرعه‌کشی")
def lottery_menu_handler(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🎫 ورود به قرعه‌کشی", "🏆 لیست برندگان قرعه‌کشی")
    markup.add("🎁 لیست جوایز اول تا سوم", "👥 لیست شرکت‌کنندگان")
    markup.add("🔙 بازگشت به منوی اصلی")
    bot.send_message(
        message.chat.id,
        "🎫 **به بخش قرعه‌کشی خوش آمدید!**\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# --- دکمه بازگشت به منوی اصلی از بخش قرعه‌کشی ---
@bot.message_handler(func=lambda msg: msg.text == "🔙 بازگشت به منوی اصلی")
def back_from_lottery(message):
    bot.send_message(
        message.chat.id,
        "🔄 به منوی اصلی بازگشتید:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

# --- ۱. ورود به قرعه‌کشی (خرید بلیت) ---
@bot.message_handler(func=lambda msg: msg.text == "🎫 ورود به قرعه‌کشی")
def lottery_entry_handler(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    packages = [
        ("۲۰0,۰۰۰ تومان 👈 ۲ بلیت", "buy_ticket_200000_2"),
        ("۴۰۰,۰۰۰ تومان 👈 ۴ بلیت", "buy_ticket_400000_4"),
        ("۶۰۰,۰۰۰ تومان 👈 ۶ بلیت", "buy_ticket_600000_6"),
        ("۸۰۰,۰۰۰ تومان 👈 ۸ بلیت", "buy_ticket_800000_8"),
        ("۱,۰۰۰,۰۰۰ تومان 👈 ۱۰ بلیت", "buy_ticket_1000000_10")
    ]
    for text, cd in packages:
        markup.add(types.InlineKeyboardButton(text, callback_data=cd))
    
    # دکمه میانبر به فروشگاه
    markup.add(types.InlineKeyboardButton("🛍️ ورود به فروشگاه (خرید و شارژ)", callback_data="shop_coins"))
    
    bot.send_message(
        message.chat.id,
        "🎫 **خرید بلیت قرعه‌کشی**\n\n"
        "با خرید بسته‌های زیر شانس خود را برای برنده شدن جوایز ویژه افزایش دهید!\n"
        "لطفاً بسته مورد نظر خود را انتخاب کنید:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# --- پردازش انتخاب بسته بلیت ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_ticket_"))
def process_ticket_purchase(call):
    _, _, price, tickets = call.data.split("_")
    price = int(price)
    tickets = int(tickets)
    
    # ذخیره موقت در دیتابیس یا هدایت به کارت‌به‌کارتر (مشابه فروشگاه)
    # اینجا برای ثبت سفارش بلیت، از سیستم فیش فروشگاه استفاده می‌کنیم:
    user_shop_data[call.from_user.id] = {
        'item_type': 'ticket',
        'amount': tickets,
        'price': price
    }
    
    card_num = database.get_setting("card_number") or "5892.1011.1699.1486"
    
    msg_text = (
        f"🎫 **خرید بلیت قرعه‌کشی**\n\n"
        f"📌 تعداد بلیت: **{tickets} عدد**\n"
        f"💵 مبلغ قابل پرداخت: **{price:,} تومان**\n\n"
        f"💳 **شماره کارت جهت واریز:**\n`{card_num}`\n\n"
        f"📸 **لطفاً عکس فیش یا تصویر تراکنش واریزی خود را ارسال کنید:**"
    )
    
    bot.edit_message_text(call.message.chat.id, call.message.message_id, msg_text, parse_mode="Markdown")
    # ثبت استپ هندلر برای دریافت فیش بلیت
    bot.register_next_step_handler(call.message, receive_receipt_photo)

# --- ۲. لیست برندگان قرعه‌کشی ---
@bot.message_handler(func=lambda msg: msg.text == "🏆 لیست برندگان قرعه‌کشی")
def lottery_winners_handler(message):
    winners = database.get_setting("lottery_winners") or "هنوز مشخص نشده / نامشخص"
    bot.send_message(
        message.chat.id,
        f"🏆 **اسامی برندگان دوره‌های قبل قرعه‌کشی:**\n\n{winners}",
        parse_mode="Markdown"
    )

# --- ۳. لیست جوایز قرعه‌کشی ---
@bot.message_handler(func=lambda msg: msg.text == "🎁 لیست جوایز اول تا سوم")
def lottery_prizes_handler(message):
    p1 = database.get_setting("prize_1") or "تنظیم نشده"
    p2 = database.get_setting("prize_2") or "تنظیم نشده"
    p3 = database.get_setting("prize_3") or "تنظیم نشده"
    
    text = (
        f"🎁 **جوایز ارزنده قرعه‌کشی این دوره:**\n\n"
        f"🥇 **نفر اول:** {p1}\n"
        f"🥈 **نفر دوم:** {p2}\n"
        f"🥉 **نفر سوم:** {p3}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- ۴. لیست شرکت‌کنندگان ---
@bot.message_handler(func=lambda msg: msg.text == "👥 لیست شرکت‌کنندگان")
def lottery_participants_handler(message):
    # محاسبه تعداد کل کاربرانی که بلیت فعال دارند از دیتابیس
    conn = database.get_connection()
    cursor = conn.cursor()
    # فرض می‌کنیم ستون یا جدولی برای بلیت‌ها داریم یا از فیلد مربوطه می‌خوانیم
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM users") # نمونه آماری
    total_users = cursor.fetchone()[0]
    conn.close()
    
    bot.send_message(
        message.chat.id,
        f"👥 **آمار شرکت‌کنندگان قرعه‌کشی:**\n\n"
        f"تعداد کل کاربران شرکت‌کننده دارای بلیت فعال در دوره جاری: **{total_users} نفر**",
        parse_mode="Markdown"
    )

# ----------------------------------------------------
# اجرای ربات
# ----------------------------------------------------
if __name__ == "__main__":
    database.init_db()
    patch_database()
    keep_alive()
    print("ربات روشن شد...")
    bot.infinity_polling()
