telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS post_views (
        post_id TEXT PRIMARY KEY,
        view_count INTEGER DEFAULT 0
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
        lottery_p1 TEXT DEFAULT '0 الماس ممبرگیر',
        lottery_p2 TEXT DEFAULT '0 سکه ویوگیر',
        lottery_p3 TEXT DEFAULT '0 سکه ویوگیر',
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
        kb.append(["⚙ پنل مدیریت"])
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
(WAIT_VIEW_POST, WAIT_VIEW_CONFIRM, WAIT_MEMBER_LINK, WAIT_MEMBER_CONFIRM, 
 WAIT_RECEIPT_PHOTO, WAIT_NEW_CARD) = range(6)

# ----------------- HANDLERS -----------------
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

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    u = get_or_create_user(user.id, user.username or "")
    st = get_settings()

    if text == "💎جم اوری سکه رایگان":
        today_str = str(datetime.date.today())
        if u[5] == today_str:
            await update.message.reply_text("❌ شما امروز سکه و الماس رایگان خود را دریافت کرده‌اید!")
        else:
            db_query("UPDATE users SET coin_view = coin_view + ?, coin_member = coin_member + ?, last_daily = ? WHERE user_id=?", 
                     (st[3], st[4], today_str, user.id), commit=True)
            await update.message.reply_text(f"🎉 {st[3]} **سکه ویو** و {st[4]} **الماس ممبر** رایگان به حساب شما اضافه شد!", parse_mode="Markdown")

    elif text == "💻حصاب کار بری مشحصات":
        username_line = f"👤 **یوزرنیم:** @{u[1]}\n" if u[1] else ""
        msg = f"""💻 **مشخصات حساب کاربری شما:**

👤 **نام:** {user.first_name}
🆔 **آیدی:** `{u[0]}`
{username_line}
🎟 **تعداد بلیت‌های قرعه‌کشی شما:** {u[12]}
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
        bot_un = (await context.bot.get_me()).username
        msg = f"""👥 **جذب زیرمجموعه و دریافت سکه رایگان**

🎉 با دعوت از هر دوست به ربات، **{st[5]} سکه ویوگیر** و **{st[6]} الماس ممبرگیر** دریافت کنید!

🔗 **لینک اختصاصی شما:**
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
        await update.message.reply_text("🎉 **به بخش قرعه‌کشی خوش آمدید!**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ikb, parse_mode="Markdown")

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

    elif text == "👨‍💻🛍︎︎فروشگاه":
        await update.message.reply_text("به فروشگاه خوش آمدید! بخش مورد نظر را انتخاب کنید:", reply_markup=shop_keyboard())

    elif text == "👁خرید سکه ویوگیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("20.000 سکه ⚡️ 50.000 تومان (2 بلیت)", callback_data="buy_coin_20000_50000")],
            [InlineKeyboardButton("40.000 سکه ⚡️ 100.000 تومان (4 بلیت)", callback_data="buy_coin_40000_100000")],
            [InlineKeyboardButton("50.000 سکه ⚡️ 150.000 تومان (4 بلیت)", callback_data="buy_coin_50000_150000")],
            [InlineKeyboardButton("200.000 سکه ⚡️ 200.000 تومان (6 بلیت)", callback_data="buy_coin_200000_200000")]
        ])
        await update.message.reply_text("🛍 **پک‌های سکه ویوگیر:**", reply_markup=ikb)

    elif text == "👁خرید الماس ممبر گیر":
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("100 الماس 💎 25.000 تومان", callback_data="buy_diamond_100_25000")],
            [InlineKeyboardButton("250 الماس 💎 50.000 تومان (2 بلیت)", callback_data="buy_diamond_250_50000")],
            [InlineKeyboardButton("500 الماس 💎 100.000 تومان (4 بلیت)", callback_data="buy_diamond_500_100000")],
            [InlineKeyboardButton("1000 الماس 💎 200.000 تومان (6 بلیت)", callback_data="buy_diamond_1000_200000")],
            [InlineKeyboardButton("4000 الماس 💎 800.000 تومان (10 بلیت)", callback_data="buy_diamond_4000_800000")]
        ])
        await update.message.reply_text("🛍 **پک‌های الماس ممبرگیر:**", reply_markup=ikb)

    elif text == "بازگشت به منوی اصلی":
        await update.message.reply_text("به منوی اصلی بازگشتید.", reply_markup=main_keyboard(user.id))

    # ------------ ADMIN COMMANDS ------------
    elif text == "⚙ پنل مدیریت" and user.id in ADMIN_IDS:
        await update.message.reply_text("⚙️ **به پنل مدیریت خوش آمدید:**", reply_markup=admin_keyboard(), parse_mode="Markdown")

    elif text == "📊 آمار کاربران" and user.id in ADMIN_IDS:
        # کل کاربران و لفت داده‌ها
        tot_u = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0] or 0
        left_u = db_query("SELECT COUNT(*) FROM users WHERE is_left = 1", fetchone=True)[0] or 0
        
        # بیشترین ویو ثبت شده توسط یک کاربر
        max_view = db_query("SELECT MAX(total_views) FROM users", fetchone=True)[0] or 0
        
        # بیشترین سکه موجود/دریافتی
        max_coin = db_query("SELECT MAX(coin_view) FROM users", fetchone=True)[0] or 0
        
        # بیشترین الماس موجود/دریافتی
        max_diamond = db_query("SELECT MAX(coin_member) FROM users", fetchone=True)[0] or 0
        
        # بیشترین کلیک / کلک (پرفعالیت‌ترین کاربر)
        max_activity = db_query("SELECT MAX(cnt) FROM (SELECT COUNT(*) as cnt FROM user_clicks GROUP BY user_id)", fetchone=True)
        max_activity_val = max_activity[0] if max_activity else 0

        # بالاترین جوین شده (بیشترین زیرمجموعه)
        max_ref = db_query("SELECT MAX(ref_count) FROM users", fetchone=True)[0] or 0

        # تعداد کاربران شرکت‌کننده در قرعه‌کشی (دارای حداقل ۱ بلیت)
        lottery_users = db_query("SELECT COUNT(*) FROM users WHERE tickets > 0", fetchone=True)[0] or 0

        # آمار کل خرید فروشگاه
        tot_s = db_query("SELECT SUM(total_spent) FROM users", fetchone=True)[0] or 0
        
        msg = f"""📊 **آمار کامل و دقیق ربات:**

👥 **تعداد کل کاربران:** {tot_u:,} نفر
🚪 **تعداد لفت‌داده‌ها:** {left_u:,} نفر

👁 **بیشترین ویو:** {max_view:,} بازدید
💰 **بیشترین سکه دریافتی:** {max_coin:,} سکه
💎 **بیشترین الماس دریافتی:** {max_diamond:,} الماس

⚡️ **بیشترین فعالیت:** {max_activity_val:,} انجام کار
🔗 **بالاترین جوین‌شده (زیرمجموعه):** {max_ref:,} نفر
🎟 **تعداد شرکت کنندگان قرعه‌کشی:** {lottery_users:,} نفر

💳 **آمار خرید (مبلغ فروشگاه):** {tot_s:,} تومان"""
        await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------- ADMIN SETTINGS FUNCTIONS -----------------
async def start_set_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return ConversationHandler.END

    st = get_settings()
    current_card = st[1]
    await update.message.reply_text(
        f"💳 **تنظیم شماره کارت فروشگاه**\n\n"
        f"شماره کارت فعلی: `{current_card}`\n\n"
        f"لطفاً شماره کارت جدید (۱۶ رقمی با نام صاحب حساب) را ارسال کنید:",
        parse_mode="Markdown"
    )
    return WAIT_NEW_CARD

async def save_new_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_card = update.message.text.strip()
    db_query("UPDATE bot_settings SET card_number = ? WHERE id = 1", (new_card,), commit=True)
    await update.message.reply_text(f"✅ شماره کارت جدید با موفقیت ثبت شد:\n`{new_card}`", parse_mode="Markdown", reply_markup=admin_keyboard())
    return ConversationHandler.END

async def cancel_admin_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=admin_keyboard())
    return ConversationHandler.END

# ----------------- SHOP & LOTTERY CALLBACKS -----------------
async def handle_lottery_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    u = get_or_create_user(user.id, user.username or "")
    st = get_settings()

    if data == "lottery_enter":
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ورود به فروشگاه", callback_data="goto_shop")]])
        msg = f"""به قرعه کشی ربات خوش امدید
برایه ورود در قرعه کشی در ربات بزرگ ممبرگیر وویوگیر
باید از ربات خرید کنید و بلیت شانش دریافت کنید

🎟 **بیلیت شما:** {u[12]} 

۵۰.۰۰۰ هزار تومان خرید ۲ بلیت
۱۰۰.۰۰۰ هزار تومان خرید ۴ بلیت
۲۰۰.۰۰۰ هزار تومان خرید ۶ بلیت
۵۰۰.۰۰۰ هزار تومان خرید ۱۰ بلیت"""
        await query.message.reply_text(msg, reply_markup=ikb)

    elif data == "lottery_winners":
        w1, w2, w3 = st[18], st[19], st[20]
        if not w1 and not w2 and not w3:
            await query.message.reply_text("هنوز برنده‌ای وجود ندارد")
        else:
            msg = f"🏆 **برندگان قرعه‌کشی:**\n\n🥇 نفر اول: {w1}\n🥈 نفر دوم: {w2}\n🥉 نفر سوم: {w3}"
            await query.message.reply_text(msg)

    elif data == "lottery_prizes":
        msg = f"🎁 **جوایز قرعه‌کشی:**\n\nنفر اول = {st[15]}\nنفر دوم = {st[16]}\nنفر سوم = {st[17]}"
        await query.message.reply_text(msg)

    elif data == "goto_shop":
        await query.message.reply_text("به بخش فروشگاه هدایت شدید:", reply_markup=shop_keyboard())

async def select_buy_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    item_type, amount, price = data[1], int(data[2]), int(data[3])

    context.user_data["buy_type"] = item_type
    context.user_data["buy_amount"] = amount
    context.user_data["buy_price"] = price

    unit_name = "سکه ویو" if item_type == "coin" else "الماس ممبر"
    tickets = calculate_tickets(price)
    st = get_settings()

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 پرداخت کارت به کارت", callback_data="pay_card")],
        [InlineKeyboardButton("🔗 پرداخت از طریق درگاه", url=st[2])]
    ])

    ticket_text = f"\n🎟 **هدیه بلیت قرعه‌کشی:** {tickets} عدد بلیت" if tickets > 0 else ""
    await query.message.reply_text(
        f"🛒 **سفارش شما:** {amount:,} {unit_name}\n"
        f"💵 **مبلغ:** {price:,} تومان{ticket_text}\n\n"
        f"روش پرداخت را انتخاب کنید:",
        reply_markup=ikb, parse_mode="Markdown"
    )

async def pay_card_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    st = get_settings()
    amount = context.user_data.get("buy_amount")
    price = context.user_data.get("buy_price")
    item_type = context.user_data.get("buy_type")
    unit_name = "سکه ویو" if item_type == "coin" else "الماس ممبر"

    msg = f"""💳 **اطلاعات واریز کارت به کارت:**

📌 **شماره کارت:**
`{st[1]}`

💵 **مبلغ:** {price:,} تومان
📦 **سفارش:** {amount:,} {unit_name}

⚠️ عکس تراکنش (فیش واریزی) را همین حالا بفرستید."""

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

    await update.message.reply_text("✅ فیش شما دریافت شد و برای مدیریت ارسال گردید.")

    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"approve_{user.id}_{item_type}_{amount}_{tickets}_{price}"),
            InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_{user.id}")
        ]
    ])

    admin_msg = f"""📥 **رسید واریزی جدید**

👤 کاربر: {user.first_name} (@{user.username or 'بدون آیدی'})
🆔 آیدی: `{user.id}`
📦 بسته: {amount:,} {unit_name}
💵 مبلغ: {price:,} تومان
🎟 بلیت تعلق‌گرفته: {tickets} عدد"""

    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=admin_msg, reply_markup=admin_kb, parse_mode="Markdown")
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
        tickets = int(data[4])
        price = int(data[5])

        if item_type == "coin":
            db_query("UPDATE users SET coin_view = coin_view + ?, tickets = tickets + ?, total_spent = total_spent + ? WHERE user_id=?", 
                     (amount, tickets, price, target_user_id), commit=True)
            unit_name = "سکه ویو"
        else:
            db_query("UPDATE users SET coin_member = coin_member + ?, tickets = tickets + ?, total_spent = total_spent + ? WHERE user_id=?", 
                     (amount, tickets, price, target_user_id), commit=True)
            unit_name = "الماس ممبر"

        await query.message.edit_caption(caption=query.message.caption + "\n\n✅ **تایید شد.**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"🎉 پرداخت تایید شد! {amount:,} {unit_name} و {tickets} بلیت اضافه شد.")
        except:
            pass

    elif action == "reject":
        target_user_id = int(data[1])
        await query.message.edit_caption(caption=query.message.caption + "\n\n❌ **رد شد.**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_user_id, text="❌ فیش واریزی شما تایید نشد.")
        except:
            pass

# ----------------- ADS CREATION CONVERSATIONS -----------------
async def start_view_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cost = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    u = get_or_create_user(user_id)
    if u[2] < cost and user_id not in ADMIN_IDS:
        await query.message.reply_text(f"❌ موجودی کافی نیست! نیاز به {cost} سکه دارید.")
        return ConversationHandler.END

    context.user_data["view_cost"] = cost
    await query.message.reply_text("📩 پست مورد نظر را ارسال کنید:")
    return WAIT_VIEW_POST

async def receive_view_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["view_message"] = update.message
    cost = context.user_data.get("view_cost")

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ثبت", callback_data="confirm_view_post")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_ads")]
    ])
    await update.message.reply_text(f"📋 ثبت {cost} بازدید با هزینه {cost} سکه. تایید می‌کنید؟", reply_markup=ikb)
    return WAIT_VIEW_CONFIRM

async def confirm_view_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cost = context.user_data.get("view_cost")
    msg = context.user_data.get("view_message")
    bot_un = (await context.bot.get_me()).username

    db_query("UPDATE users SET coin_view = coin_view - ? WHERE user_id=?", (cost, user_id), commit=True)

    try:
        sent_msg = await context.bot.copy_message(chat_id=VIEW_CHANNEL, from_chat_id=msg.chat_id, message_id=msg.message_id)
        target_id = f"v_{sent_msg.message_id}"
        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👁 ثبت بازدید", callback_data=f"do_view_{target_id}")],
            [InlineKeyboardButton("🤖 بازگشت به ربات", url=f"https://t.me/{bot_un}")]
        ])
        await context.bot.edit_message_reply_markup(chat_id=VIEW_CHANNEL, message_id=sent_msg.message_id, reply_markup=ikb)
        await query.message.edit_text("✅ پست با موفقیت در کانال ثبت شد.")
    except Exception as e:
        await query.message.edit_text(f"✅ ثبت شد اما خطا در کانال:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

async def start_member_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cost = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    u = get_or_create_user(user_id)
    if u[3] < cost and user_id not in ADMIN_IDS:
        await query.message.reply_text(f"❌ موجودی کافی نیست! نیاز به {cost} الماس دارید.")
        return ConversationHandler.END

    context.user_data["member_cost"] = cost
    context.user_data["member_count"] = cost // 2
    await query.message.reply_text("🔗 لینک کانال را ارسال کنید (مثلاً @ChannelName):")
    return WAIT_MEMBER_LINK

async def receive_member_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    context.user_data["member_link"] = link
    cost = context.user_data.get("member_cost")
    count = context.user_data.get("member_count")

    ikb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ثبت", callback_data="confirm_member_link")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_ads")]
    ])
    await update.message.reply_text(f"📋 ثبت سفارش {count} ممبر با هزینه {cost} الماس برای {link}. تایید می‌کنید؟", reply_markup=ikb)
    return WAIT_MEMBER_CONFIRM

async def confirm_member_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cost = context.user_data.get("member_cost")
    count = context.user_data.get("member_count")
    link = context.user_data.get("member_link")
    bot_un = (await context.bot.get_me()).username

    db_query("UPDATE users SET coin_member = coin_member - ? WHERE user_id=?", (cost, user_id), commit=True)
    target_url = link if link.startswith("http") else f"https://t.me/{link.replace('@', '')}"

    try:
        sent_msg = await context.bot.send_message(
            chat_id=MEMBER_CHANNEL,
            text=f"📢 **سفارش جدید ممبرگیر**\n\nعضو کانال شوید و الماس بگیرید:\nتعداد مورد نیاز: {count} ممبر",
            parse_mode="Markdown"
        )
        channel_un = link.replace('@', '') if link.startswith('@') else None
        cb_target = f"m_{sent_msg.message_id}_{channel_un}" if channel_un else f"m_{sent_msg.message_id}"

        ikb = InlineKeyboardMarkup([
            [InlineKeyboardButton("عضویت", url=target_url)],
            [InlineKeyboardButton("💎 دریافت الماس", callback_data=f"get_diamond_{cb_target}")],
            [InlineKeyboardButton("سفارش ممبر", url=f"https://t.me/{bot_un}")]
        ])
        await context.bot.edit_message_reply_markup(chat_id=MEMBER_CHANNEL, message_id=sent_msg.message_id, reply_markup=ikb)
        await query.message.edit_text("✅ سفارش ممبر با موفقیت ثبت شد.")
    except Exception as e:
        await query.message.edit_text(f"✅ ثبت شد اما خطا در کانال:\n`{e}`", parse_mode="Markdown")

    return ConversationHandler.END

async def cancel_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# ----------------- BUTTON CLICK REWARDS -----------------
async def handle_channel_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data.startswith("do_view_"):
        target_id = data.replace("do_view_", "")
        if db_query("SELECT * FROM user_clicks WHERE user_id=? AND target_id=?", (user_id, target_id), fetchone=True):
            await query.answer("❌ قبلاً این بازدید را ثبت کرده‌اید!", show_alert=True)
            return

        db_query("INSERT INTO user_clicks (user_id, target_id) VALUES (?, ?)", (user_id, target_id), commit=True)
        db_query("UPDATE users SET coin_view = coin_view + 1, total_views = total_views + 1, today_views = today_views + 1 WHERE user_id=?", (user_id,), commit=True)
        await query.answer("🎉 ۱ سکه ویو به حساب شما اضافه شد!", show_alert=True)

    elif data.startswith("get_diamond_"):
        info = data.replace("get_diamond_", "").split("_")
        target_id = info[1]
        channel_un = info[2] if len(info) > 0 and len(info) > 2 else None

        if db_query("SELECT * FROM user_clicks WHERE user_id=? AND target_id=?", (user_id, f"m_{target_id}"), fetchone=True):
            await query.answer("❌ قبلاً پاداش این کانال را دریافت کرده‌اید!", show_alert=True)
            return

        if channel_un:
            try:
                m = await context.bot.get_chat_member(chat_id=f"@{channel_un}", user_id=user_id)
                if m.status in ["left", "kicked"]:
                    await query.answer("❌ هنوز در کانال عضو نشده‌اید! ابتدا عضو شوید.", show_alert=True)
                    return
            except:
                pass

        db_query("INSERT INTO user_clicks (user_id, target_id) VALUES (?, ?)", (user_id, f"m_{target_id}"), commit=True)
        db_query("UPDATE users SET coin_member = coin_member + 1 WHERE user_id=?", (user_id,), commit=True)
        await query.answer("🎉 ۱ الماس به حساب شما اضافه شد!", show_alert=True)

# ----------------- MAIN SERVER SETUP -----------------
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

    # گفتگو برای تنظیم شماره کارت
    card_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💳 تنظیم شماره کارت$"), start_set_card)],
        states={
            WAIT_NEW_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_card)]
        },
        fallbacks=[MessageHandler(filters.Regex("^بازگشت به منوی اصلی$"), cancel_admin_state)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(view_conv)
    app.add_handler(member_conv)
    app.add_handler(receipt_conv)
    app.add_handler(card_conv)

    app.add_handler(CallbackQueryHandler(handle_lottery_callbacks, pattern="^(lottery_|goto_shop)"))
    app.add_handler(CallbackQueryHandler(select_buy_package, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(admin_payment_decision, pattern="^(approve_|reject_)"))
    app.add_handler(CallbackQueryHandler(handle_channel_callbacks, pattern="^(do_view_|get_diamond_)"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    logging.info("Starting Bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
