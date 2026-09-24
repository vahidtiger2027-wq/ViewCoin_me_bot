import os
import sqlite3
import datetime
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864400306:AAHsgcfH1GdWzJARqMxnX8ABMWBYWFH4Rn4")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
PORT = int(os.environ.get("PORT", 10000))

MEMBER_CHANNEL = os.environ.get("MEMBER_CHANNEL", "@my_member_chan")
VIEW_CHANNEL = os.environ.get("VIEW_CHANNEL", "@my_view_chan")

logging.basicConfig(level=logging.INFO)

# ----------------- DUMMY SERVER FOR RENDER -----------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
    server.serve_forever()

# ----------------- DATABASE SETUP -----------------
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
        ref_view_gift INTEGER DEFAULT 0,
        ref_member_gift INTEGER DEFAULT 0,
        total_views INTEGER DEFAULT 0,
        today_views INTEGER DEFAULT 0,
        last_daily TEXT,
        lottery_wins INTEGER DEFAULT 0,
        gift_received INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
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
        "lottery_price_unit": "50000"
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    
    c.execute("INSERT OR REPLACE INTO users (user_id, username, coin_view, coin_member) VALUES (?, 'Admin', 999999, 999999)", (ADMIN_ID,))
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

def get_user(user_id, username=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    u = c.fetchone()
    if not u:
        coins = 999999 if user_id == ADMIN_ID else 0
        c.execute("INSERT INTO users (user_id, username, coin_view, coin_member) VALUES (?, ?, ?, ?)", (user_id, username, coins, coins))
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

# ----------------- STATES -----------------
WAITING_TRANSFER_USER, WAITING_TRANSFER_AMOUNT = range(2)
WAIT_MEMBER_LINK, WAIT_MEMBER_CONFIRM = range(2, 4)
WAIT_VIEW_POST, WAIT_VIEW_CONFIRM = range(4, 6)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username or "")
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
        coin_v = "بی‌نهایت (ادمین)" if user.id == ADMIN_ID else u[2]
        coin_m = "بی‌نهایت (ادمین)" if user.id == ADMIN_ID else u[3]
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

    elif text == "بازگشت به منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید.", reply_markup=main_keyboard(user.id))

# ----------------- ORDER MEMBER FLOW -----------------
async def start_member_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    cost = int(data.split("_")[1])
    u = get_user(user_id)

    if user_id != ADMIN_ID and u[3] < cost:
        await query.message.reply_text(f"❌ موجودی الماس شما کافی نیست! (نیاز به {cost} الماس دارید)")
        return ConversationHandler.END

    context.user_data["member_cost"] = cost
    context.user_data["member_count"] = cost // 2
    await query.message.reply_text("🔗 لطفاً لینک عمومی یا خصوصی کانال خود را ارسال کنید:")
    return WAIT_MEMBER_LINK

async def receive_member_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not (link.startswith("http://") or link.startswith("https://") or link.startswith("@") or link.startswith("t.me/")):
        await update.message.reply_text("❌ لینک ارسال شده معتبر نیست! لطفاً یک لینک صحیح بفرستید:")
        return WAIT_MEMBER_LINK

    context.user_data["target_link"] = link
    count = context.user_data.get("member_count")
    cost = context.user_data.get("member_cost")

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ثبت سفارش", callback_data="confirm_member_order")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_order")]
    ])

    await update.message.reply_text(
        f"📋 **پیش‌نمایش سفارش ممبر:**\n\n🔗 لینک کانال: {link}\n👥 تعداد ممبر: {count}\n💎 هزینه سفارش: {cost} الماس\n\nآیا سفارش مورد تایید است؟",
        parse_mode="Markdown",
        reply_markup=ikb
    )
    return WAIT_MEMBER_CONFIRM

async def confirm_member_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cost = context.user_data.get("member_cost")
    count = context.user_data.get("member_count")
    link = context.user_data.get("target_link")

    if user_id != ADMIN_ID:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET coin_member = coin_member - ? WHERE user_id=?", (cost, user_id))
        conn.commit()
        conn.close()

    try:
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 عضویت در کانال", url=link if link.startswith("http") else f"https://t.me/{link.replace('@', '')}")]])
        await context.bot.send_message(
            chat_id=MEMBER_CHANNEL,
            text=f"📢 **سفارش جدید ممبرگیر**\n\nبرای دریافت سکه در کانال زیر عضو شوید:\nتعداد مورد نیاز: {count} ممبر",
            reply_markup=ikb
        )
        await query.message.edit_text("✅ سفارش شما با موفقیت ثبت شد و به کانال ممبرگیر ارسال گردید.")
    except Exception as e:
        await query.message.edit_text(f"✅ سفارش ثبت شد ولی ارسال به کانال ممبرگیر به دلیل مشکل تنظیم کانال با خطا مواجه شد:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

# ----------------- ORDER VIEW FLOW -----------------
async def start_view_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    cost = int(data.split("_")[1])
    u = get_user(user_id)

    if user_id != ADMIN_ID and u[2] < cost:
        await query.message.reply_text(f"❌ موجودی سکه شما کافی نیست! (نیاز به {cost} سکه دارید)")
        return ConversationHandler.END

    context.user_data["view_cost"] = cost
    context.user_data["view_count"] = cost
    await query.message.reply_text("📩 لطفاً پست مورد نظر خود را فوروارد کنید یا فرستید:")
    return WAIT_VIEW_POST

async def receive_view_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["post_message_id"] = update.message.message_id
    context.user_data["post_chat_id"] = update.message.chat_id

    cost = context.user_data.get("view_cost")
    count = context.user_data.get("view_count")

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ثبت سفارش", callback_data="confirm_view_order")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_order")]
    ])

    await update.message.reply_text(
        f"📋 **پیش‌نمایش سفارش ویو:**\n\n👁 تعداد بازدید: {count}\n💰 هزینه سفارش: {cost} سکه\n\nآیا از ارسال این پست مطمئن هستید؟",
        reply_markup=ikb
    )
    return WAIT_VIEW_CONFIRM

async def confirm_view_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cost = context.user_data.get("view_cost")
    msg_id = context.user_data.get("post_message_id")
    chat_id = context.user_data.get("post_chat_id")

    if user_id != ADMIN_ID:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET coin_view = coin_view - ? WHERE user_id=?", (cost, user_id))
        conn.commit()
        conn.close()

    try:
        await context.bot.forward_message(chat_id=VIEW_CHANNEL, from_chat_id=chat_id, message_id=msg_id)
        await query.message.edit_text("✅ پست شما با موفقیت ثبت شد و به کانال ویوگیر ارسال گردید.")
    except Exception as e:
        await query.message.edit_text(f"✅ سفارش ثبت شد ولی ارسال به کانال ویوگیر به دلیل عدم تنظیم درست کانال با خطا مواجه شد:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ سفارش لغو شد.")
    return ConversationHandler.END

# ----------------- TRANSFER FLOW -----------------
async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["transfer_type"] = "coin" if "سکه" in text else "diamond"
    await update.message.reply_text("لطفاً آیدی عددی اکانت مورد نظر را وارد کنید:")
    return WAITING_TRANSFER_USER

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

        if sender_id != ADMIN_ID and balance < amount:
            await update.message.reply_text("❌ موجودی شما کافی نیست!")
        else:
            if sender_id != ADMIN_ID:
                c.execute(f"UPDATE users SET {field} = {field} - ? WHERE user_id=?", (amount, sender_id))
            c.execute(f"UPDATE users SET {field} = {field} + ? WHERE user_id=?", (amount, target_id))
            conn.commit()
            await update.message.reply_text("✅ انتقال با موفقیت انجام شد.")
            await context.bot.send_message(chat_id=target_id, text=f"🎉 تعداد {amount} {t_type} از طرف کاربر `{sender_id}` به حساب شما واریز شد.")
        conn.close()
    except Exception:
        await update.message.reply_text("❌ خطایی رخ داد. آیدی یا مقدار وارد شده معتبر نیست.")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # گفتگوی ثبت سفارش ممبر
    member_order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_member_order, pattern="^m_")],
        states={
            WAIT_MEMBER_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_member_link)],
            WAIT_MEMBER_CONFIRM: [
                CallbackQueryHandler(confirm_member_order, pattern="^confirm_member_order$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_order, pattern="^cancel_order$")]
    )

    # گفتگوی ثبت سفارش ویو
    view_order_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_view_order, pattern="^v_")],
        states={
            WAIT_VIEW_POST: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_view_post)],
            WAIT_VIEW_CONFIRM: [
                CallbackQueryHandler(confirm_view_order, pattern="^confirm_view_order$"),
                CallbackQueryHandler(cancel_order, pattern="^cancel_order$")
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_order, pattern="^cancel_order$")]
    )

    # گفتگوی انتقال سکه و الماس
    transfer_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(💰 انتقال سکه|💎︎  انتقال الماس)$"), start_transfer)],
        states={
            WAITING_TRANSFER_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_transfer_user)],
            WAITING_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_transfer_amount)],
        },
        fallbacks=[]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(member_order_conv)
    application.add_handler(view_order_conv)
    application.add_handler(transfer_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    logging.info("ربات با موفقیت روشن شد...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
