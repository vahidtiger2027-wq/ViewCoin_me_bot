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
        lottery_p1 TEXT DEFAULT '0 الماس و 0 سکه',
        lottery_p2 TEXT DEFAULT '0 الماس و 0 سکه',
        lottery_p3 TEXT DEFAULT '0 الماس و 0 سکه',
        winner_1 TEXT DEFAULT '',
        winner_2 TEXT DEFAULT '',
        winner_3 TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS lottery_packs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price INTEGER,
        tickets INTEGER
    )''')
    
    c.execute("INSERT OR IGNORE INTO bot_settings (id) VALUES (1)")
    
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
        ["👨‍💻🛍فروشگاه", "قرعه کشی"],
        ["💰 انتقال سکه", "💎︎  انتقال الماس"]
    ]
    if user_id in ADMIN_IDS:
        kb.append(["⚙ پنل مدیریت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_keyboard():
    kb = [
        ["📊 آمار کاربران", "💳 تنظیم شماره کارت"],
        ["🔗 تنظیم درگاه پرداخت", "🎁 تنظیم هدیه روزانه"],
        ["👥 تنظیم زیرمجموعه", "🎉 تنظیمات جوایز قرعه‌کشی"],
        ["🔒 تنظیم اسپانسر", "⏱ تنظیم روز ماندگاری (ضد لفت)"],
        ["📢 ارسال پیام همگانی", "بازگشت به منوی اصلی"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- CONVERSATION STATES -----------------
(WAIT_CARD_NUM, WAIT_GATEWAY, WAIT_DAILY_C, WAIT_DAILY_D, 
 WAIT_REF_C, WAIT_REF_D, WAIT_BROADCAST, WAIT_SPONSORS,
 WAIT_TRANSFER_COIN_ID, WAIT_TRANSFER_COIN_AMT,
 WAIT_TRANSFER_DIAMOND_ID, WAIT_TRANSFER_DIAMOND_AMT,
 WAIT_LOTTERY_PRIZE_VAL1, WAIT_LOTTERY_PRIZE_VAL2,
 WAIT_TICKET_PRICE, WAIT_TICKET_COUNT) = range(16)

# ----------------- START & USER HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = int(args[0]) if args and args[0].isdigit() else 0

    get_or_create_user(user.id, user.username or "", referrer_id)
    
    if not await check_sponsors(user.id, context):
        st = get_settings()
        sponsors = [s.strip() for s in st[9].split(",") if s.strip()]
        ikb = []
        for sp in sponsors:
            url = f"https://t.me/{sp.replace('@', '')}"
            ikb.append([InlineKeyboardButton(f"📢 عضویت در {sp}", url=url)])
        ikb.append([InlineKeyboardButton("✅ عضو شدم / تایید", callback_data="check_sponsor_again")])
        await update.message.reply_text("⚠️ برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(ikb))
        return

    st = get_settings()
    await update.message.reply_text(f"{st[10]}\n\nسلام {user.first_name} عزیز، خوش آمدید!", reply_markup=main_keyboard(user.id))

async def check_sponsor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if await check_sponsors(user.id, context):
        await query.message.delete()
        st = get_settings()
        await context.bot.send_message(chat_id=user.id, text=f"✅ عضویت شما تایید شد!\n\n{st[10]}", reply_markup=main_keyboard(user.id))
    else:
        await query.answer("❌ شما هنوز در همه کانال‌ها عضو نشده‌‌اید!", show_alert=True)

async def user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = db_query("SELECT * FROM users WHERE user_id=?", (update.effective_user.id,), fetchone=True)
    if not u:
        return
    msg = f"""💻 **حساب کاربری شما:**

🆔 **شناسه عددی:** `{u[0]}`
🪙 **سکه بازدید:** {u[2]}
💎 **الماس ممبر:** {u[3]}
👥 **تعداد زیرمجموعه:** {u[4]}
🎫 **تعداد بلیت قرعه‌کشی:** {u[12]}
🎁 **جوایز قرعه‌کشی برنده شده:** {u[9]}
💰 **پورسانت زیرمجموعه:** {u[10]}"""
    await update.message.reply_text(msg, parse_mode="Markdown")

async def get_free_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id=?", (user_id,), fetchone=True)
    st = get_settings()
    
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if u[5] == today_str:
        await update.message.reply_text("❌ شما هدیه روزانه امروز خود را دریافت کرده‌اید. فردا دوباره تلاش کنید!")
        return

    db_query("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ?, last_daily = ? WHERE user_id = ?",
             (st[3], st[4], today_str, user_id), commit=True)
    await update.message.reply_text(f"🎁 هدیه روزانه شما شامل {st[3]} سکه و {st[4]} الماس با موفقیت واریز شد!")

async def ref_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_info = await context.bot.get_me()
    st = get_settings()
    user_id = update.effective_user.id
    link = f"https://t.me/{bot_info.username}?start={user_id}"
    msg = f"""👥 **برنامه دعوت دوستان**

با دعوت هر دوست به ربات:
🪙 **{st[5]} سکه**
💎 **{st[6]} الماس**
دریافت کنید!

🔗 **لینک اختصاصی شما:**
`{link}`"""
    await update.message.reply_text(msg, parse_mode="Markdown")

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = get_settings()
    msg = f"""👨‍💻🛍 **فروشگاه ربات**

💳 **شماره کارت جهت واریز:**
`{st[1]}`

🔗 **لینک درگاه پرداخت:**
{st[2]}

پس از واریز، عکس فیش واریزی را برای پشتیبانی ارسال کنید."""
    await update.message.reply_text(msg, parse_mode="Markdown")

async def lottery_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = get_settings()
    u = db_query("SELECT * FROM users WHERE user_id=?", (update.effective_user.id,), fetchone=True)
    status_str = "🟢 فعال" if st[13] else "🔴 غیرفعال"
    
    msg = f"""🎉 **قرعه‌کشی بزرگ ربات**

📌 **وضعیت:** {status_str}
📅 **بازه برگزاری:** {st[14]}

🎁 **جوایز این دوره:**
🥇 **نفر اول:** {st[15]}
🥈 **نفر دوم:** {st[16]}
🥉 **نفر سوم:** {st[17]}

🎫 **تعداد بلیت‌های شما:** {u[12]}

شما با خرید از فروشگاه یا فعالیت در ربات بلیت قرعه‌کشی دریافت می‌کنید!"""
    await update.message.reply_text(msg, parse_mode="Markdown")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بازگشت به منوی اصلی:", reply_markup=main_keyboard(update.effective_user.id))

# ----------------- ADMIN PANEL HANDLERS -----------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text("⚙️ به پنل مدیریت خوش آمدید:", reply_markup=admin_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    await update.message.reply_text(f"📊 **آمار ربات:**\n\n👥 کل کاربران: **{total_users}** نفر", parse_mode="Markdown")
# ----------------- LOTTERY ADMIN SETTINGS -----------------
async def lottery_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    st = get_settings()
    status_str = "🟢 روشن" if st[13] else "🔴 خاموش"
    
    ikb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("خاموش کردن قرعه کشی 🔴", callback_data="lottery_off"),
            InlineKeyboardButton("روشن کردن قرعه کشی 🟢", callback_data="lottery_on")
        ],
        [
            InlineKeyboardButton("هفتگی 📅", callback_data="lottery_period_7"),
            InlineKeyboardButton("۱۵ روزه 📅", callback_data="lottery_period_15"),
            InlineKeyboardButton("ماهانه 📅", callback_data="lottery_period_30")
        ],
        [InlineKeyboardButton("🎁 تنظیم جوایز اول تا سوم", callback_data="set_prizes_menu")],
        [InlineKeyboardButton("🎫 تنظیم قیمت بیلیت قرعه کشی", callback_data="set_ticket_prices_menu")]
    ])
    msg = f"⚙️ **تنظیمات قرعه‌کشی**\n\nوضعیت فعلی: **{status_str}**\nبازه فعلی: **{st[14]}**"
    await update.message.reply_text(msg, reply_markup=ikb, parse_mode="Markdown")

async def handle_lottery_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data in ["lottery_on", "lottery_off"]:
        is_active = 1 if data == "lottery_on" else 0
        db_query("UPDATE bot_settings SET lottery_active = ? WHERE id = 1", (is_active,), commit=True)
        txt = "✅ قرعه‌کشی روشن شد." if is_active else "🔴 قرعه‌کشی خاموش شد."
        await query.message.edit_text(txt)

    elif data.startswith("lottery_period_"):
        days = int(data.split("_")[2])
        mode_str = "هفتگی" if days == 7 else ("۱۵ روزه" if days == 15 else "ماهانه")
        db_query("UPDATE bot_settings SET lottery_mode = ? WHERE id = 1", (mode_str,), commit=True)

        today_dt = datetime.date.today()
        end_dt = today_dt + datetime.timedelta(days=days)
        today_str = today_dt.strftime("%Y/%m/%d")
        end_str = end_dt.strftime("%Y/%m/%d")

        broadcast_msg = f"💰🎁قرعه کشی ربات از امروز ( {today_str} ) اغاز شد  قرعه کشی در روز  ( {end_str} ) انجام میشود برایه این که یکی از برندگان ما باشید در قرعه کشی ما  شرکت کنید😍💰"

        all_users = db_query("SELECT user_id FROM users", fetchall=True)
        for u in all_users:
            try:
                await context.bot.send_message(chat_id=u[0], text=broadcast_msg)
            except:
                pass
        
        await query.message.edit_text(f"✅ بازه {mode_str} انتخاب شد و پیام همگانی ارسال گردید.")

    elif data == "set_prizes_menu":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🥇 جوایز نفر اول", callback_data="prize_rank_1")],
            [InlineKeyboardButton("🥈 جوایز نفر دوم", callback_data="prize_rank_2")],
            [InlineKeyboardButton("🥉 جوایز نفر سوم", callback_data="prize_rank_3")]
        ])
        await query.message.edit_text("لطفاً رتبه جایزه مورد نظر را انتخاب کنید:", reply_markup=ikb)

    elif data.startswith("prize_rank_"):
        rank = data.split("_")[2]
        context.user_data["prize_rank"] = rank
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪙 سکه", callback_data="p_type_coin"), InlineKeyboardButton("💎 الماس", callback_data="p_type_diamond")],
            [InlineKeyboardButton("💎🪙 هردو", callback_data="p_type_both")]
        ])
        await query.message.edit_text(f"نوع جایزه را برای **نفر {rank}** انتخاب کنید:", reply_markup=ikb, parse_mode="Markdown")

    elif data == "set_ticket_prices_menu":
        packs = db_query("SELECT id, price, tickets FROM lottery_packs ORDER BY id ASC", fetchall=True)
        ikb = []
        for p in packs:
            ikb.append([InlineKeyboardButton(f"قیمت ( {p[1]:,} )   بیلیت  ( {p[2]} )", callback_data=f"edit_pack_{p[0]}")])
        await query.message.edit_text("⚙️ **کادرهای ۵ گانه تنظیم قیمت و بلیت:**\nجهت ویرایش روی هر کادر کلیک کنید:", reply_markup=InlineKeyboardMarkup(ikb), parse_mode="Markdown")

# ----------------- PRIZE & PACK CONVERSATION HANDLERS -----------------
async def start_prize_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    p_type = query.data.replace("p_type_", "")
    context.user_data["prize_type"] = p_type
    rank = context.user_data.get("prize_rank")

    if p_type in ["both", "diamond"]:
        await query.message.reply_text(f"مقدار **الماس** برای نفر {rank} را وارد کنید:", parse_mode="Markdown")
    else:
        await query.message.reply_text(f"مقدار **سکه** برای نفر {rank} را وارد کنید:", parse_mode="Markdown")
    return WAIT_LOTTERY_PRIZE_VAL1

async def receive_prize_val1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val1 = update.message.text.strip()
    if not val1.isdigit():
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید:")
        return WAIT_LOTTERY_PRIZE_VAL1

    p_type = context.user_data.get("prize_type")
    rank = context.user_data.get("prize_rank")

    if p_type == "both":
        context.user_data["temp_diamond"] = val1
        await update.message.reply_text(f"حال مقدار **سکه** را برای نفر {rank} وارد کنید:", parse_mode="Markdown")
        return WAIT_LOTTERY_PRIZE_VAL2
    elif p_type == "diamond":
        text_str = f"{val1} الماس"
    else:
        text_str = f"{val1} سکه"

    col_name = f"lottery_p{rank}"
    db_query(f"UPDATE bot_settings SET {col_name} = ? WHERE id = 1", (text_str,), commit=True)
    await update.message.reply_text(f"✅ جایزه نفر {rank} تنظیم شد: **{text_str}**", parse_mode="Markdown")
    return ConversationHandler.END

async def receive_prize_val2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val2 = update.message.text.strip()
    if not val2.isdigit():
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید:")
        return WAIT_LOTTERY_PRIZE_VAL2

    diamond_val = context.user_data.get("temp_diamond")
    rank = context.user_data.get("prize_rank")
    text_str = f"{diamond_val} الماس و {val2} سکه"

    col_name = f"lottery_p{rank}"
    db_query(f"UPDATE bot_settings SET {col_name} = ? WHERE id = 1", (text_str,), commit=True)
    await update.message.reply_text(f"✅ جایزه نفر {rank} تنظیم شد: **{text_str}**", parse_mode="Markdown")
    return ConversationHandler.END

async def start_edit_pack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pack_id = int(query.data.split("_")[2])
    context.user_data["edit_pack_id"] = pack_id
    await query.message.reply_text("لطفاً **قیمت جدید (تومان)** را وارد کنید:")
    return WAIT_TICKET_PRICE

async def receive_pack_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = update.message.text.strip()
    if not price.isdigit():
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید:")
        return WAIT_TICKET_PRICE

    context.user_data["temp_pack_price"] = int(price)
    await update.message.reply_text("لطفاً **تعداد بلیت** مربوط به این قیمت را وارد کنید:")
    return WAIT_TICKET_COUNT

async def receive_pack_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tickets = update.message.text.strip()
    if not tickets.isdigit():
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید:")
        return WAIT_TICKET_COUNT

    pack_id = context.user_data.get("edit_pack_id")
    price = context.user_data.get("temp_pack_price")
    
    db_query("UPDATE lottery_packs SET price = ?, tickets = ? WHERE id = ?", (price, int(tickets), pack_id), commit=True)
    await update.message.reply_text(f"✅ کادر به‌روزرسانی شد:\nقیمت: {price:,} تومان | بلیت: {tickets}")
    return ConversationHandler.END

# ----------------- MAIN APPLICATION STARTUP -----------------
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Handlers
    prize_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_prize_type, pattern="^p_type_")],
        states={
            WAIT_LOTTERY_PRIZE_VAL1: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prize_val1)],
            WAIT_LOTTERY_PRIZE_VAL2: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prize_val2)]
        },
        fallbacks=[]
    )

    pack_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit_pack, pattern="^edit_pack_")],
        states={
            WAIT_TICKET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_price)],
            WAIT_TICKET_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pack_count)]
        },
        fallbacks=[]
    )

    # Commands
    app.add_handler(CommandHandler("start", start))

    # User Buttons
    app.add_handler(MessageHandler(filters.Regex("^💻حصاب کار بری مشحصات$"), user_profile))
    app.add_handler(MessageHandler(filters.Regex("^💎جم اوری سکه رایگان$"), get_free_coins))
    app.add_handler(MessageHandler(filters.Regex("^👥جذب زیر مجموعه$"), ref_link))
    app.add_handler(MessageHandler(filters.Regex("^👨‍💻🛍فروشگاه$"), shop_menu))
    app.add_handler(MessageHandler(filters.Regex("^قرعه کشی$"), lottery_user_menu))
    app.add_handler(MessageHandler(filters.Regex("^بازگشت به منوی اصلی$"), back_to_main))

    # Admin Buttons
    app.add_handler(MessageHandler(filters.Regex("^⚙ پنل مدیریت$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📊 آمار کاربران$"), admin_stats))
    app.add_handler(MessageHandler(filters.Regex("^🎉 تنظیمات جوایز قرعه‌کشی$"), lottery_settings_menu))

    # Callback Query Handlers
    app.add_handler(prize_conv)
    app.add_handler(pack_conv)
    app.add_handler(CallbackQueryHandler(check_sponsor_callback, pattern="^check_sponsor_again$"))
    app.add_handler(CallbackQueryHandler(handle_lottery_admin_callbacks, pattern="^(lottery_|set_prizes_menu|prize_rank_|set_ticket_prices_menu)"))

    logging.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
