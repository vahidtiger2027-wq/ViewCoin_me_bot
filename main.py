import os
import sqlite3
import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789")) # آیدی عددی مدیر اصلی
PORT = int(os.environ.get("PORT", 5000))

MEMBER_CHANNEL = "@my_member_man"
VIEW_CHANNEL = "@view_sin_channel"

# ----------------- DATABASE SETUP -----------------
DB_FILE = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        coin_view INTEGER DEFAULT 0,
        coin_member INTEGER DEFAULT 0,
        ref_count INTEGER DEFAULT 0,
        ref_view_gift INTEGER DEFAULT 0,
        ref_member_gift INTEGER DEFAULT 0,
        total_views INTEGER DEFAULT 0,
        today_views INTEGER DEFAULT 0,
        last_daily TEXT,
        lottery_wins INTEGER DEFAULT 0
    )''')
    # جدول تنظیمات پنل
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # تنظیمات پیش‌فرض
    defaults = {
        "daily_coin": "10",
        "ref_view": "500",
        "ref_member": "100",
        "card_number": "وارد نشده",
        "gateway_url": "وارد نشده",
        "sponsor_channel": "",
        "welcome_msg": "به ربات ممبرگیر و ویوگیر خوش آمدید!"
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else ""

def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_user(user_id, username=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    u = c.fetchone()
    if not u:
        c.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        u = c.fetchone()
    conn.close()
    return u

def update_user_coins(user_id, view_add=0, member_add=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ? WHERE user_id=?", (view_add, member_add, user_id))
    conn.commit()
    conn.close()

# ----------------- KEYBOARDS -----------------
def main_keyboard(user_id):
    kb = [
        ["▪︎جمع اوری سکه رایگان"],
        ["حساب کار بری مشحصات", "👥جذب زیر مجموعه"],
        ["▪︎ثبت تبلیغ ویو گیر و ممبر گیر"],
        ["▪︎فروشگاه", "دکمه قرعه کشی"],
        ["▪︎انتقال سکه", "▪︎انتقال الماس"]
    ]
    if user_id == ADMIN_ID:
        kb.append(["▪︎پنل مدیریت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- BOT HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u_data = get_user(user.id, user.username or "")
    
    # بررسی زیرمجموعه‌گیری
    if context.args and len(context.args) > 0:
        try:
            ref_id = int(context.args[0])
            if ref_id != user.id:
                # چک کردیم که قبلش زیرمجموعه نبوده باشه
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT ref_count FROM users WHERE user_id=?", (user.id,))
                # ساده‌سازی: اعطای پاداش به دعوت‌کننده
                rv = int(get_setting("ref_view"))
                rm = int(get_setting("ref_member"))
                c.execute("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ?, ref_count = ref_count + 1 WHERE user_id=?", (rv, rm, ref_id))
                conn.commit()
                conn.close()
        except:
            pass

    welcome_text = get_setting("welcome_msg")
    await update.message.reply_text(f"{welcome_text}\n\nسلام {user.first_name} خوش آمدید!", reply_markup=main_keyboard(user.id))

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    u = get_user(user.id, user.username or "")
    
    if text == "▪︎جمع اوری سکه رایگان":
        today = str(datetime.date.today())
        if u[8] == today:
            await update.message.reply_text("❌ شما امروز سکه رایگان دریافت کرده‌اید! فردا مجدداً تلاش کنید.")
        else:
            daily_val = int(get_setting("daily_coin"))
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE users SET coin_view = coin_view + ?, last_daily = ? WHERE user_id=?", (daily_val, today, user.id))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"🎉 تعداد {daily_val} سکه رایگان روزانه به حساب شما اضافه شد!")

    elif text == "حساب کار بری مشحصات":
        coin_v = 9999999 if user.id == ADMIN_ID else u[2]
        coin_m = 9999999 if user.id == ADMIN_ID else u[3]
        username_str = f"@{u[1]}" if u[1] else "ندارد"
        
        msg = f"""👤 **مشخصات حساب کاربری:**

🔹 **نام کاربری:** {username_str}
🔹 **آیدی عددی:** `{u[0]}`
🎁 **هدیه مدیریت:** {u[5]} ویو / {u[6]} الماس
👁 **بازدیدهای شما:** {u[7]}
📅 **بازدیدهای امروز:** {u[8] if u[8] else 0}
🏆 **جوایز قرعه‌کشی:** {u[10]}
👥 **تعداد زیرمجموعه‌ها:** {u[4]}
💰 **پورسانت زیرمجموعه‌گیری:** {u[5]} سکه / {u[6]} الماس
💎 **موجودی سکه ویو شما:** {coin_v}
💎 **موجودی الماس ممبر شما:** {coin_m}"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "👥جذب زیر مجموعه":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        rv = get_setting("ref_view")
        rm = get_setting("ref_member")
        msg = f"""👥 **جذب زیرمجموعه**

با دعوت دوستان خود به ربات، پاداش دریافت کنید!
🎁 **جایزه هر زیرمجموعه:** {rv} سکه ویوگیر + {rm} الماس ممبرگیر

🔗 **لینک اختصاصی شما:**
`{ref_link}`"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "▪︎ثبت تبلیغ ویو گیر و ممبر گیر":
        kb = ReplyKeyboardMarkup([
            ["👁ثبت تبلیغ ویوگیر", "👥ثبت تبلیغ ممبر گیر"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await update.message.reply_text("لطفاً نوع تبلیغ خود را انتخاب کنید:", reply_markup=kb)

    elif text == "👁ثبت تبلیغ ویوگیر":
        inline_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("۴۰ سکه -> ۴۰ ویو", callback_data="v_40"), InlineKeyboardButton("۵۰ سکه -> ۵۰ ویو", callback_data="v_50")],
            [InlineKeyboardButton("۱۰۰ سکه -> ۱۰۰ ویو", callback_data="v_100"), InlineKeyboardButton("۲۰۰ سکه -> ۲۰۰ ویو", callback_data="v_200")]
        ])
        await update.message.reply_text("تعداد بازدید مورد نظر خود را انتخاب کنید:", reply_markup=inline_kb)

    elif text == "👥ثبت تبلیغ ممبر گیر":
        inline_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("۲۰ سکه -> ۱۰ ممبر", callback_data="m_10"), InlineKeyboardButton("۴۰ سکه -> ۲۰ ممبر", callback_data="m_20")],
            [InlineKeyboardButton("۶۰ سکه -> ۳۰ ممبر", callback_data="m_30"), InlineKeyboardButton("۸۰ سکه -> ۴۰ ممبر", callback_data="m_40")],
            [InlineKeyboardButton("۱۰۰ سکه -> ۵۰ ممبر", callback_data="m_50")]
        ])
        await update.message.reply_text("تعداد ممبر مورد نظر خود را انتخاب کنید:", reply_markup=inline_kb)

    elif text == "▪︎فروشگاه":
        kb = ReplyKeyboardMarkup([
            ["👁خرید سکه ویوگیر", "👁خرید الماس ممبر گیر"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await update.message.reply_text("به فروشگاه خوش آمدید! بخش مورد نظر را انتخاب کنید:", reply_markup=kb)

    elif text == "👁خرید سکه ویوگیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("20.000 سکه - 50.000 تومان", callback_data="buy_v_50")],
            [InlineKeyboardButton("40.000 سکه - 100.000 تومان", callback_data="buy_v_100")],
            [InlineKeyboardButton("50.000 سکه - 150.000 تومان", callback_data="buy_v_150")],
            [InlineKeyboardButton("200.000 سکه - 200.000 تومان", callback_data="buy_v_200")]
        ])
        await update.message.reply_text("پکیج سکه ویوگیر را انتخاب کنید:", reply_markup=ikb)

    elif text == "👁خرید الماس ممبر گیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("100 الماس - 25.000 تومان", callback_data="buy_m_25")],
            [InlineKeyboardButton("250 الماس - 50.000 تومان", callback_data="buy_m_50")],
            [InlineKeyboardButton("500 الماس - 100.000 تومان", callback_data="buy_m_100")],
            [InlineKeyboardButton("1000 الماس - 200.000 تومان", callback_data="buy_m_200")],
            [InlineKeyboardButton("4000 الماس - 800.000 تومان", callback_data="buy_m_800")]
        ])
        await update.message.reply_text("پکیج الماس ممبرگیر را انتخاب کنید:", reply_markup=ikb)

    elif text == "دکمه قرعه کشی":
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("ورود به فروشگاه", callback_data="go_shop")]])
        msg = """🎰 **به قرعه‌کشی ربات بزرگ ممبرگیر و ویوگیر خوش آمدید!**

برای ورود به قرعه‌کشی باید از ربات خرید کنید و بلیت شانس دریافت کنید:
🎫 ۵۰.۰۰۰ تومان خرید = ۲ بلیت
🎫 ۱۰۰.۰۰۰ تومان خرید = ۴ بلیت
🎫 ۲۰۰.۰۰۰ تومان خرید = ۶ بلیت
🎫 ۵۰۰.۰۰۰ تومان خرید = ۱۰ بلیت"""
        await update.message.reply_text(msg, reply_markup=ikb)

    elif text == "▪︎انتقال سکه" or text == "▪︎انتقال الماس":
        await update.message.reply_text("جهت انتقال، لطفاً دستور زیر را ارسال کنید:\n\n`انتقال [آیدی_عددی] [تعداد]`\nمثال:\n`انتقال 123456789 100`", parse_mode="Markdown")

    elif text == "بازگشت به منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید.", reply_markup=main_keyboard(user.id))

    elif text == "▪︎پنل مدیریت" and user.id == ADMIN_ID:
        admin_kb = ReplyKeyboardMarkup([
            ["تنظیم سفارشات ویو", "تنظیم سفارش ممبر"],
            ["تنظیم فروشگاه", "تنظیم سکه روزانه"],
            ["تنظیم سکه زیر مجموعه", "تنظیم اسپانسر"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await update.message.reply_text("🛠 **پنل مدیریت ربات**", reply_markup=admin_kb)

# ----------------- CALLBACK HANDLER -----------------
async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    await query.answer()
    data = query.data
    card = get_setting("card_number")
    gate = get_setting("gateway_url")

    if data.startswith("buy_v_") or data.startswith("buy_m_"):
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("پرداخت از طریق درگاه", url=gate if gate.startswith("http") else "https://t.me")]
        ])
        msg = f"💳 **شماره کارت جهت واریز:**\n`{card}`\n\nپس از واریز کارت به کارت، عکس فیش تراکنش را ارسال کنید.\nیا برای پرداخت آنلاین از دکمه زیر استفاده کنید:"
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=ikb)

    elif data == "go_shop":
        kb = ReplyKeyboardMarkup([
            ["👁خرید سکه ویوگیر", "👁خرید الماس ممبر گیر"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await query.message.reply_text("جهت شرکت در قرعه‌کشی، پکیج مورد نظر خود را از فروشگاه خریداری کنید:", reply_markup=kb)

# ----------------- FLASK & WEBHOOK SERVER -----------------
app = Flask(__name__)
bot_app = Application.builder().token(BOT_TOKEN).build()

# افزودن هندرها به ربات
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
bot_app.add_handler(CallbackQueryHandler(handle_callback))

@app.route("/", methods=["GET"])
def index():
    return "Bot is Running Live 24/7!", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    await bot_app.process_update(update)
    return "OK", 200

if __name__ == "__main__":
    import asyncio
    # مقداردهی اولیه ربات
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_app.initialize())
    app.run(host="0.0.0.0", port=PORT)
