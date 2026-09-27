import os
import sqlite3
import datetime
import logging
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
        referrer_id INTEGER DEFAULT 0
    )''')
    
    # جدول ثبت کلیک‌های یکتای کاربران روی هر پست یا لینک
    c.execute('''CREATE TABLE IF NOT EXISTS user_clicks (
        user_id INTEGER,
        target_id TEXT,
        PRIMARY KEY (user_id, target_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS post_views (
        post_id TEXT PRIMARY KEY,
        view_count INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

init_db()

def get_or_create_user(user_id, username="", referrer_id=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""SELECT user_id, username, coin_view, coin_member, ref_count, last_daily, 
                        admin_gift, total_views, today_views, lottery_wins, ref_commission 
                 FROM users WHERE user_id=?""", (user_id,))
    u = c.fetchone()
    if not u:
        c.execute("""INSERT INTO users 
            (user_id, username, coin_view, coin_member, ref_count, last_daily, admin_gift, total_views, today_views, lottery_wins, ref_commission, referrer_id) 
            VALUES (?, ?, 0, 0, 0, '', 0, 0, 0, 0, 0, ?)""", (user_id, username, referrer_id))
        conn.commit()
        
        if referrer_id and referrer_id != user_id:
            c.execute("""UPDATE users 
                         SET coin_view = coin_view + 200, 
                             coin_member = coin_member + 50, 
                             ref_count = ref_count + 1 
                         WHERE user_id=?""", (referrer_id,))
            conn.commit()
            
        c.execute("""SELECT user_id, username, coin_view, coin_member, ref_count, last_daily, 
                            admin_gift, total_views, today_views, lottery_wins, ref_commission 
                     FROM users WHERE user_id=?""", (user_id,))
        u = c.fetchone()
    conn.close()
    return u

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

# ----------------- CONVERSATION STATES -----------------
WAIT_VIEW_POST, WAIT_VIEW_CONFIRM = range(2)
WAIT_MEMBER_LINK, WAIT_MEMBER_CONFIRM = range(2, 4)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = 0
    if args and args[0].isdigit():
        referrer_id = int(args[0])

    get_or_create_user(user.id, user.username or "", referrer_id)
    await update.message.reply_text(f"سلام {user.first_name} عزیز، به ربات خوش آمدید!", reply_markup=main_keyboard())

# دستور مخصوص ادمین برای افزایش سکه بی‌نهایت خودتان (/add_admin_coin 10000 10000)
async def add_admin_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        coins = int(context.args[0])
        diamonds = int(context.args[1])
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ? WHERE user_id=?", (coins, diamonds, ADMIN_ID))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ با موفقیت {coins} سکه و {diamonds} الماس به حساب ادمین اضافه شد.")
    except:
        await update.message.reply_text("فرمت صحیح:\n`/add_admin_coin 1000 1000`", parse_mode="Markdown")

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

    elif text == "بازگشت به منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید.", reply_markup=main_keyboard())

    else:
        await update.message.reply_text("این بخش در حال حاضر در حال تنظیم است.", reply_markup=main_keyboard())

# ----------------- VIEW ADS FLOW -----------------
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

# ----------------- MEMBER ADS FLOW -----------------
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
    await query.message.edit_text("❌ ثبت سفارش لغو شد.")
    return ConversationHandler.END

# ----------------- BUTTON CALLBACKS (IN CHANNELS) -----------------
async def handle_channel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # ثبت بازدید
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

    # توربو
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

    # دریافت الماس
    elif data.startswith("get_diamond_"):
        target_info = data.replace("get_diamond_", "").split("_")
        target_id = target_info[1]
        channel_username = target_info[2] if len(target_info) > 2 else None

        # چک کردن دریافت تکراری
        c.execute("SELECT * FROM user_clicks WHERE user_id=? AND target_id=?", (user_id, f"m_{target_id}"))
        if c.fetchone():
            conn.close()
            await query.answer("❌ شما قبلاً برای این پست الماس دریافت کرده‌اید!", show_alert=True)
            return

        # بررسی عضویت کاربر در کانال (در صورت آیدی عمومی)
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_admin_coin", add_admin_coin))
    app.add_handler(view_conv)
    app.add_handler(member_conv)
    app.add_handler(CallbackQueryHandler(handle_channel_callbacks, pattern="^(do_view_|do_turbo_|get_diamond_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    logging.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
