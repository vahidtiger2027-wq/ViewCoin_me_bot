import os
import sqlite3
import datetime
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
PORT = int(os.environ.get("PORT", 5000))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

# کانال‌های ویو و ممبرگیر اصلی ربات
MEMBER_CHANNEL = os.environ.get("MEMBER_CHANNEL", "@my_member_chan")
VIEW_CHANNEL = os.environ.get("VIEW_CHANNEL", "@my_view_chan")

logging.basicConfig(level=logging.INFO)

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
        lottery_wins INTEGER DEFAULT 0,
        gift_received INTEGER DEFAULT 0,
        is_left INTEGER DEFAULT 0
    )''')
    # جدول تنظیمات
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    # جدول تراکنش‌های فیش واریزی
    c.execute('''CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        photo_id TEXT,
        status TEXT DEFAULT 'PENDING'
    )''')

    defaults = {
        "daily_coin": "20",
        "daily_diamond": "20",
        "ref_view": "200",
        "ref_member": "50",
        "card_number": "تنظیم نشده",
        "gateway_url": "تنظیم نشده",
        "sponsor_channel": "",
        "welcome_msg": "به ربات بزرگ ممبرگیر و ویوگیر خوش آمدید!",
        "lottery_p1_coin": "50",
        "lottery_p1_diamond": "20",
        "lottery_p2_coin": "30",
        "lottery_p2_diamond": "10",
        "lottery_p3_coin": "10",
        "lottery_p3_diamond": "5",
        "lottery_price_unit": "50000",
        "lottery_status": "OFF",
        "forced_days": "3",
        "forced_penalty": "2"
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

def set_setting(key, val):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(val)))
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

# ----------------- KEYBOARDS -----------------
def main_keyboard(user_id):
    kb = [
        ["💎جم اوری سکه رایگان"],
        ["💻حصاب کار بری مشحصات", "👥جذب زیر مجموعه"],
        ["📥ثبت تبلیغ ویو گیر و ممبر گیر"],
        ["👨‍💻🛍︎فروشگاه", "دکمه قرعه کشی"],
        ["💰 انتقال سکه", "💎︎  انتقال الماس"]
    ]
    if user_id == ADMIN_ID:
        kb.append(["▪︎پنل مدیریت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- STATES FOR CONVERSATIONS -----------------
WAITING_POST_VIEW, WAITING_LINK_MEMBER = range(2)
WAITING_TRANSFER_USER, WAITING_TRANSFER_AMOUNT = range(2, 4)
WAITING_RECEIPT_PHOTO = 4

# ----------------- BOT HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u_data = get_user(user.id, user.username or "")
    
    # اسپانسر جوین اجباری
    sponsor = get_setting("sponsor_channel")
    if sponsor and str(sponsor).startswith("@"):
        try:
            member_check = await context.bot.get_chat_member(chat_id=sponsor, user_id=user.id)
            if member_check.status in ["left", "kicked"]:
                ikb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 عضویت در کانال اسپانسر", url=f"https://t.me/{sponsor[1:]}")]])
                await update.message.reply_text("❌ جهت استفاده از ربات ابتدا باید در کانال اسپانسر عضو شوید:", reply_markup=ikb)
                return
        except Exception:
            pass

    # زیرمجموعه‌گیری
    if context.args and len(context.args) > 0:
        try:
            ref_id = int(context.args[0])
            if ref_id != user.id:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                rv = int(get_setting("ref_view"))
                rm = int(get_setting("ref_member"))
                c.execute("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ?, ref_count = ref_count + 1 WHERE user_id=?", (rv, rm, ref_id))
                conn.commit()
                conn.close()
                await context.bot.send_message(chat_id=ref_id, text=f"🎉 کاربر جدیدی با لینک شما وارد شد! +{rv} سکه و +{rm} الماس دریافت کردید.")
        except Exception as e:
            logging.error(f"Error in ref: {e}")

    welcome_text = get_setting("welcome_msg")
    await update.message.reply_text(f"{welcome_text}\n\nسلام {user.first_name} خوش آمدید!", reply_markup=main_keyboard(user.id))

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    u = get_user(user.id, user.username or "")
    
    if text == "💎جم اوری سکه رایگان":
        today = str(datetime.date.today())
        if u[9] == today:
            await update.message.reply_text("❌ شما امروز سکه رایگان دریافت کرده‌اید! فردا مجدداً تلاش کنید.")
        else:
            daily_coin = int(get_setting("daily_coin"))
            daily_diamond = int(get_setting("daily_diamond"))
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ?, last_daily = ? WHERE user_id=?", (daily_coin, daily_diamond, today, user.id))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"🎉 تعداد {daily_coin} سکه و {daily_diamond} الماس رایگان روزانه به حساب شما اضافه شد!")

    elif text == "💻حصاب کار بری مشحصات":
        coin_v = u[2]
        coin_m = u[3]
        username_str = f"@{u[1]}" if u[1] else "ندارد"
        lottery_str = u[10] if u[10] > 0 else "0"
        
        msg = f"""💻 **مشخصات حساب کاربری:**

🆔 **نام کاربری:** {username_str}
🔹 **آیدی عددی:** `{u[0]}`
🎁 **هدیه مدیریت:** {u[11]}
👁 **بازدیدهای شما:** {u[7]}
📅 **بازدیدهای امروز:** {u[8]}
🏆 **جوایز قرعه‌کشی:** {lottery_str}
👥 **تعداد زیرمجموعه‌ها:** {u[4]}
💰 **پورسانت زیرمجموعه‌گیری:** {u[5]} سکه / {u[6]} الماس
💎 **موجودی سکه شما:** {coin_v}
💎 **موجودی الماس شما:** {coin_m}"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "👥جذب زیر مجموعه":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        rv = get_setting("ref_view")
        rm = get_setting("ref_member")
        msg = f"""👥 **جذب زیرمجموعه**

با دعوت هر عضو جدید، پاداش دریافت کنید!
🎁 **پاداش:** {rv} سکه ویوگیر + {rm} الماس ممبرگیر برای هر عضو جدید

🔗 **لینک اختصاصی شما:**
`{ref_link}`"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "📥ثبت تبلیغ ویو گیر و ممبر گیر":
        kb = ReplyKeyboardMarkup([
            ["👁ثبت تبلیغ ویوگیر", "👥ثبت تبلیغ ممبر گیر"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await update.message.reply_text("لطفاً نوع تبلیغ خود را انتخاب کنید:", reply_markup=kb)

    elif text == "👁ثبت تبلیغ ویوگیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("۴۰ سکه -> ۴۰ ویو", callback_data="v_40"), InlineKeyboardButton("۵۰ سکه -> ۵۰ ویو", callback_data="v_50")],
            [InlineKeyboardButton("۱۰۰ سکه -> ۱۰۰ ویو", callback_data="v_100"), InlineKeyboardButton("۲۰۰ سکه -> ۲۰۰ ویو", callback_data="v_200")]
        ])
        await update.message.reply_text("مقدار سفارش ویو را انتخاب کنید:", reply_markup=ikb)

    elif text == "👥ثبت تبلیغ ممبر گیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("۲۰ سکه -> ۱۰ ممبر", callback_data="m_10"), InlineKeyboardButton("۴۰ سکه -> ۲۰ ممبر", callback_data="m_20")],
            [InlineKeyboardButton("۶۰ سکه -> ۳۰ ممبر", callback_data="m_30"), InlineKeyboardButton("۸۰ سکه -> ۴۰ ممبر", callback_data="m_40")],
            [InlineKeyboardButton("۱۰۰ سکه -> ۵۰ ممبر", callback_data="m_50")]
        ])
        await update.message.reply_text("مقدار سفارش ممبر را انتخاب کنید:", reply_markup=ikb)

    elif text == "👨‍💻🛍︎فروشگاه":
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
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("فروشگاه", callback_data="go_shop")]])
        p_unit = get_setting("lottery_price_unit")
        msg = f"""🎰 **به قرعه‌کشی ربات بزرگ ممبرگیر و ویوگیر خوش آمدید!**

برای ورود در قرعه‌کشی باید از ربات خرید کنید و بلیت شانس دریافت کنید:

🎫 {p_unit} هزار تومان خرید = ۲ بلیت
🎫 ۱۰۰.۰۰۰ هزار تومان خرید = ۴ بلیت
🎫 ۲۰۰.۰۰۰ هزار تومان خرید = ۶ بلیت
🎫 ۵۰۰.۰۰۰ هزار تومان خرید = ۱۰ بلیت"""
        await update.message.reply_text(msg, reply_markup=ikb)

    elif text in ["💰 انتقال سکه", "💎︎  انتقال الماس"]:
        context.user_data["transfer_type"] = "coin" if "سکه" in text else "diamond"
        await update.message.reply_text("لطفاً آیدی عددی اکانت مورد نظر را وارد کنید:")
        return WAITING_TRANSFER_USER

    elif text == "بازگشت به منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید.", reply_markup=main_keyboard(user.id))

    elif text == "▪︎پنل مدیریت" and user.id == ADMIN_ID:
        admin_kb = ReplyKeyboardMarkup([
            ["تنظیم سفارشات ویو", "تنظیم سفارش ممبر"],
            ["تنظیم فروشگاه", "تنظیم شماره کارت"],
            ["تنظیم آیدی/لینک درگاه", "تنظیم سکه و الماس روزانه"],
            ["تنظیم سکه زیرمجموعه", "تنظیم سکه هدیه"],
            ["تنظیم جایزه قرعه کشی", "تنظیم شروع قرعه کشی"],
            ["تنظیم اسپانسر جوین اجباری", "تنظیم پیام خوشامد گویی"],
            ["آمار کاربران", "تنظیم روز جوین اجباری"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await update.message.reply_text("🛠 **پنل مدیریت ربات**", reply_markup=admin_kb)

# ----------------- INLINE CALLBACK HANDLER -----------------
async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    await query.answer()
    data = query.data
    card = get_setting("card_number")
    gate = get_setting("gateway_url")

    if data.startswith("buy_v_") or data.startswith("buy_m_"):
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💱 لینک/پرداخت آنلاین درگاه", url=gate if gate.startswith("http") else "https://t.me")]
        ])
        msg = f"💳 **شماره کارت جهت واریز:**\n`{card}`\n\nپس از واریز از طریق شماره کارت، عکس فیش تراکنش را ارسال کنید.\nیا برای واریز آنلاین از دکمه زیر استفاده کنید:"
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=ikb)

    elif data == "go_shop":
        kb = ReplyKeyboardMarkup([
            ["👁خرید سکه ویوگیر", "👁خرید الماس ممبر گیر"],
            ["بازگشت به منوی اصلی"]
        ], resize_keyboard=True)
        await query.message.reply_text("جهت شرکت در قرعه‌کشی، پکیج مورد نظر را انتخاب کنید:", reply_markup=kb)

    elif data.startswith("v_"):
        context.user_data["order_view_amount"] = data.split("_")[1]
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("تایید و ارسال پست", callback_data="confirm_v_post")]])
        await query.message.reply_text("پست مورد نظر را بفرستید (توضیحات یا همراه با لینک):", reply_markup=ikb)

    elif data == "confirm_v_post":
        bot_username = (await context.bot.get_me()).username
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ثبت بازدید", callback_data="click_view"), InlineKeyboardButton("توربو", callback_data="click_turbo")],
            [InlineKeyboardButton("بازگشت به ربات", url=f"https://t.me/{bot_username}")]
        ])
        await context.bot.send_message(chat_id=VIEW_CHANNEL, text="📌 **پست جدید برای بازدید:**", reply_markup=ikb)
        await query.message.reply_text("✅ پست شما با موفقیت در کانال ویو ثبت شد!")

    elif data.startswith("m_"):
        context.user_data["order_member_amount"] = data.split("_")[1]
        await query.message.reply_text("لطفاً لینک کانال مورد نظر را بفرستید:")

    elif data == "click_view":
        user_id = query.from_user.id
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET coin_view = coin_view + 1, total_views = total_views + 1, today_views = today_views + 1 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        await query.answer("✅ ۱ سکه بازدید دریافت کردید!", show_alert=True)

    elif data == "click_turbo":
        await query.answer("🚀 سیستم توربو فعال است! (به ازای هر ۱۰۰ بازدید ۵۰ سکه اضافه)", show_alert=True)

# ----------------- TRANSFER HANDLERS -----------------
async def process_transfer_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["target_user_id"] = update.message.text.strip()
    t_type = "سکه" if context.user_data.get("transfer_type") == "coin" else "الماس"
    await update.message.reply_text(f"مقدار {t_type} انتقالی را وارد کنید:")
    return WAITING_TRANSFER_AMOUNT

async def process_transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        target_id = int(context.user_data.get("target_user_id"))
        sender_id = update.effective_user.id
        t_type = context.user_data.get("transfer_type")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT coin_view, coin_member FROM users WHERE user_id=?", (sender_id,))
        sender = c.fetchone()

        field = "coin_view" if t_type == "coin" else "coin_member"
        balance = sender[0] if t_type == "coin" else sender[1]

        if balance < amount:
            await update.message.reply_text("❌ موجودی شما کافی نیست!")
        else:
            c.execute(f"UPDATE users SET {field} = {field} - ? WHERE user_id=?", (amount, sender_id))
            c.execute(f"UPDATE users SET {field} = {field} + ? WHERE user_id=?", (amount, target_id))
            conn.commit()
            await update.message.reply_text("✅ انتقال با موفقیت انجام شد.")
            await context.bot.send_message(chat_id=target_id, text=f"🎉 تعداد {amount} {t_type} از طرف کاربر `{sender_id}` به حساب شما واریز شد.")
        conn.close()
    except Exception as e:
        await update.message.reply_text("❌ خطایی رخ داد. آیدی یا مقدار وارد شده معتبر نیست.")
    return ConversationHandler.END

# ----------------- FLASK & WEBHOOK -----------------
app = Flask(__name__)
bot_app = Application.builder().token(BOT_TOKEN).build()

bot_app.add_handler(CommandHandler("start", start))

transfer_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(💰 انتقال سکه|💎︎  انتقال الماس)$"), handle_messages)],
    states={
        WAITING_TRANSFER_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_transfer_user)],
        WAITING_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_transfer_amount)],
    },
    fallbacks=[]
)

bot_app.add_handler(transfer_conv)
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
bot_app.add_handler(CallbackQueryHandler(handle_callback))

@app.route("/", methods=["GET"])
def index():
    return "Bot Server is Active!", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        await bot_app.process_update(update)
        return "OK", 200

async def setup_webhook():
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
        await bot_app.bot.set_webhook(url=webhook_url)
        logging.info(f"Webhook set to {webhook_url}")

import asyncio
loop = asyncio.get_event_loop()
loop.run_until_complete(bot_app.initialize())
if RENDER_URL:
    loop.run_until_complete(setup_webhook())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
