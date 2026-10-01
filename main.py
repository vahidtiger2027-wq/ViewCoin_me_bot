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
ADMIN_ID = 5412332176
ADMIN_IDS = [ADMIN_ID]

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
        last_daily TEXT DEFAULT '',
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
        welcome_msg TEXT DEFAULT 'سلام! به ربات بزرگ خوش آمدید.',
        unsub_days INTEGER DEFAULT 3,
        unsub_penalty INTEGER DEFAULT 2,
        lottery_active INTEGER DEFAULT 1,
        lottery_mode TEXT DEFAULT 'هفتگی',
        lottery_p1 TEXT DEFAULT '100 الماس',
        lottery_p2 TEXT DEFAULT '1000 سکه',
        lottery_p3 TEXT DEFAULT '500 سکه',
        winner_1 TEXT DEFAULT 'هنوز مشخص نشده',
        winner_2 TEXT DEFAULT 'هنوز مشخص نشده',
        winner_3 TEXT DEFAULT 'هنوز مشخص نشده'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS lottery_packs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price INTEGER,
        tickets INTEGER
    )''')
    
    c.execute("INSERT OR IGNORE INTO bot_settings (id) VALUES (1)")

    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if "tickets" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN tickets INTEGER DEFAULT 0")

    c.execute("SELECT COUNT(*) FROM lottery_packs")
    if c.fetchone()[0] == 0:
        default_packs = [
            (50000, 2),
            (100000, 4),
            (150000, 4),
            (200000, 6),
            (500000, 10)
        ]
        c.executemany("INSERT INTO lottery_packs (price, tickets) VALUES (?, ?)", default_packs)

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
        ref_c = st[5] if st else 200
        ref_d = st[6] if st else 50
        
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

# ----------------- KEYBOARDS -----------------
def main_keyboard(user_id):
    kb = [
        ["💎 جم اوری سکه رایگان"],
        ["💻 حساب کاربری مشخصات", "👥 جذب زیر مجموعه"],
        ["📥 ثبت تبلیغ ویو گیر و ممبر گیر"],
        ["👨‍💻🛍 فروشگاه", "🎉 قرعه کشی"],
        ["💰 انتقال سکه", "💎 انتقال الماس"]
    ]
    if user_id in ADMIN_IDS:
        kb.append(["⚙ پنل مدیریت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_keyboard():
    kb = [
        ["📊 آمار کاربران", "💳 تنظیم شماره کارت"],
        ["🔗 تنظیم درگاه پرداخت", "🎁 تنظیم هدیه روزانه"],
        ["🔒 تنظیم اسپانسر", "🎉 تنظیمات جوایز قرعه‌کشی"],
        ["📢 ارسال پیام همگانی", "بازگشت به منوی اصلی"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = int(args[0]) if args and args[0].isdigit() else 0
    get_or_create_user(user.id, user.username or "", referrer_id)
    await update.message.reply_text(f"سلام {user.first_name} عزیز، خوش آمدید!", reply_markup=main_keyboard(user.id))

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بازگشت به منوی اصلی:", reply_markup=main_keyboard(update.effective_user.id))

# --- این تابع اصلی قرعه‌کشی با ۳ دکمه شیشه‌ای است ---
async def lottery_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_or_create_user(update.effective_user.id)
    tickets = u[12] if (u and len(u) > 12 and u[12] is not None) else 0
    st = get_settings()
    
    status_str = "🟢 فعال" if st and st[13] else "🔴 غیرفعال"
    mode_str = st[14] if st else "هفتگی"
    p1 = st[15] if st else "نامشخص"
    p2 = st[16] if st else "نامشخص"
    p3 = st[17] if st else "نامشخص"

    msg = f"""🎉 **قرعه‌کشی بزرگ ربات**

📌 **وضعیت:** {status_str}
📅 **بازه برگزاری:** {mode_str}

🎁 **جوایز این دوره:**
🥇 **نفر اول:** {p1}
🥈 **نفر دوم:** {p2}
🥉 **نفر سوم:** {p3}

🎫 **تعداد بلیت‌های شما:** {tickets:,}

لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"""

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟 ورود به قرعه کشی و خرید بلیت", callback_data="lottery_enter_inline")],
        [
            InlineKeyboardButton("🏆 نمایش برندگان", callback_data="lottery_winners_inline"),
            InlineKeyboardButton("🎁 نمایش جوایز", callback_data="lottery_prizes_inline")
        ]
    ])

    await update.message.reply_text(msg, reply_markup=ikb, parse_mode="Markdown")

async def lottery_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "lottery_enter_inline":
        u = get_or_create_user(update.effective_user.id)
        tickets = u[12] if len(u) > 12 and u[12] is not None else 0
        packs = db_query("SELECT id, price, tickets FROM lottery_packs ORDER BY id ASC", fetchall=True)
        ikb = []
        for p in packs:
            ikb.append([InlineKeyboardButton(f"قیمت: {p[1]:,} تومان | {p[2]} بلیت 🎫", callback_data=f"buy_pack_{p[0]}")])
            
        msg = f"""🎟 **ورود به قرعه‌کشی**

🎫 **تعداد بلیت‌های فعلی شما:** {tickets:,}

جهت افزایش شانس برنده شدن می‌توانید بسته‌های زیر را خریداری کنید:"""
        await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(ikb), parse_mode="Markdown")

    elif data == "lottery_winners_inline":
        st = get_settings()
        w1 = st[18] if st and len(st) > 18 and st[18] else "هنوز مشخص نشده"
        w2 = st[19] if st and len(st) > 19 and st[19] else "هنوز مشخص نشده"
        w3 = st[20] if st and len(st) > 20 and st[20] else "هنوز مشخص نشده"

        msg = f"""🏆 **برندگان دوره قبل قرعه‌کشی**

🥇 **نفر اول:** {w1}
🥈 **نفر دوم:** {w2}
🥉 **نفر سوم:** {w3}"""
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "lottery_prizes_inline":
        st = get_settings()
        p1 = st[15] if st else "نامشخص"
        p2 = st[16] if st else "نامشخص"
        p3 = st[17] if st else "نامشخص"
        status_str = "🟢 فعال" if st and st[13] else "🔴 غیرفعال"
        mode_str = st[14] if st else "هفتگی"

        msg = f"""🎁 **جوایز قرعه‌کشی این دوره**

📌 **وضعیت:** {status_str}
📅 **بازه برگزاری:** {mode_str}

🥇 **نفر اول:** {p1}
🥈 **نفر دوم:** {p2}
🥉 **نفر سوم:** {p3}"""
        await query.message.reply_text(msg, parse_mode="Markdown")

async def buy_pack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pack_id = query.data.replace("buy_pack_", "")
    pack = db_query("SELECT price, tickets FROM lottery_packs WHERE id=?", (pack_id,), fetchone=True)
    st = get_settings()
    if pack:
        msg = f"""💳 **سفارش خرید بلیت قرعه‌کشی**

🎫 تعداد بلیت: {pack[1]} عدد
💰 مبلغ: {pack[0]:,} تومان

لطفاً مبلغ را به کارت زیر واریز کنید:
`{st[1]}`"""
        await query.message.reply_text(msg, parse_mode="Markdown")

# ----------------- MAIN APP -----------------
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🎉 قرعه کشی$"), lottery_user_menu))
    app.add_handler(MessageHandler(filters.Regex("^بازگشت به منوی اصلی$"), back_to_main))
    
    app.add_handler(CallbackQueryHandler(lottery_inline_callback, pattern="^lottery_.*_inline$"))
    app.add_handler(CallbackQueryHandler(buy_pack_callback, pattern="^buy_pack_"))

    logging.info("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
