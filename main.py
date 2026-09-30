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
ADMIN_IDS = [ADMIN_ID]  # لیست ادمین‌ها

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
        referrer_id INTEGER DEFAULT 0,
        tickets INTEGER DEFAULT 0,
        total_spent INTEGER DEFAULT 0,
        is_left INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_clicks (
        user_id INTEGER,
        target_id TEXT,
        click_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, target_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS post_views (
        post_id TEXT PRIMARY KEY,
        view_count INTEGER DEFAULT 0
    )''')

    # جدول تنظیمات عمومی ربات و پنل مدیریت
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
        id INTEGER PRIMARY KEY,
        card_number TEXT DEFAULT 'تنظیم نشده',
        gateway_url TEXT DEFAULT 'https://t.me/Admin_ID',
        daily_coin INTEGER DEFAULT 20,
        daily_diamond INTEGER DEFAULT 20,
        ref_coin INTEGER DEFAULT 200,
        ref_diamond INTEGER DEFAULT 50,
        monthly_gift_amount INTEGER DEFAULT 1000,
        monthly_gift_type TEXT DEFAULT 'coin',
        sponsors TEXT DEFAULT '',
        welcome_msg TEXT DEFAULT 'سلام! به ربات بزرگ ممبرگیر و ویوگیر خوش آمدید.',
        unsub_days INTEGER DEFAULT 3,
        unsub_penalty INTEGER DEFAULT 2,
        lottery_active INTEGER DEFAULT 1,
        lottery_mode TEXT DEFAULT 'هفتگی',
        lottery_p1 TEXT DEFAULT '1000 الماس',
        lottery_p2 TEXT DEFAULT '500 سکه',
        lottery_p3 TEXT DEFAULT '200 سکه',
        winner_1 TEXT DEFAULT '',
        winner_2 TEXT DEFAULT '',
        winner_3 TEXT DEFAULT ''
    )''')
    
    c.execute("INSERT OR IGNORE INTO bot_settings (id) VALUES (1)")
    conn.commit()
    conn.close()

init_db()

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    res = None
    if fetchone:
        res = c.fetchone()
    elif fetchall:
        res = c.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return res

def get_settings():
    return db_query("SELECT * FROM bot_settings WHERE id=1", fetchone=True)

def get_or_create_user(user_id, username="", referrer_id=0):
    u = db_query("SELECT * FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not u:
        st = get_settings()
        ref_c = st[5]
        ref_d = st[6]
        
        db_query("""INSERT INTO users 
            (user_id, username, coin_view, coin_member, ref_count, last_daily, admin_gift, total_views, today_views, lottery_wins, ref_commission, referrer_id, tickets, total_spent, is_left) 
            VALUES (?, ?, 0, 0, 0, '', 0, 0, 0, 0, 0, ?, 0, 0, 0)""", (user_id, username, referrer_id), commit=True)
        
        if referrer_id and referrer_id != user_id:
            db_query("""UPDATE users 
                         SET coin_view = coin_view + ?, 
                             coin_member = coin_member + ?, 
                             ref_count = ref_count + 1 
                         WHERE user_id=?""", (ref_c, ref_d, referrer_id), commit=True)
            
        u = db_query("SELECT * FROM users WHERE user_id=?", (user_id,), fetchone=True)
    return u

# ----------------- SPONSOR CHECK -----------------
async def check_sponsors(user_id, context):
    st = get_settings()
    sponsors_str = st[9]
    if not sponsors_str:
        return True
    
    sponsors = [s.strip() for s in sponsors_str.split(",") if s.strip()]
    for sp in sponsors:
        try:
            chat_id = sp if sp.startswith("-100") or sp.startswith("@") else f"@{sp}"
            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            pass
    return True

# ----------------- KEYBOARDS -----------------
def main_keyboard(user_id):
    kb = [
        ["💎جم اوری سکه رایگان"],
        ["💻حصاب کار بری مشحصات", "👥جذب زیر مجموعه"],
        ["📥ثبت تبلیغ ویو گیر و ممبر گیر"],
        ["👨‍💻🛍︎فروشگاه", "قرعه کشی"],
        ["💰 انتقال سکه", "💎︎  انتقال الماس"]
    ]
    if user_id in ADMIN_IDS:
        kb.append(["⚙️️ پنل مدیریت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_keyboard():
    kb = [
        ["📊 آمار کاربران", "⚙️ تنظیمات عمومی"],
        ["🎯 تنظیم سفارشات", "🛍️ تنظیمات فروشگاه"],
        ["🎁 تنظیمات پاداش و هدیه", "🎉 تنظیمات قرعه‌کشی"],
        ["🔒 تنظیمات اسپانسر و قفل", "👥 مدیریت کاربران (دستی)"],
        ["📢 ارسال پیام همگانی", "بازگشت به منوی اصلی"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- STATES -----------------
(WAIT_VIEW_POST, WAIT_VIEW_CONFIRM, WAIT_MEMBER_LINK, WAIT_MEMBER_CONFIRM, 
 WAIT_RECEIPT_PHOTO, ADMIN_STATE_DECIDE, SET_CARD, SET_GATEWAY, SET_DAILY, 
 SET_REF, SET_GIFTS, SET_LOTTERY_PRIZE, SET_SPONSOR, SET_WELCOME, SET_UNSUB_DAYS, 
 SET_UNSUB_PENALTY, SET_BROADCAST, MANAGE_USER_ID, MANAGE_USER_ACTION) = range(19)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = int(args[0]) if args and args[0].isdigit() else 0

    get_or_create_user(user.id, user.username or "", referrer_id)
    
    # اسپانسر اجباری
    is_joined = await check_sponsors(user.id, context)
    if not is_joined:
        st = get_settings()
        sponsors = [s.strip() for s in st[9].split(",") if s.strip()]
        ikb = []
        for sp in sponsors:
            url = f"https://t.me/{sp.replace('@', '')}"
            ikb.append([InlineKeyboardButton(f"📢 عضویت در {sp}", url=url)])
        ikb.append([InlineKeyboardButton("✅ عضو شدم / تایید", callback_data="check_sponsor_again")])
        
        await update.message.reply_text("⚠️ جهت استفاده از ربات، ابتدا باید در کانال‌های اسپانسر زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(ikb))
        return

    st = get_settings()
    await update.message.reply_text(f"{st[10]}\n\nسلام {user.first_name} عزیز، به ربات خوش آمدید!", reply_markup=main_keyboard(user.id))

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    u = get_or_create_user(user.id, user.username or "")
    st = get_settings()

    if text == "💎جم اوری سکه رایگان":
        today_str = str(datetime.date.today())
        if u[5] == today_str:
            await update.message.reply_text("❌ شما امروز سکه و الماس رایگان خود را دریافت کرده‌اید!\nلطفاً فردا مراجعه کنید.")
        else:
            db_query("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ?, last_daily = ? WHERE user_id=?", 
                     (st[3], st[4], today_str, user.id), commit=True)
            await update.message.reply_text(f"🎉 {st[3]} **سکه ویو** و {st[4]} **الماس ممبر** رایگان دریافت کردید!", parse_mode="Markdown")

    elif text == "💻حصاب کار بری مشحصات":
        msg = f"""💻 **مشخصات حساب کاربری:**

👤 **نام:** {user.first_name}
🆔 **آیدی:** `{u[0]}`
🎟 **بلیت‌های قرعه‌کشی:** {u[12]}
👁 **بازدیدهای شما:** {u[7]}
👥 **زیرمجموعه‌ها:** {u[4]}

💰 **موجودی سکه:** {u[2]}
💎 **موجودی الماس:** {u[3]}"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "👥جذب زیر مجموعه":
        bot_un = (await context.bot.get_me()).username
        msg = f"""👥 **جذب زیرمجموعه**

🎉 با دعوت از دوستان خود، **{st[5]} سکه ویو** و **{st[6]} الماس** بگیرید!

🔗 **لینک شما:**
`https://t.me/{bot_un}?start={user.id}`"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "قرعه کشی":
        if not st[13]:
            await update.message.reply_text("❌ **قرعه‌کشی در حال حاضر غیرفعال می‌باشد.**")
            return

        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟 ورود به قرعه کشی", callback_data="lottery_enter")],
            [InlineKeyboardButton("🏆 نمایش برندگان قرعه کشی", callback_data="lottery_winners")],
            [InlineKeyboardButton("🎁 نمایش جوایز قرعه کشی", callback_data="lottery_prizes")]
        ])
        await update.message.reply_text("🎉 **به بخش قرعه‌کشی خوش آمدید!**", reply_markup=ikb, parse_mode="Markdown")

    elif text == "👨‍💻🛍︎فروشگاه":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👁 خرید سکه ویوگیر", callback_data="shop_coins")],
            [InlineKeyboardButton("💎 خرید الماس ممبرگیر", callback_data="shop_diamonds")]
        ])
        await update.message.reply_text("🛍 **به فروشگاه خوش آمدید!** انتخاب کنید:", reply_markup=ikb)

    elif text == "⚙️ پنل مدیریت" and user.id in ADMIN_IDS:
        await update.message.reply_text("⚙️ **به پنل مدیریت ربات خوش آمدید:**", reply_markup=admin_keyboard(), parse_mode="Markdown")

    elif text == "📊 آمار کاربران" and user.id in ADMIN_IDS:
        total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        left_users = db_query("SELECT COUNT(*) FROM users WHERE is_left=1", fetchone=True)[0]
        total_tickets = db_query("SELECT SUM(tickets) FROM users", fetchone=True)[0] or 0
        total_sales = db_query("SELECT SUM(total_spent) FROM users", fetchone=True)[0] or 0
        top_view = db_query("SELECT username, total_views FROM users ORDER BY total_views DESC LIMIT 1", fetchone=True)
        
        msg = f"""📊 **آمار جامع ربات:**

👤 **کل کاربران:** {total_users:,} نفر
🚶 **لفت داده‌ها:** {left_users:,} نفر
🎟 **کل بلیت‌های قرعه‌‌کشی:** {total_tickets:,} عدد
💳 **مجموع فروش فروشگاه:** {total_sales:,} تومان

🏆 **بیشترین بازدیدکننده:** @{top_view[0] if top_view else 'نامشخص'} ({top_view[1] if top_view else 0} بازدید)"""
        await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------- CALLBACKS -----------------
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    st = get_settings()

    if data == "check_sponsor_again":
        if await check_sponsors(user.id, context):
            await query.message.delete()
            await query.message.reply_text("✅ عضویت شما تایید شد!", reply_markup=main_keyboard(user.id))
        else:
            await query.answer("❌ هنوز در تمام کانال‌ها عضو نشده‌اید!", show_alert=True)

    elif data == "lottery_enter":
        u = get_or_create_user(user.id)
        msg = f"""به قرعه کشی ربات خوش امدید
برای ورود در قرعه کشی باید از ربات خرید کنید و بلیت شانس دریافت کنید.

🎟 **بلیت شما:** {u[12]}

💵 ۵۰.۰۰۰ تومان خرید ⬅️ ۲ بلیت
💵 ۱۰۰.۰۰۰ تومان خرید ⬅️ ۴ بلیت
💵 ۲۰۰.۰۰۰ تومان خرید ⬅️ ۶ بلیت
💵 ۵۰۰.۰۰۰ تومان خرید ⬅️ ۱۰ بلیت"""
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ورود به فروشگاه", callback_data="shop_coins")]])
        await query.message.reply_text(msg, reply_markup=ikb)

    elif data == "lottery_winners":
        w1, w2, w3 = st[18], st[19], st[20]
        if not w1 and not w2 and not w3:
            await query.message.reply_text("هنوز برنده‌ای وجود ندارد")
        else:
            msg = f"🏆 **برندگان دوره قبل:**\n\n🥇 **نفر اول:** {w1}\n🥈 **نفر دوم:** {w2}\n🥉 **نفر سوم:** {w3}"
            await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "lottery_prizes":
        msg = f"🎁 **جوایز قرعه‌کشی:**\n\n🥇 **نفر اول:** {st[15]}\n🥈 **نفر دوم:** {st[16]}\n🥉 **نفر سوم:** {st[17]}"
        await query.message.reply_text(msg, parse_mode="Markdown")

# ----------------- MAIN -----------------
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    logging.info("Starting Bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
