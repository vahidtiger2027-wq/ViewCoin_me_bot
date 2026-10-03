import os
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import config
import database
import keyboards

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

bot = telebot.TeleBot(config.BOT_TOKEN)
user_states = {}

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

def send_welcome_menu(user_id):
    is_admin = user_id in config.ADMIN_IDS
    welcome_text = database.get_setting("welcome_message") or "به ربات ممبرگیر و ویوگیر خوش آمدید!"
    markup = keyboards.main_menu_keyboard(is_admin=is_admin)
    bot.send_message(user_id, welcome_text, reply_markup=markup)

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
            cursor.execute("UPDATE users SET coins = coins + ?, diamonds = diamonds + ? WHERE user_id = ?", (ref_coin, ref_diamond, referrer_id))
            conn.commit()
            try:
                bot.send_message(referrer_id, f"🎉 کاربر جدیدی با لینک شما وارد شد!\n🎁 پاداش شما: {ref_coin} سکه و {ref_diamond} الماس")
            except Exception:
                pass
    conn.close()

    not_joined = check_sponsorship(user_id)
    if not_joined:
        markup = types.InlineKeyboardMarkup()
        for idx, (link, _) in enumerate(not_joined, 1):
            markup.add(types.InlineKeyboardButton(f"📢 عضویت در کانال {idx}", url=link))
        markup.add(types.InlineKeyboardButton("✅ عضو شدم / تایید", callback_data="check_join"))
        bot.send_message(user_id, "⚠️ جهت استفاده از امکانات ربات، ابتدا باید در کانال‌های زیر عضو شوید:", reply_markup=markup)
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

# --- 👤 حساب کاربری ---
@bot.message_handler(func=lambda msg: msg.text == "👤 حساب کاربری")
def profile_handler(message):
    user_id = message.from_user.id
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins, diamonds, tickets, joined_at FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as ref_count FROM users WHERE referrer_id = ?", (user_id,))
    ref_count = cursor.fetchone()['ref_count']
    conn.close()

    if user:
        joined_date = user['joined_at'].split()[0] if user['joined_at'] else "نامشخص"
        text = (
            f"👤 **حساب کاربری شما**\n\n"
            f"🆔 **شناسه عددی:** `{user_id}`\n"
            f"🟡 **موجودی سکه:** {user['coins']}\n"
            f"💎 **موجودی الماس:** {user['diamonds']}\n"
            f"🎟 **بلیت‌های قرعه‌کشی:** {user['tickets']}\n"
            f"👥 **تعداد زیرمجموعه‌ها:** {ref_count} نفر\n"
            f"📅 **تاریخ عضویت:** {joined_date}"
        )
        bot.send_message(user_id, text, parse_mode="Markdown")

# --- 🛒 فروشگاه ---
@bot.message_handler(func=lambda msg: msg.text == "🛒 فروشگاه")
def shop_handler(message):
    card_number = database.get_setting("card_number") or "ثبت نشده"
    shop_text = (
        "🛒 **فروشگاه سکه و الماس**\n\n"
        "برای خرید هر بسته، مبلغ مربوطه را به شماره کارت زیر واریز کرده و به پشتیبانی پیام دهید:\n\n"
        "📦 **بسته‌های سکه:**\n"
        "▫️ بسته ۱: ۵۰۰ سکه ➔ ۲۵,۰۰۰ تومان\n"
        "▫️ بسته ۲: ۱,۰۰۰ سکه ➔ ۴۵,۰۰۰ تومان\n"
        "▫️ بسته ۳: ۲,۵۰۰ سکه ➔ ۱۰۰,۰۰۰ تومان\n"
        "▫️ بسته ۴: ۵,۰۰۰ سکه ➔ ۱۸۰,۰۰۰ تومان\n"
        "▫️ بسته ۵: ۱۰,۰۰۰ سکه ➔ ۳۲۰,۰۰۰ تومان\n\n"
        "💎 **بسته‌های الماس:**\n"
        "▫️ بسته ۱: ۱۰ الماس ➔ ۱۵,۰۰۰ تومان\n"
        "▫️ بسته ۲: ۲۵ الماس ➔ ۳۰,۰۰۰ تومان\n"
        "▫️ بسته ۳: ۵۰ الماس ➔ ۵۵,۰۰۰ تومان\n"
        "▫️️ بسته ۴: ۱۰۰ الماس ➔ ۱۰۰,۰۰۰ تومان\n"
        "▫️ بسته ۵: ۲۵۰ الماس ➔ ۲۲۰,۰۰۰ تومان\n\n"
        f"💳 **شماره کارت جهت واریز:**\n`{card_number}`"
    )
    bot.send_message(message.chat.id, shop_text, parse_mode="Markdown")

# --- 👁‍‍🗨 ثبت سفارش (دکمه‌های شیشه‌ای تفکیک‌شده) ---
@bot.message_handler(func=lambda msg: msg.text == "👁‍🗨 ثبت سفارش ویو و ممبر")
def order_start(message):
    bot.send_message(
        message.chat.id,
        "👁‍🗨 **ثبت سفارش جدید**\n\nلطفاً نوع خدمت درخواستی خود را انتخاب کنید:",
        reply_markup=keyboards.order_type_keyboard(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("order_type_"))
def order_type_selected(call):
    service_type = call.data.replace("order_type_", "")
    title = "بازدید (ویو)" if service_type == "view" else "اعضا (ممبر)"
    bot.edit_message_text(
        f"📦 **لیست بسته‌های {title}**\n\nلطفاً یکی از بسته‌های زیر را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboards.order_packages_keyboard(service_type),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("pkg_"))
def package_selected(call):
    parts = call.data.split("_")
    service_type = parts[1]
    amount = int(parts[2])
    cost = int(parts[3])
    user_id = call.from_user.id

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    user_coins = cursor.fetchone()['coins']
    conn.close()

    if user_coins < cost:
        bot.answer_callback_query(call.id, f"❌ موجودی سکه شما کافی نیست! (نیاز به {cost} سکه داری، اما موجودیت {user_coins} سکه‌ست)", show_alert=True)
        return

    user_states[user_id] = {
        "step": "wait_link",
        "service_type": service_type,
        "amount": amount,
        "cost": cost
    }

    target_title = "لینک پست تلگرام" if service_type == "view" else "لینک عمومی یا آیدی کانال (مثلاً @channel)"
    bot.edit_message_text(
        f"✅ بسته انتخابی: **{amount} {'بازدید' if service_type == 'view' else 'ممبر'}**\n"
        f"💰 هزینه: **{cost} سکه**\n\n"
        f"🔗 لطفاً **{target_title}** خود را ارسال کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboards.cancel_inline_keyboard(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "wait_link")
def receive_order_link(message):
    user_id = message.from_user.id
    target_link = message.text.strip()
    state = user_states[user_id]

    service_type = state["service_type"]
    amount = state["amount"]
    cost = state["cost"]

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    user_coins = cursor.fetchone()['coins']

    if user_coins < cost:
        bot.send_message(user_id, "❌ موجودی سکه شما کافی نیست!")
        del user_states[user_id]
        conn.close()
        return

    cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (cost, user_id))
    cursor.execute("INSERT INTO orders (user_id, service_type, amount, cost, target_link) VALUES (?, ?, ?, ?, ?)",
                   (user_id, service_type, amount, cost, target_link))
    conn.commit()
    order_id = cursor.lastrowid
    conn.close()

    del user_states[user_id]

    service_name = "بازدید" if service_type == "view" else "ممبر"
    success_text = (
        f"🎉 **سفارش شما با موفقیت ثبت شد!**\n\n"
        f"🆔 **کد پیگیری:** `{order_id}`\n"
        f"📌 **نوع سفارش:** {service_name}\n"
        f"🔢 **تعداد:** {amount}\n"
        f"💳 **سکه‌ی کسر شده:** {cost}\n"
        f"🔗 **لینک ثبت شده:** {target_link}\n\n"
        f"⚡ سفارش شما به زودی پردازش و اعمال خواهد شد."
    )
    bot.send_message(user_id, success_text, parse_mode="Markdown")

# --- 👥 زیرمجموعه‌گیری ---
@bot.message_handler(func=lambda msg: msg.text == "👥 زیرمجموعه‌گیری")
def referral_handler(message):
    user_id = message.from_user.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_coin = database.get_setting("referral_coin") or "0"
    ref_diamond = database.get_setting("referral_diamond") or "0"

    text = (
        f"👥 **سیستم زیرمجموعه‌گیری**\n\n"
        f"با دعوت دوستان خود به ربات پاداش بگیرید!\n\n"
        f"🎁 **پاداش هر دعوت:**\n"
        f"🟡 {ref_coin} سکه\n"
        f"💎 {ref_diamond} الماس\n\n"
        f"🔗 **لینک اختصاصی شما:**\n`{ref_link}`"
    )
    bot.send_message(user_id, text, parse_mode="Markdown")

# --- 🎁 هدیه روزانه ---
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

    bot.send_message(user_id, f"🎉 **هدیه روزانه دریافت شد!**\n\n🟡 {daily_coin} سکه\n💎 {daily_diamond} الماس\nبه حساب شما اضافه شد.")

# --- 🏆 قرعه‌کشی ---
@bot.message_handler(func=lambda msg: msg.text == "🏆 ورود به قرعه‌کشی")
def lottery_handler(message):
    status = database.get_setting("lottery_status") or "off"
    if status == "off":
        bot.send_message(message.chat.id, "❌ در حال حاضر قرعه‌کشی فعال نیست.")
    else:
        p1 = database.get_setting("lottery_prize_1") or "ثبت نشده"
        p2 = database.get_setting("lottery_prize_2") or "ثبت نشده"
        p3 = database.get_setting("lottery_prize_3") or "ثبت نشده"
        text = f"🏆 **قرعه‌کشی فعال است!**\n\n🥇 نفر اول: {p1}\n🥈 نفر دوم: {p2}\n🥉 نفر سوم: {p3}"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- 🔄 انتقال سکه و الماس ---
@bot.message_handler(func=lambda msg: msg.text == "🔄 انتقال سکه و الماس")
def transfer_start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🟡 انتقال سکه", callback_data="tr_type_coin"),
        types.InlineKeyboardButton("💎 انتقال الماس", callback_data="tr_type_diamond")
    )
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_action"))
    bot.send_message(message.chat.id, "🔄 لطفاً نوع دارایی جهت انتقال را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("tr_type_"))
def transfer_select_type(call):
    asset_type = call.data.replace("tr_type_", "")
    user_states[call.from_user.id] = {"step": "wait_target", "type": asset_type}
    asset_title = "سکه" if asset_type == "coin" else "الماس"
    bot.edit_message_text(
        f"آیتم انتخابی: **{asset_title}**\n\nلطفاً **شناسه عددی (ID)** کاربر مقصد را بفرستید:",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=keyboards.cancel_inline_keyboard()
    )

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "wait_target")
def transfer_get_target(message):
    user_id = message.from_user.id
    target_id_str = message.text.strip()
    if not target_id_str.isdigit():
        bot.reply_to(message, "❌ شناسه عددی معتبر نیست!")
        return
    target_id = int(target_id_str)
    if target_id == user_id:
        bot.reply_to(message, "❌ نمی‌توانید به خودتان منتقل کنید!")
        return
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (target_id,))
    target_exists = cursor.fetchone()
    conn.close()
    if not target_exists:
        bot.reply_to(message, "❌ کاربر مقصد در ربات یافت نشد.")
        return
    user_states[user_id]["target_id"] = target_id
    user_states[user_id]["step"] = "wait_amount"
    asset_title = "سکه" if user_states[user_id]["type"] == "coin" else "الماس"
    bot.send_message(message.chat.id, f"✅ کاربر تأیید شد (`{target_id}`).\n\nتعداد **{asset_title}** را وارد کنید:", parse_mode="Markdown", reply_markup=keyboards.cancel_inline_keyboard())

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "wait_amount")
def transfer_get_amount(message):
    user_id = message.from_user.id
    amount_str = message.text.strip()
    if not amount_str.isdigit() or int(amount_str) <= 0:
        bot.reply_to(message, "❌ عدد وارد شده معتبر نیست.")
        return
    amount = int(amount_str)
    state = user_states[user_id]
    asset_type = state["type"]
    target_id = state["target_id"]
    column = "coins" if asset_type == "coin" else "diamonds"
    asset_title = "سکه" if asset_type == "coin" else "الماس"

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {column} FROM users WHERE user_id = ?", (user_id,))
    user_balance = cursor.fetchone()[column]
    if user_balance < amount:
        bot.reply_to(message, f"❌ موجودی کافی نیست! (موجودی شما: {user_balance} {asset_title})")
        conn.close()
        return

    cursor.execute(f"UPDATE users SET {column} = {column} - ? WHERE user_id = ?", (amount, user_id))
    cursor.execute(f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()
    del user_states[user_id]

    bot.send_message(message.chat.id, f"✅ با موفقیت {amount} {asset_title} به کاربر `{target_id}` منتقل شد.", parse_mode="Markdown")

# --- ⚙️ پنل مدیریت ---
@bot.message_handler(func=lambda msg: msg.text == "⚙️ پنل مدیریت")
def admin_panel_handler(message):
    if message.from_user.id in config.ADMIN_IDS:
        markup = keyboards.admin_panel_keyboard()
        bot.send_message(message.chat.id, "⚙️ به **پنل مدیریت** خوش آمدید:", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "📊 آمار ربات")
def admin_stats(message):
    if message.from_user.id in config.ADMIN_IDS:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total_orders FROM orders")
        total_orders = cursor.fetchone()['total_orders']
        conn.close()
        
        bot.send_message(message.chat.id, f"📊 **آمار ربات:**\n\n👥 کل کاربران: {total_users} نفر\n📦 کل سفارشات: {total_orders} عدد", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "🔙 بازگشت به منوی اصلی")
def back_to_main_handler(message):
    send_welcome_menu(message.from_user.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_action")
def cancel_callback(call):
    if call.from_user.id in user_states:
        del user_states[call.from_user.id]
    bot.answer_callback_query(call.id, "عملیات لغو شد.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == "__main__":
    database.init_db()
    keep_alive()
    print("ربات به‌طور کامل و بدون ایراد فعال شد...")
    bot.infinity_polling()
