import os
import sqlite3
import datetime
import logging
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864400306:AAHsgcfH1GdWzJARqMxnX8ABMWBYWFH4Rn4")
PORT = int(os.environ.get("PORT", 10000))
ADMIN_ID = 5412332176  # آیدی ادمین اصلی

VIEW_CHANNEL = os.environ.get("VIEW_CHANNEL", "@my_view_chan")
MEMBER_CHANNEL = os.environ.get("MEMBER_CHANNEL", "@my_member_chan")

CARD_NUMBER = os.environ.get("CARD_NUMBER", "تنظیم نشده (جهت تنظیم به مدیریت مراجعه کنید)")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://t.me/Admin_ID")

logging.basicConfig(level=logging.INFO)

# ----------------- HEALTH CHECK SERVER -----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
    server.serve_forever()

# ----------------- DATABASE -----------------
DB_FILE = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        coin_view INTEGER DEFAULT 0,
        coin_member INTEGER DEFAULT 0,
        ref_count INTEGER DEFAULT 0,
        last_daily TEXT,
        admin_gift INTEGER DEFAULT 0,
        total_views INTEGER DEFAULT 0,
        today_views INTEGER DEFAULT 0,
        lottery_wins INTEGER DEFAULT 0,
        ref_commission INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_clicks (
        user_id INTEGER,
        target_id TEXT,
        PRIMARY KEY (user_id, target_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS post_views (
        post_id TEXT PRIMARY KEY,
        view_count INTEGER DEFAULT 0
    )''')

    # جدول تنظیمات قرعه‌کشی
    c.execute('''CREATE TABLE IF NOT EXISTS lottery_settings (
        id INTEGER PRIMARY KEY,
        is_active INTEGER DEFAULT 1,
        prize_1 TEXT DEFAULT '50,000 سکه ویو',
        prize_2 TEXT DEFAULT '30,000 سکه ویo',
        prize_3 TEXT DEFAULT '10,000 سکه ویو',
        draw_date TEXT DEFAULT 'پایان هر ماه'
    )''')
    
    c.execute("INSERT OR IGNORE INTO lottery_settings (id, is_active) VALUES (1, 1)")
    conn.commit()
    conn.close()

init_db()

def get_or_create_user(user_id, username="", referrer_id=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT user_id, username, coin_view, coin_member, ref_count, last_daily, 
                        admin_gift, total_views, today_views, lottery_wins, ref_commission, tickets 
                 FROM users WHERE user_id=?""", (user_id,))
    u = c.fetchone()
    if not u:
        c.execute("""INSERT INTO users 
            (user_id, username, coin_view, coin_member, ref_count, last_daily, admin_gift, total_views, today_views, lottery_wins, ref_commission, referrer_id, tickets) 
            VALUES (?, ?, 0, 0, 0, '', 0, 0, 0, 0, 0, ?, 0)""", (user_id, username, referrer_id))
        conn.commit()
        
        if referrer_id and referrer_id != user_id:
            c.execute("""UPDATE users 
                         SET coin_view = coin_view + 200, 
                             coin_member = coin_member + 50, 
                             ref_count = ref_count + 1 
                         WHERE user_id=?""", (referrer_id,))
            conn.commit()
            
        c.execute("""SELECT user_id, username, coin_view, coin_member, ref_count, last_daily, 
                            admin_gift, total_views, today_views, lottery_wins, ref_commission, tickets 
                     FROM users WHERE user_id=?""", (user_id,))
        u = c.fetchone()
    conn.close()
    return u

def get_lottery_settings():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_active, prize_1, prize_2, prize_3, draw_date FROM lottery_settings WHERE id=1")
    s = c.fetchone()
    conn.close()
    return s

# محاسبه بلیت بر اساس مبلغ خرید (تومان)
def calculate_tickets(price):
    if price >= 500000:
        return 10
    elif price >= 200000:
        return 6
    elif price >= 100000:
        return 4
    elif price >= 50000:
        return 2
    return 0

# ----------------- KEYBOARDS -----------------
def main_keyboard():
    kb = [
        ["💎جم اوری سکه رایگان"],
        ["💻حصاب کار بری مشحصات", "👥جذب زیر مجموعه"],
        ["📥ثبت تبلیغ ویو گیر و ممبر گیر"],
        ["👨‍💻🛍︎فروشگاه", "دکمه قرعه کشی"],
        ["💰 انتقال سکه", "💎︎  انتقال الماس"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def ads_keyboard():
    kb = [
        ["👁ثبت تبلیغ ویوگیر", "👥ثبت تبلیغ ممبر گیر"],
        ["بازگشت به منوی اصلی"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def shop_keyboard():
    kb = [
        ["👁خرید سکه ویوگیر", "👁خرید الماس ممبر گیر"],
        ["بازگشت به منوی اصلی"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- CONVERSATION STATES -----------------
WAIT_VIEW_POST, WAIT_VIEW_CONFIRM = 1, 2
WAIT_MEMBER_LINK, WAIT_MEMBER_CONFIRM = 3, 4
WAIT_RECEIPT_PHOTO = 5

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = 0
    if args and args[0].isdigit():
        referrer_id = int(args[0])

    get_or_create_user(user.id, user.username or "", referrer_id)
    await update.message.reply_text(f"سلام {user.first_name} عزیز، به ربات خوش آمدید!", reply_markup=main_keyboard())

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    u = get_or_create_user(user.id, user.username or "")

    if text == "💎جم اوری سکه رایگان":
        today_str = str(datetime.date.today())
        last_daily = u[5]
        
        if last_daily == today_str:
            await update.message.reply_text("❌ شما امروز سکه و الماس رایگان خود را دریافت کرده‌اید!\nلطفاً فردا مجدداً مراجعه کنید.")
        else:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""UPDATE users 
                         SET coin_view = coin_view + 20, 
                             coin_member = coin_member + 20, 
                             last_daily = ? 
                         WHERE user_id=?""", (today_str, user.id))
            conn.commit()
            conn.close()
            await update.message.reply_text("🎉 ۲۰ **سکه ویو** و ۲۰ **الماس ممبر** رایگان به حساب شما اضافه شد!", parse_mode="Markdown")

    elif text == "💻حصاب کار بری مشحصات":
        username_line = f"👤 **یوزرنیم:** @{u[1]}\n" if u[1] else ""
        
        msg = f"""💻 **مشخصات حساب کاربری شما:**

👤 **نام کاربری اکانت:** {user.first_name}
🆔 **آیدی:** `{u[0]}`
{username_line}
🎟 **تعداد بلیت‌های قرعه‌کشی شما:** {u[11]}
🎁 **هدیه مدیریت:** {u[6]}
👁 **بازدیدهای شما:** {u[7]}
📅 **بازدیدهای امروز:** {u[8]}
🏆 **جوایز:** {u[9]}
👥 **تعداد زیرمجموعه‌ها:** {u[4]}
💰 **پورسانت زیرمجموعه‌گیری:** {u[10]}

💰 **موجودی سکه شما:** {u[2]}
💎 **موجودی الماس شما:** {u[3]}"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "👥جذب زیر مجموعه":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        
        msg = f"""👥 **جذب زیرمجموعه و دریافت سکه رایگان**

🎉 با دعوت از هر دوست به ربات، **۲۰۰ سکه ویوگیر** و **۵۰ الماس ممبرگیر** دریافت کنید!

🔗 **لینک اختصاصی شما:**
`{ref_link}`

لینک بالا را برای دوستان خود بفرستید تا با ورود آن‌ها سکه و الماس رایگان بگیرید."""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "دکمه قرعه کشی":
        settings = get_lottery_settings()
        is_active = settings[0]

        if not is_active:
            await update.message.reply_text("❌ **قرعه‌کشی در حال حاضر غیرفعال می‌باشد.**\nلطفاً بعداً مراجعه کنید.")
            return

        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟 ورود به قرعه کشی", callback_data="lottery_enter")],
            [InlineKeyboardButton("🏆 نمایش برندگان قرعه کشی", callback_data="lottery_winners")]
        ])

        msg = f"""🎉 **به بخش قرعه‌کشی بزرگ ربات خوش آمدید!**

برای شرکت در قرعه‌کشی و شانس برنده شدن جوایز ویژه، کافیست از فروشگاه خرید کنید و بلیت شانس دریافت کنید!

🎟 **تعداد بلیت‌های فعلی شما:** {u[11]} عدد

یکی از گزینه‌های زیر را انتخاب کنید:"""
        await update.message.reply_text(msg, reply_markup=ikb, parse_mode="Markdown")

    elif text == "📥ثبت تبلیغ ویو گیر و ممبر گیر":
        await update.message.reply_text("لطفاً نوع تبلیغ مورد نظر خود را انتخاب کنید:", reply_markup=ads_keyboard())

    elif text == "👁ثبت تبلیغ ویوگیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("۴۰ سکه -> ۴۰ ویو", callback_data="v_40"), InlineKeyboardButton("۵۰ سکه -> ۵۰ ویو", callback_data="v_50")],
            [InlineKeyboardButton("۱۰۰ سکه -> ۱۰۰ ویو", callback_data="v_100"), InlineKeyboardButton("۲۰۰ سکه -> ۲۰۰ ویو", callback_data="v_200")]
        ])
        await update.message.reply_text("تعداد بازدید مورد نظر خود را انتخاب کنید:", reply_markup=ikb)

    elif text == "👥ثبت تبلیغ ممبر گیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("۲۰ سکه -> ۱۰ ممبر", callback_data="m_20"), InlineKeyboardButton("۴۰ سکه -> ۲۰ ممبر", callback_data="m_40")],
            [InlineKeyboardButton("۶۰ سکه -> ۳۰ ممبر", callback_data="m_60"), InlineKeyboardButton("۸۰ سکه -> ۴۰ ممبر", callback_data="m_80")],
            [InlineKeyboardButton("۱۰۰ سکه -> ۵۰ ممبر", callback_data="m_100")]
        ])
        await update.message.reply_text("تعداد ممبر مورد نظر خود را انتخاب کنید:", reply_markup=ikb)

    elif text == "👨‍💻🛍︎فروشگاه":
        await update.message.reply_text("به فروشگاه خوش آمدید! بخش مورد نظر را انتخاب کنید:", reply_markup=shop_keyboard())

    elif text == "👁خرید سکه ویوگیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("20.000 سکه ⚡️ 50.000 تومان (2 بلیت)", callback_data="buy_coin_20000_50000")],
            [InlineKeyboardButton("40.000 سکه ⚡️ 100.000 تومان (4 بلیت)", callback_data="buy_coin_40000_100000")],
            [InlineKeyboardButton("50.000 سکه ⚡️ 150.000 تومان (4 بلیت)", callback_data="buy_coin_50000_150000")],
            [InlineKeyboardButton("200.000 سکه ⚡️ 200.000 تومان (6 بلیت)", callback_data="buy_coin_200000_200000")]
        ])
        await update.message.reply_text("🛍 **پک‌های سکه ویوگیر:**\nلطفاً یکی از بسته‌های زیر را انتخاب کنید:", reply_markup=ikb)

    elif text == "👁خرید الماس ممبر گیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("100 الماس 💎 25.000 تومان", callback_data="buy_diamond_100_25000")],
            [InlineKeyboardButton("250 الماس 💎 50.000 تومان (2 بلیت)", callback_data="buy_diamond_250_50000")],
            [InlineKeyboardButton("500 الماس 💎 100.000 تومان (4 بلیت)", callback_data="buy_diamond_500_100000")],
            [InlineKeyboardButton("1000 الماس 💎 200.000 تومان (6 بلیت)", callback_data="buy_diamond_1000_200000")],
            [InlineKeyboardButton("4000 الماس 💎 800.000 تومان (10 بلیت)", callback_data="buy_diamond_4000_800000")]
        ])
        await update.message.reply_text("🛍 **پک‌های الماس ممبرگیر:**\nلطفاً یکی از بسته‌های زیر را انتخاب کنید:", reply_markup=ikb)

    elif text == "بازگشت به منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید.", reply_markup=main_keyboard())

# ----------------- LOTTERY CALLBACKS -----------------
async def handle_lottery_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "lottery_enter":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 ورود به فروشگاه", callback_data="goto_shop")]
        ])

        msg = """✨ **برای ورود به قرعه‌کشی بزرگ کافیست از فروشگاه خرید کنید:**

💵 **۵۰,۰۰۰ تومان خرید** ⬅️ دریافت **۲ بلیت**
💵 **۱۰۰,۰۰۰ تومان خرید** ⬅️ دریافت **۴ بلیت**
💵 **۲۰۰,۰۰۰ تومان خرید** ⬅️ دریافت **۶ بلیت**
💵 **۵۰۰,۰۰۰ تومان خرید** ⬅️ دریافت **۱۰ بلیت**

با هر خرید، بلیت‌های شما به‌صورت اتوماتیک ثبت و افزوده می‌شوند."""
        await query.message.reply_text(msg, reply_markup=ikb, parse_mode="Markdown")

    elif data == "lottery_winners":
        settings = get_lottery_settings()
        p1, p2, p3, draw_date = settings[1], settings[2], settings[3], settings[4]

        msg = f"""🏆 **جوایز این دوره قرعه‌کشی:**

🥇 **نفر اول:** {p1}
🥈 **نفر دوم:** {p2}
🥉 **نفر سوم:** {p3}

📅 **تاریخ برگزاری قرعه‌کشی:** {draw_date}

شما هم می‌توانید با خرید از فروشگاه و دریافت بلیت، یکی از برندگان ما باشید!"""
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "goto_shop":
        await query.message.reply_text("به بخش فروشگاه هدایت شدید:", reply_markup=shop_keyboard())

# ----------------- SHOP PAYMENT FLOW -----------------
async def select_buy_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    
    item_type = data[1]
    amount = int(data[2])
    price = int(data[3])

    context.user_data["buy_type"] = item_type
    context.user_data["buy_amount"] = amount
    context.user_data["buy_price"] = price

    unit_name = "سکه ویو" if item_type == "coin" else "الماس ممبر"
    tickets = calculate_tickets(price)

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 پرداخت کارت به کارت", callback_data="pay_card")],
        [InlineKeyboardButton("🔗 پرداخت از طریق درگاه", url=GATEWAY_URL)]
    ])

    ticket_text = f"\n🎟 **هدیه بلیت قرعه‌کشی:** {tickets} عدد بلیت" if tickets > 0 else ""

    await query.message.reply_text(
        f"🛒 **سفارش شما:** {amount:,} {unit_name}\n"
        f"💵 **مبلغ قابل پرداخت:** {price:,} تومان{ticket_text}\n\n"
        f"لطفاً روش پرداخت مورد نظر خود را انتخاب کنید:",
        reply_markup=ikb,
        parse_mode="Markdown"
    )

async def pay_card_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    amount = context.user_data.get("buy_amount")
    price = context.user_data.get("buy_price")
    item_type = context.user_data.get("buy_type")
    unit_name = "سکه ویو" if item_type == "coin" else "الماس ممبر"

    msg = f"""💳 **اطلاعات واریز کارت به کارت:**

📌 **شماره کارت:**
`{CARD_NUMBER}`

💵 **مبلغ:** {price:,} تومان
📦 **سفارش:** {amount:,} {unit_name}

⚠️ **توجه:** بعد از واریزی، **عکس تراکنش (فیش واریزی)** را همین حالا به ربات بفرستید."""

    await query.message.reply_text(msg, parse_mode="Markdown")
    return WAIT_RECEIPT_PHOTO

async def receive_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    user = update.effective_user
    amount = context.user_data.get("buy_amount")
    price = context.user_data.get("buy_price")
    item_type = context.user_data.get("buy_type")
    unit_name = "سکه ویو" if item_type == "coin" else "الماس ممبر"
    tickets = calculate_tickets(price)

    await update.message.reply_text("✅ فیش شما دریافت شد و برای مدیریت ارسال گردید.\nپس از بررسی و تایید، حساب شما شارژ خواهد شد.")

    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"approve_{user.id}_{item_type}_{amount}_{tickets}"),
            InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_{user.id}")
        ]
    ])

    admin_msg = f"""📥 **رسید واریزی جدید**

👤 کاربر: {user.first_name} (@{user.username or 'بدون آیدی'})
🆔 آیدی: `{user.id}`
📦 بسته: {amount:,} {unit_name}
💵 مبلغ: {price:,} تومان
🎟 بلیت تعلق‌گرفته: {tickets} عدد"""

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=admin_msg,
        reply_markup=admin_kb,
        parse_mode="Markdown"
    )

    return ConversationHandler.END

async def admin_payment_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action = data[0]

    if action == "approve":
        target_user_id = int(data[1])
        item_type = data[2]
        amount = int(data[3])
        tickets = int(data[4]) if len(data) > 4 else 0

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        if item_type == "coin":
            c.execute("UPDATE users SET coin_view = coin_view + ?, tickets = tickets + ? WHERE user_id=?", (amount, tickets, target_user_id))
            unit_name = "سکه ویو"
        else:
            c.execute("UPDATE users SET coin_member = coin_member + ?, tickets = tickets + ? WHERE user_id=?", (amount, tickets, target_user_id))
            unit_name = "الماس ممبر"
        conn.commit()
        conn.close()

        ticket_msg = f"\n🎟 تعداد {tickets} بلیت قرعه‌کشی نیز به حساب شما اضافه شد!" if tickets > 0 else ""

        await query.message.edit_caption(caption=query.message.caption + "\n\n✅ **تایید شد و حساب کاربر شارژ گردید.**", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **پرداخت شما تایید شد!**\nتعداد {amount:,} {unit_name} به حساب شما اضافه شد.{ticket_msg}"
            )
        except:
            pass

    elif action == "reject":
        target_user_id = int(data[1])
        await query.message.edit_caption(caption=query.message.caption + "\n\n❌ **درخواست لغو/رد شد.**", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ فیش واریزی شما توسط مدیریت تایید نشد."
            )
        except:
            pass

# ----------------- VIEW & MEMBER ADS CONVERSATIONS -----------------
async def start_view_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    cost = int(data.split("_")[1])
    user_id = query.from_user.id
    
    u = get_or_create_user(user_id)
    if u[2] < cost and user_id != ADMIN_ID:
        await query.message.reply_text(f"❌ موجودی سکه ویو شما کافی نیست! شما به {cost} سکه نیاز دارید.")
        return ConversationHandler.END

    context.user_data["view_cost"] = cost
    await query.message.reply_text("📩 **پست مورد نظر را بفرستید:**\n(پست می‌تواند حاوی متن، عکس، فیلم یا لینک باشد)")
    return WAIT_VIEW_POST

async def receive_view_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["view_message"] = update.message
    cost = context.user_data.get("view_cost")

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ثبت پست", callback_data="confirm_view_post")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_ads")]
    ])

    await update.message.reply_text(f"📋 **پیش‌نمایش سفارش ویوگیر**\n💰 هزینه: {cost} سکه\n👁 میزان ویو: {cost} بازدید\n\nآیا از ثبت این پست مطمئن هستید؟", reply_markup=ikb)
    return WAIT_VIEW_CONFIRM

async def confirm_view_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cost = context.user_data.get("view_cost")
    msg = context.user_data.get("view_message")
    bot_username = (await context.bot.get_me()).username

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET coin_view = coin_view - ? WHERE user_id=?", (cost, user_id))
    conn.commit()
    conn.close()

    bot_url = f"https://t.me/{bot_username}"

    try:
        sent_msg = await context.bot.copy_message(
            chat_id=VIEW_CHANNEL,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id
        )
        
        target_id = f"v_{sent_msg.message_id}"
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👁 ثبت بازدید", callback_data=f"do_view_{target_id}"), InlineKeyboardButton("🚀 توربو", callback_data=f"do_turbo_{target_id}")],
            [InlineKeyboardButton("🤖 بازگشت به ربات", url=bot_url)]
        ])
        
        await context.bot.edit_message_reply_markup(
            chat_id=VIEW_CHANNEL,
            message_id=sent_msg.message_id,
            reply_markup=ikb
        )
        await query.message.edit_text("✅ پست شما با موفقیت ثبت شد و در کانال ویوگیر قرار گرفت.")
    except Exception as e:
        await query.message.edit_text(f"✅ پست ثبت شد اما در ارسال به کانال خطا رخ داد:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

async def start_member_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    cost = int(data.split("_")[1])
    user_id = query.from_user.id
    
    u = get_or_create_user(user_id)
    if u[3] < cost and user_id != ADMIN_ID:
        await query.message.reply_text(f"❌ موجودی الماس شما کافی نیست! شما به {cost} الماس نیاز دارید.")
        return ConversationHandler.END

    context.user_data["member_cost"] = cost
    context.user_data["member_count"] = cost // 2
    await query.message.reply_text("🔗 **لطفاً لینک مورد نظر را بفرستید:**\n(مانند @ChannelName یا لینک عمومی/خصوصی)")
    return WAIT_MEMBER_LINK

async def receive_member_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    context.user_data["member_link"] = link
    cost = context.user_data.get("member_cost")
    count = context.user_data.get("member_count")

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ثبت لینک", callback_data="confirm_member_link")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_ads")]
    ])

    await update.message.reply_text(f"📋 **پیش‌نمایش سفارش ممبرگیر**\n🔗 لینک: {link}\n👥 تعداد ممبر: {count}\n💎 هزینه: {cost} الماس\n\nآیا از ثبت این لینک مطمئن هستید؟", reply_markup=ikb)
    return WAIT_MEMBER_CONFIRM

async def confirm_member_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cost = context.user_data.get("member_cost")
    count = context.user_data.get("member_count")
    link = context.user_data.get("member_link")
    bot_username = (await context.bot.get_me()).username

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET coin_member = coin_member - ? WHERE user_id=?", (cost, user_id))
    conn.commit()
    conn.close()

    target_url = link if link.startswith("http") else f"https://t.me/{link.replace('@', '')}"
    bot_url = f"https://t.me/{bot_username}"

    try:
        sent_msg = await context.bot.send_message(
            chat_id=MEMBER_CHANNEL,
            text=f"📢 **سفارش جدید ممبرگیر**\n\nعضو کانال زیر شوید و روی دریافت الماس کلیک کنید:\nتعداد مورد نیاز: {count} ممبر",
            parse_mode="Markdown"
        )
        
        channel_user_id = link.replace('@', '') if link.startswith('@') else None
        callback_target = f"m_{sent_msg.message_id}_{channel_user_id}" if channel_user_id else f"m_{sent_msg.message_id}"

        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("عضویت", url=target_url)],
            [InlineKeyboardButton("💎 دریافت الماس", callback_data=f"get_diamond_{callback_target}")],
            [InlineKeyboardButton("سفارش ممبر", url=bot_url)]
        ])

        await context.bot.edit_message_reply_markup(
            chat_id=MEMBER_CHANNEL,
            message_id=sent_msg.message_id,
            reply_markup=ikb
        )
        await query.message.edit_text("✅ لینک شما با موفقیت ثبت شد و در کانال ممبرگیر قرار گرفت.")
    except Exception as e:
        await query.message.edit_text(f"✅ لینک ثبت شد اما در ارسال به کانال خطا رخ داد:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

async def cancel_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# ----------------- BUTTON CALLBACKS -----------------
async def handle_channel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if data.startswith("do_view_"):
        target_id = data.replace("do_view_", "")
        c.execute("SELECT * FROM user_clicks WHERE user_id=? AND target_id=?", (user_id, target_id))
        if c.fetchone():
            conn.close()
            await query.answer("❌ شما قبلاً برای این پست بازدید ثبت کرده‌اید!", show_alert=True)
            return

        c.execute("INSERT INTO user_clicks (user_id, target_id) VALUES (?, ?)", (user_id, target_id))
        c.execute("UPDATE users SET coin_view = coin_view + 1, total_views = total_views + 1, today_views = today_views + 1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        await query.answer("🎉 ۱ سکه ویو به حساب شما اضافه شد!", show_alert=True)

    elif data.startswith("do_turbo_"):
        target_id = data.replace("do_turbo_", "")
        c.execute("INSERT OR IGNORE INTO post_views (post_id, view_count) VALUES (?, 0)", (target_id,))
        c.execute("UPDATE post_views SET view_count = view_count + 1 WHERE post_id=?", (target_id,))
        c.execute("SELECT view_count FROM post_views WHERE post_id=?", (target_id,))
        views = c.fetchone()[0]

        bonus = 0
        if views >= 100:
            bonus = 50
        elif views >= 80:
            bonus = 40
        elif views >= 60:
            bonus = 30
        elif views >= 40:
            bonus = 20

        if bonus > 0:
            c.execute("UPDATE users SET coin_view = coin_view + ? WHERE user_id=?", (bonus, user_id))
            conn.commit()
            conn.close()
            await query.answer(f"🚀 این پست {views} بازدید داشته است! {bonus} سکه توربو دریافت کردید!", show_alert=True)
        else:
            conn.close()
            await query.answer(f"📊 این پست تاکنون {views} بازدید داشته است.\nپاداش توربو از ۴۰ بازدید به بالا شروع می‌شود!", show_alert=True)

    elif data.startswith("get_diamond_"):
        target_info = data.replace("get_diamond_", "").split("_")
        target_id = target_info[1]
        channel_username = target_info[2] if len(target_info) > 2 else None

        c.execute("SELECT * FROM user_clicks WHERE user_id=? AND target_id=?", (user_id, f"m_{target_id}"))
        if c.fetchone():
            conn.close()
            await query.answer("❌ شما قبلاً برای این پست الماس دریافت کرده‌اید!", show_alert=True)
            return

        if channel_username:
            try:
                member = await context.bot.get_chat_member(chat_id=f"@{channel_username}", user_id=user_id)
                if member.status in ["left", "kicked"]:
                    conn.close()
                    await query.answer("❌ شما هنوز در کانال عضو نشده‌اید! ابتدا عضو شوید.", show_alert=True)
                    return
            except:
                pass

        c.execute("INSERT INTO user_clicks (user_id, target_id) VALUES (?, ?)", (user_id, f"m_{target_id}"))
        c.execute("UPDATE users SET coin_member = coin_member + 1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        await query.answer("🎉 ۱ الماس ممبرگیر به حساب شما اضافه شد!", show_alert=True)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    view_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_view_ads, pattern="^v_")],
        states={
            WAIT_VIEW_POST: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_view_post)],
            WAIT_VIEW_CONFIRM: [
                CallbackQueryHandler(confirm_view_post, pattern="^confirm_view_post$"),
                CallbackQueryHandler(cancel_ads, pattern="^cancel_ads$")
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_ads, pattern="^cancel_ads$")]
    )

    member_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_member_ads, pattern="^m_")],
        states={
            WAIT_MEMBER_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_member_link)],
            WAIT_MEMBER_CONFIRM: [
                CallbackQueryHandler(confirm_member_link, pattern="^confirm_member_link$"),
                CallbackQueryHandler(cancel_ads, pattern="^cancel_ads$")
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_ads, pattern="^cancel_ads$")]
    )

    receipt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(pay_card_handler, pattern="^pay_card$")],
        states={
            WAIT_RECEIPT_PHOTO: [MessageHandler(filters.PHOTO, receive_receipt_photo)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(view_conv)
    app.add_handler(member_conv)
    app.add_handler(receipt_conv)
    
    # Callback Handlers
    app.add_handler(CallbackQueryHandler(handle_lottery_callbacks, pattern="^(lottery_|goto_shop)"))
    app.add_handler(CallbackQueryHandler(select_buy_package, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(admin_payment_decision, pattern="^(approve_|reject_)"))
    app.add_handler(CallbackQueryHandler(handle_channel_callbacks, pattern="^(do_view_|do_turbo_|get_diamond_)"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    logging.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
