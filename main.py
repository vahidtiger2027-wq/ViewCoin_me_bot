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
        winner_3 TEXT DEFAULT 'هنوز مشخص نشده',
        coin_per_view INTEGER DEFAULT 1,
        diamond_per_member INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS lottery_packs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price INTEGER,
        tickets INTEGER
    )''')
    
    c.execute("INSERT OR IGNORE INTO bot_settings (id) VALUES (1)")

    # Safe Column Alterations
    c.execute("PRAGMA table_info(bot_settings)")
    cols = [col[1] for col in c.fetchall()]
    if "coin_per_view" not in cols:
        c.execute("ALTER TABLE bot_settings ADD COLUMN coin_per_view INTEGER DEFAULT 1")
    if "diamond_per_member" not in cols:
        c.execute("ALTER TABLE bot_settings ADD COLUMN diamond_per_member INTEGER DEFAULT 1")

    c.execute("SELECT COUNT(*) FROM lottery_packs")
    if c.fetchone()[0] == 0:
        default_packs = [(50000, 2), (100000, 4), (150000, 4), (200000, 6), (500000, 10)]
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

def admin_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار کاربران", callback_data="adm_stats")],
        [InlineKeyboardButton("💳 شماره کارت", callback_data="adm_card"), InlineKeyboardButton("🔗 درگاه پرداخت", callback_data="adm_gateway")],
        [InlineKeyboardButton("🎁 هدیه روزانه", callback_data="adm_daily"), InlineKeyboardButton("👥 هدیه زیرمجموعه", callback_data="adm_ref")],
        [InlineKeyboardButton("🔒 اسپانسر (جوین اجباری)", callback_data="adm_sponsor")],
        [InlineKeyboardButton("👁 نرخ ویو", callback_data="adm_rate_view"), InlineKeyboardButton("👤 نرخ ممبر", callback_data="adm_rate_member")],
        [InlineKeyboardButton("⚠️ جریمه لفت", callback_data="adm_penalty"), InlineKeyboardButton("⏱ ماندگاری در کانال", callback_data="adm_unsub_days")],
        [InlineKeyboardButton("🎉 تنظیمات قرعه کشی", callback_data="adm_lottery_menu")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast")]
    ])

# ----------------- CONVERSATION STATES -----------------
(
    SET_CARD, SET_GATEWAY, SET_DAILY_COIN, SET_DAILY_DIAMOND,
    SET_REF_COIN, SET_REF_DIAMOND, SET_SPONSOR, SET_RATE_VIEW,
    SET_RATE_MEMBER, SET_PENALTY, SET_UNSUB_DAYS, SET_BROADCAST
) = range(12)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username or "")
    await update.message.reply_text(f"سلام {user.first_name} عزیز، خوش آمدید!", reply_markup=main_keyboard(user.id))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text("⚙️ **پنل مدیریت ربات**\nجهت تنظیم هر بخش دکمه مربوطه را انتخاب کنید:", reply_markup=admin_inline_keyboard(), parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "adm_stats":
        total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        await query.message.reply_text(f"📊 **آمار کاربران:**\n\n👥 کل اعضا: **{total_users}** نفر", parse_mode="Markdown")

    elif data == "adm_lottery_menu":
        st = get_settings()
        status_str = "🟢 روشن" if st and st[13] else "🔴 خاموش"
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("خاموش 🔴", callback_data="lottery_off"), InlineKeyboardButton("روشن 🟢", callback_data="lottery_on")]
        ])
        await query.message.reply_text(f"🎉 **تنظیمات قرعه کشی**\nوضعیت فعلی: {status_str}", reply_markup=ikb)

# ----------------- CONVERSATIONS -----------------
async def start_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("💳 لطفاً شماره کارت جدید را وارد کنید:")
    return SET_CARD

async def save_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_query("UPDATE bot_settings SET card_number = ? WHERE id = 1", (update.message.text.strip(),), commit=True)
    await update.message.reply_text("✅ شماره کارت ذخیره شد.")
    return ConversationHandler.END

async def start_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("👥 لطفاً **تعداد سکه** هدیه زیرمجموعه‌گیری را وارد کنید:")
    return SET_REF_COIN

async def save_ref_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ref_coin"] = int(update.message.text.strip())
    await update.message.reply_text("حال لطفاً **تعداد الماس** هدیه زیرمجموعه‌گیری را وارد کنید:")
    return SET_REF_DIAMOND

async def save_ref_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = int(update.message.text.strip())
    c = context.user_data.get("ref_coin", 200)
    db_query("UPDATE bot_settings SET ref_coin = ?, ref_diamond = ? WHERE id = 1", (c, d), commit=True)
    await update.message.reply_text(f"✅ پورسانت زیرمجموعه تنظیم شد:\n🪙 {c} سکه | 💎 {d} الماس")
    return ConversationHandler.END

async def start_rate_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("👁 برای ۱ بازدید، کاربر چند **سکه** باید پرداخت کند؟")
    return SET_RATE_VIEW

async def save_rate_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = int(update.message.text.strip())
    db_query("UPDATE bot_settings SET coin_per_view = ? WHERE id = 1", (v,), commit=True)
    await update.message.reply_text(f"✅ هزینه هر بازدید: **{v} سکه** تنظیم شد.", parse_mode="Markdown")
    return ConversationHandler.END

async def start_rate_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("👤 برای ۱ ممبر، کاربر چند **الماس** باید پرداخت کند؟")
    return SET_RATE_MEMBER

async def save_rate_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = int(update.message.text.strip())
    db_query("UPDATE bot_settings SET diamond_per_member = ? WHERE id = 1", (m,), commit=True)
    await update.message.reply_text(f"✅ هزینه هر ممبر: **{m} الماس** تنظیم شد.", parse_mode="Markdown")
    return ConversationHandler.END

async def start_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⚠️ در صورت لفت زودتر از موعد، چند **الماس/سکه** به عنوان جریمه کسر شود؟")
    return SET_PENALTY

async def save_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = int(update.message.text.strip())
    db_query("UPDATE bot_settings SET unsub_penalty = ? WHERE id = 1", (p,), commit=True)
    await update.message.reply_text(f"✅ جریمه لفت: **{p} عدد** تنظیم شد.", parse_mode="Markdown")
    return ConversationHandler.END

async def start_unsub_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏱ کاربر چند **روز** باید در کانال بماند تا جریمه نشود؟")
    return SET_UNSUB_DAYS

async def save_unsub_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = int(update.message.text.strip())
    db_query("UPDATE bot_settings SET unsub_days = ? WHERE id = 1", (d,), commit=True)
    await update.message.reply_text(f"✅ روزهای ماندگاری: **{d} روز** تنظیم شد.", parse_mode="Markdown")
    return ConversationHandler.END

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("منوی اصلی:", reply_markup=main_keyboard(update.effective_user.id))

# ----------------- MAIN -----------------
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    BTN_FILTER = filters.Regex("^(💳|🔗|🎁|👥|🎉|🔒|⏱|📢|📊|⚙).*")
    cancel_fallback = [MessageHandler(BTN_FILTER, back_to_main)]

    # Conversations for Admin Buttons
    card_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_card, pattern="^adm_card$")],
        states={SET_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_card)]},
        fallbacks=cancel_fallback
    )

    ref_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ref, pattern="^adm_ref$")],
        states={
            SET_REF_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_ref_coin)],
            SET_REF_DIAMOND: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_ref_diamond)]
        },
        fallbacks=cancel_fallback
    )

    rate_view_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_rate_view, pattern="^adm_rate_view$")],
        states={SET_RATE_VIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_rate_view)]},
        fallbacks=cancel_fallback
    )

    rate_member_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_rate_member, pattern="^adm_rate_member$")],
        states={SET_RATE_MEMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_rate_member)]},
        fallbacks=cancel_fallback
    )

    penalty_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_penalty, pattern="^adm_penalty$")],
        states={SET_PENALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_penalty)]},
        fallbacks=cancel_fallback
    )

    unsub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_unsub_days, pattern="^adm_unsub_days$")],
        states={SET_UNSUB_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_unsub_days)]},
        fallbacks=cancel_fallback
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^⚙ پنل مدیریت$"), admin_panel))

    app.add_handler(card_conv)
    app.add_handler(ref_conv)
    app.add_handler(rate_view_conv)
    app.add_handler(rate_member_conv)
    app.add_handler(penalty_conv)
    app.add_handler(unsub_conv)

    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_.*"))

    logging.info("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
