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
        welcome_msg TEXT DEFAULT 'سلام! به ربات خوش آمدید. لطفاً جهت استفاده در کانال‌های زیر عضو شوید:',
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

    c.execute('''CREATE TABLE IF NOT EXISTS sponsors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT UNIQUE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS lottery_packs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price INTEGER,
        tickets INTEGER
    )''')
    
    c.execute("INSERT OR IGNORE INTO bot_settings (id) VALUES (1)")

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
    st = get_settings()
    ref_c = st[5] if st else 200
    ref_d = st[6] if st else 50
    daily_c = st[3] if st else 20
    daily_d = st[4] if st else 20

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار کاربران", callback_data="adm_stats")],
        [InlineKeyboardButton(f"👥 هدیه زیرمجموعه ({ref_c}🪙 | {ref_d}💎)", callback_data="adm_ref_start")],
        [InlineKeyboardButton(f"🎁 هدیه روزانه ({daily_c}🪙 | {daily_d}💎)", callback_data="adm_daily_start")],
        [InlineKeyboardButton("💳 شماره کارت", callback_data="adm_card_start"), InlineKeyboardButton("🔗 درگاه/آیدی", callback_data="adm_gateway_start")],
        [InlineKeyboardButton("🔒 اسپانسر و جوین اجباری", callback_data="adm_sponsor_menu")],
        [InlineKeyboardButton("🎉 تنظیمات قرعه کشی", callback_data="adm_lottery_menu")],
        [InlineKeyboardButton("⏱ روزهای ماندگاری", callback_data="adm_unsub_start"), InlineKeyboardButton("⚠️ جریمه لفت", callback_data="adm_penalty_start")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast_start")]
    ])

# ----------------- CONVERSATION STATES -----------------
(
    SET_CARD, SET_GATEWAY,
    SET_REF_COIN, SET_REF_DIAMOND,
    SET_DAILY_DIAMOND, SET_DAILY_COIN,
    ADD_SPONSOR_LINK, SET_START_TEXT,
    SET_UNSUB_DAYS, SET_PENALTY,
    SET_LOTTERY_P1, SET_LOTTERY_P2, SET_LOTTERY_P3,
    BROADCAST_MSG
) = range(14)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username or "")
    await update.message.reply_text(f"سلام {user.first_name} عزیز، خوش آمدید!", reply_markup=main_keyboard(user.id))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text("⚙️ **پنل مدیریت ربات**\nیکی از گزینه‌های زیر را جهت تنظیم انتخاب کنید:", reply_markup=admin_inline_keyboard(), parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # 1. آمار دقیق کاربران
    if data == "adm_stats":
        total_u = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        left_u = db_query("SELECT COUNT(*) FROM users WHERE is_left=1", fetchone=True)[0]
        max_v = db_query("SELECT MAX(total_views) FROM users", fetchone=True)[0] or 0
        max_c = db_query("SELECT MAX(coin_view) FROM users", fetchone=True)[0] or 0
        max_d = db_query("SELECT MAX(coin_member) FROM users", fetchone=True)[0] or 0
        max_act = db_query("SELECT MAX(today_views) FROM users", fetchone=True)[0] or 0
        max_ref = db_query("SELECT MAX(ref_count) FROM users", fetchone=True)[0] or 0
        lottery_u = db_query("SELECT COUNT(*) FROM users WHERE tickets > 0", fetchone=True)[0]
        total_buy = db_query("SELECT SUM(total_spent) FROM users", fetchone=True)[0] or 0

        msg = f"""📊 **آمار کامل کاربران و ربات**

👥 تعداد کل کاربران: **{total_u:,}** نفر
🚪 لفت داده‌ها: **{left_u:,}** نفر

👁 بیشترین ویو: **{max_v:,}**
🪙 بیشترین سکه دریافتی: **{max_c:,}**
💎 بیشترین الماس دریافتی: **{max_d:,}**
🔥 بیشترین فعالیت امروز: **{max_act:,}**
👥 بالاترین جوین (زیرمجموعه‌گیری): **{max_ref:,}** نفر

🎫 شرکت‌کنندگان قرعه‌کشی: **{lottery_u:,}** نفر
💰 آمار خریدهای فروشگاه: **{total_buy:,}** تومان"""
        await query.message.reply_text(msg, parse_mode="Markdown")

    # 6. اسپانسر
    elif data == "adm_sponsor_menu":
        sponsors = db_query("SELECT id, link FROM sponsors", fetchall=True)
        ikb = [[InlineKeyboardButton("➕ افزودن لینک جدید", callback_data="adm_add_sponsor")],
               [InlineKeyboardButton("✏️ تنظیم متن استارت", callback_data="adm_set_start_text")]]
        for sp in sponsors:
            ikb.append([InlineKeyboardButton(f"❌ حذف: {sp[1]}", callback_data=f"del_sp_{sp[0]}")])
        
        await query.message.reply_text("🔒 **مدیریت اسپانسر و جوین اجباری**\nبرای حذف هر لینک روی دکمه مربوطه بزنید:", reply_markup=InlineKeyboardMarkup(ikb))

    elif data.startswith("del_sp_"):
        sp_id = data.replace("del_sp_", "")
        db_query("DELETE FROM sponsors WHERE id=?", (sp_id,), commit=True)
        await query.message.reply_text("✅ لینک اسپانسر با موفقیت حذف شد.")

    # 7. قرعه کشی
    elif data == "adm_lottery_menu":
        st = get_settings()
        status_str = "🟢 فعال" if st and st[13] else "🔴 غیرفعال"
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 تنظیم جوایز (۱ تا ۳)", callback_data="adm_set_lottery_prizes")],
            [InlineKeyboardButton("🟢 روشن کردن", callback_data="lottery_toggle_1"), InlineKeyboardButton("🔴 خاموش کردن", callback_data="lottery_toggle_0")]
        ])
        await query.message.reply_text(f"🎉 **تنظیمات قرعه‌کشی**\nوضعیت فعلی: **{status_str}**", reply_markup=ikb, parse_mode="Markdown")

    elif data.startswith("lottery_toggle_"):
        val = int(data.replace("lottery_toggle_", ""))
        db_query("UPDATE bot_settings SET lottery_active=? WHERE id=1", (val,), commit=True)
        await query.message.reply_text("✅ وضعیت قرعه‌کشی با موفقیت به روز شد.")

# ----------------- CONVERSATIONS -----------------
async def start_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("👥 **مرحله اول:** لطفاً **مقدار سکه** هدیه زیرمجموعه‌گیری را وارد کنید:")
    return SET_REF_COIN

async def save_ref_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ref_coin"] = int(update.message.text.strip())
    await update.message.reply_text("👥 **مرحله دوم:** لطفاً **مقدار الماس** هدیه زیرمجموعه‌گیری را وارد کنید:")
    return SET_REF_DIAMOND

async def save_ref_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = int(update.message.text.strip())
    c = context.user_data.get("ref_coin", 200)
    db_query("UPDATE bot_settings SET ref_coin=?, ref_diamond=? WHERE id=1", (c, d), commit=True)
    await update.message.reply_text(f"✅ هدیه زیرمجموعه‌گیری تنظیم شد:\n🪙 {c} سکه | 💎 {d} الماس")
    return ConversationHandler.END

async def start_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("💳 لطفاً شماره کارت جدید **۱۶ رقمی** را وارد کنید:")
    return SET_CARD

async def save_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card = update.message.text.strip()
    db_query("UPDATE bot_settings SET card_number=? WHERE id=1", (card,), commit=True)
    await update.message.reply_text(f"✅ شماره کارت جدید ثبت شد:\n`{card}`", parse_mode="Markdown")
    return ConversationHandler.END

async def start_gateway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🔗 لطفاً لینک یا آیدی جدید درگاه پرداخت را وارد کنید:")
    return SET_GATEWAY

async def save_gateway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gw = update.message.text.strip()
    db_query("UPDATE bot_settings SET gateway_url=? WHERE id=1", (gw,), commit=True)
    await update.message.reply_text(f"✅ درگاه پرداخت به روز شد:\n{gw}")
    return ConversationHandler.END

async def start_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🎁 **مرحله اول:** لطفاً **مقدار الماس** هدیه روزانه را وارد کنید:")
    return SET_DAILY_DIAMOND

async def save_daily_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["daily_d"] = int(update.message.text.strip())
    await update.message.reply_text("🎁 **مرحله دوم:** لطفاً **مقدار سکه** هدیه روزانه را وارد کنید:")
    return SET_DAILY_COIN

async def save_daily_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = int(update.message.text.strip())
    d = context.user_data.get("daily_d", 20)
    db_query("UPDATE bot_settings SET daily_coin=?, daily_diamond=? WHERE id=1", (c, d), commit=True)
    await update.message.reply_text(f"✅ هدیه روزانه تنظیم شد:\n💎 {d} الماس | 🪙 {c} سکه")
    return ConversationHandler.END

async def start_add_sponsor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🔒 لطفاً لینک جدید کانال اسپانسر را ارسال کنید:")
    return ADD_SPONSOR_LINK

async def save_sponsor_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    db_query("INSERT OR IGNORE INTO sponsors (link) VALUES (?)", (link,), commit=True)
    await update.message.reply_text("✅ لینک جدید اسپانسر اضافه شد.")
    return ConversationHandler.END

async def start_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✏️ متن جدید استارت ربات را ارسال کنید:")
    return SET_START_TEXT

async def save_start_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    db_query("UPDATE bot_settings SET welcome_msg=? WHERE id=1", (txt,), commit=True)
    await update.message.reply_text("✅ متن استارت ذخیره شد.")
    return ConversationHandler.END

async def start_lottery_prizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🥇 جایزه **نفر اول** را وارد کنید:")
    return SET_LOTTERY_P1

async def save_p1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["p1"] = update.message.text.strip()
    await update.message.reply_text("🥈 جایزه **نفر دوم** را وارد کنید:")
    return SET_LOTTERY_P2

async def save_p2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["p2"] = update.message.text.strip()
    await update.message.reply_text("🥉 جایزه **نفر سوم** را وارد کنید:")
    return SET_LOTTERY_P3

async def save_p3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p3 = update.message.text.strip()
    p1 = context.user_data.get("p1", "نامشخص")
    p2 = context.user_data.get("p2", "نامشخص")
    db_query("UPDATE bot_settings SET lottery_p1=?, lottery_p2=?, lottery_p3=? WHERE id=1", (p1, p2, p3), commit=True)
    await update.message.reply_text("✅ جوایز ۱ تا ۳ قرعه‌کشی به روز رسانی شد.")
    return ConversationHandler.END

async def start_unsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("⏱ تعداد **روزهای ماندگاری** در کانال را وارد کنید:")
    return SET_UNSUB_DAYS

async def save_unsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = int(update.message.text.strip())
    db_query("UPDATE bot_settings SET unsub_days=? WHERE id=1", (days,), commit=True)
    await update.message.reply_text(f"✅ ماندگاری در کانال: **{days} روز** تعیین شد.", parse_mode="Markdown")
    return ConversationHandler.END

async def start_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("⚠ مقدار **جریمه لفت** را وارد کنید:")
    return SET_PENALTY

async def save_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pen = int(update.message.text.strip())
    db_query("UPDATE bot_settings SET unsub_penalty=? WHERE id=1", (pen,), commit=True)
    await update.message.reply_text(f"✅ جریمه لفت: **{pen} عدد** ثبت شد.", parse_mode="Markdown")
    return ConversationHandler.END

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("📢 پیام همگانی خود را بفرستید:")
    return BROADCAST_MSG

async def save_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db_query("SELECT user_id FROM users", fetchall=True)
    count = 0
    for u in users:
        try:
            await context.bot.copy_message(chat_id=u[0], from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ پیام همگانی به **{count}** کاربر ارسال شد.")
    return ConversationHandler.END

async def cancel_fallback_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("منوی اصلی:", reply_markup=main_keyboard(update.effective_user.id))

# ----------------- MAIN -----------------
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    BTN_FILTER = filters.Regex("^(💎|💻|👥|📥|👨‍💻🛍|🎉|💰|⚙).*")
    fallbacks = [MessageHandler(BTN_FILTER, cancel_fallback_cmd)]

    ref_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ref, pattern="^adm_ref_start$")],
        states={
            SET_REF_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_ref_coin)],
            SET_REF_DIAMOND: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_ref_diamond)]
        },
        fallbacks=fallbacks
    )

    card_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_card, pattern="^adm_card_start$")],
        states={SET_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_card)]},
        fallbacks=fallbacks
    )

    gw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_gateway, pattern="^adm_gateway_start$")],
        states={SET_GATEWAY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_gateway)]},
        fallbacks=fallbacks
    )

    daily_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_daily, pattern="^adm_daily_start$")],
        states={
            SET_DAILY_DIAMOND: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_daily_diamond)],
            SET_DAILY_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_daily_coin)]
        },
        fallbacks=fallbacks
    )

    sp_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_sponsor, pattern="^adm_add_sponsor$")],
        states={ADD_SPONSOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_sponsor_link)]},
        fallbacks=fallbacks
    )

    sp_txt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_set_text, pattern="^adm_set_start_text$")],
        states={SET_START_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_start_text)]},
        fallbacks=fallbacks
    )

    lottery_prizes_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_lottery_prizes, pattern="^adm_set_lottery_prizes$")],
        states={
            SET_LOTTERY_P1: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_p1)],
            SET_LOTTERY_P2: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_p2)],
            SET_LOTTERY_P3: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_p3)]
        },
        fallbacks=fallbacks
    )

    unsub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_unsub, pattern="^adm_unsub_start$")],
        states={SET_UNSUB_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_unsub)]},
        fallbacks=fallbacks
    )

    penalty_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_penalty, pattern="^adm_penalty_start$")],
        states={SET_PENALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~BTN_FILTER, save_penalty)]},
        fallbacks=fallbacks
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_broadcast, pattern="^adm_broadcast_start$")],
        states={BROADCAST_MSG: [MessageHandler(~filters.COMMAND & ~BTN_FILTER, save_broadcast)]},
        fallbacks=fallbacks
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^⚙ پنل مدیریت$"), admin_panel))

    app.add_handler(ref_conv)
    app.add_handler(card_conv)
    app.add_handler(gw_conv)
    app.add_handler(daily_conv)
    app.add_handler(sp_add_conv)
    app.add_handler(sp_txt_conv)
    app.add_handler(lottery_prizes_conv)
    app.add_handler(unsub_conv)
    app.add_handler(penalty_conv)
    app.add_handler(broadcast_conv)

    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_.*|^del_sp_.*|^lottery_toggle_.*"))

    logging.info("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
