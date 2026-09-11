import os
import sqlite3
from datetime import datetime

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = int(os.getenv("ADMIN_ID", "5412332176"))

TARGET_CHANNEL = os.getenv(
    "TARGET_CHANNEL",
    "@view_sin_channel"
)

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

DB_NAME = "viewcoin.db"


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    conn.executescript("""
    
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        coins INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message_id INTEGER,
        target_views INTEGER NOT NULL,
        current_views INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS views (
        order_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(order_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS mandatory_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        link TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS order_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        views INTEGER NOT NULL UNIQUE,
        coins INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS coin_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        coins INTEGER NOT NULL,
        price TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );

    """)

    # تنظیمات اولیه
    conn.execute(
        "INSERT OR IGNORE INTO settings(key,value) VALUES('reward_per_view','5')"
    )

    conn.execute(
        "INSERT OR IGNORE INTO settings(key,value) VALUES('coin_purchase_enabled','0')"
    )

    # سفارش‌های اولیه
    default_orders = [
        (20, 20),
        (40, 40),
        (60, 60),
        (100, 100),
        (200, 200),
    ]

    for views, coins in default_orders:
        conn.execute(
            "INSERT OR IGNORE INTO order_options(views,coins) VALUES(?,?)",
            (views, coins)
        )

    conn.commit()
    conn.close()


def get_setting(key, default=None):

    conn = get_db()

    row = conn.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()

    conn.close()

    if row:
        return row["value"]

    return default


def set_setting(key, value):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings(key,value)
        VALUES(?,?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
        """,
        (key, str(value))
    )

    conn.commit()
    conn.close()


def reward_per_view():

    return int(
        get_setting("reward_per_view", "5")
    )


# =========================
# USERS
# =========================

def register_user(message: Message):

    user = message.from_user

    conn = get_db()

    conn.execute(
        """
        INSERT INTO users(
            telegram_id,
            username,
            created_at
        )
        VALUES(?,?,?)
        
        ON CONFLICT(telegram_id)
        DO UPDATE SET username=excluded.username
        """,
        (
            user.id,
            user.username or "",
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()
    conn.close()


# =========================
# MENUS
# =========================

def main_menu():

    buttons = [

        [
            InlineKeyboardButton(
                text="🪙 موجودی سکه",
                callback_data="balance"
            )
        ],

        [
            InlineKeyboardButton(
                text="👁️ کسب سکه / ثبت سین",
                callback_data="earn"
            )
        ],

        [
            InlineKeyboardButton(
                text="📢 سفارش بازدید",
                callback_data="order"
            )
        ],

        [
            InlineKeyboardButton(
                text="📋 سفارش‌های من",
                callback_data="myorders"
            )
        ],

        [
            InlineKeyboardButton(
                text="ℹ️ راهنما و قوانین",
                callback_data="help"
            )
        ]

    ]

    # خرید سکه فقط وقتی روشن باشد
    if get_setting(
        "coin_purchase_enabled",
        "0"
    ) == "1":

        buttons.append([
            InlineKeyboardButton(
                text="💳 خرید سکه",
                callback_data="buycoins"
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def admin_menu():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🔗 عضویت اجباری",
                    callback_data="adm_channels"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🪙 مدیریت سکه",
                    callback_data="adm_coins"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📢 مدیریت سفارش‌ها",
                    callback_data="adm_orders"
                )
            ],

            [
                InlineKeyboardButton(
                    text="👥 کاربران",
                    callback_data="adm_users"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📊 آمار ربات",
                    callback_data="adm_stats"
                )
            ],

            [
                InlineKeyboardButton(
                    text="⚙️ تنظیمات",
                    callback_data="adm_settings"
                )
            ],

        ]
    )


def is_admin(user_id):

    return user_id == ADMIN_ID


# =========================
# WELCOME / RULES
# =========================

def welcome_text():

    return """
👋 <b>به ViewCoin خوش آمدی</b>

📢 کانال اصلی:
@view_sin_channel

🪙 در این ربات می‌توانی با ثبت تعامل روی سفارش‌های دیگر کاربران سکه دریافت کنی.

👁️ هر ثبت سین موفق، مقدار مشخصی سکه به حساب شما اضافه می‌کند.

📢 سپس می‌توانی با استفاده از سکه‌ها برای پست خودت سفارش بازدید ثبت کنی.

━━━━━━━━━━━━━━

📜 <b>قوانین استفاده</b>

• هر کاربر برای هر سفارش فقط یک‌بار می‌تواند سکه دریافت کند.
• استفاده از ربات برای اسپم و سوءاستفاده ممنوع است.
• ایجاد حساب‌های متعدد برای جمع‌آوری سکه ممنوع است.
• سکه‌ها قابل انتقال به کاربران دیگر نیستند.
• مدیریت می‌تواند سفارش‌های خلاف قوانین را حذف کند.
• ثبت سین در این ربات به معنی ثبت تعامل در سیستم ربات است و تضمینی برای افزایش عدد View واقعی تلگرام نیست.

━━━━━━━━━━━━━━

✅ با استفاده از ربات، قوانین را می‌پذیری.
"""


# =========================
# MANDATORY MEMBERSHIP
# =========================

async def get_mandatory_channels():

    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM mandatory_channels"
    ).fetchall()

    conn.close()

    return rows


async def check_membership(user_id):

    channels = await get_mandatory_channels()

    missing = []

    for channel in channels:

        try:

            member = await bot.get_chat_member(
                channel["username"],
                user_id
            )

            if member.status in (
                "left",
                "kicked"
            ):
                missing.append(channel)

        except Exception:

            missing.append(channel)

    return missing


async def membership_keyboard():

    channels = await get_mandatory_channels()

    buttons = []

    for index, channel in enumerate(channels, start=1):

        buttons.append([
            InlineKeyboardButton(
                text=f"📢 عضویت در کانال {index}",
                url=channel["link"]
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="✅ بررسی عضویت",
            callback_data="check_membership"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


async def require_membership(message_or_call):

    user_id = message_or_call.from_user.id

    # ادمین از عضویت اجباری مستثنی است
    if is_admin(user_id):
        return True

    missing = await check_membership(user_id)

    if not missing:
        return True

    text = (
        "🔒 برای استفاده از ربات ابتدا "
        "در کانال‌های الزامی عضو شو."
    )

    keyboard = await membership_keyboard()

    if isinstance(message_or_call, Message):

        await message_or_call.answer(
            text,
            reply_markup=keyboard
        )

    else:

        await message_or_call.answer(
            "❌ ابتدا در کانال‌های الزامی عضو شو.",
            show_alert=True
        )

        await message_or_call.message.answer(
            text,
            reply_markup=keyboard
        )

    return False


# =========================
# STATES
# =========================

class OrderStates(StatesGroup):

    waiting_post = State()


class AdminStates(StatesGroup):

    waiting_channel = State()
    waiting_reward = State()
    waiting_order_option = State()
    waiting_package = State()


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    register_user(message)

    if not await require_membership(message):
        return

    await message.answer(
        welcome_text(),
        reply_markup=main_menu()
    )


# =========================
# ADMIN COMMAND
# =========================

@dp.message(Command("admin"))
async def admin_command(message: Message):

    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👑 <b>پنل مدیریت ViewCoin</b>",
        reply_markup=admin_menu()
    )


# =========================
# MEMBERSHIP CHECK
# =========================

@dp.callback_query(F.data == "check_membership")
async def check_membership_callback(call: CallbackQuery):

    missing = await check_membership(
        call.from_user.id
    )

    if missing:

        await call.answer(
            "❌ هنوز در همه کانال‌ها عضو نشده‌ای.",
            show_alert=True
        )

        return

    await call.answer(
        "✅ عضویت تأیید شد."
    )

    await call.message.answer(
        "🎉 عضویت تأیید شد!\n\n"
        "حالا می‌توانی از ربات استفاده کنی.",
        reply_markup=main_menu()
    )


# =========================
# BALANCE
# =========================

@dp.callback_query(F.data == "balance")
async def balance(call: CallbackQuery):

    if not await require_membership(call):
        return

    conn = get_db()

    row = conn.execute(
        "SELECT coins FROM users WHERE telegram_id=?",
        (call.from_user.id,)
    ).fetchone()

    conn.close()

    coins = row["coins"] if row else 0

    await call.answer()

    await call.message.answer(
        f"🪙 موجودی شما:\n\n"
        f"<b>{coins} سکه</b>"
    )


# =========================
# HELP
# =========================

@dp.callback_query(F.data == "help")
async def help_callback(call: CallbackQuery):

    await call.answer()

    await call.message.answer(
        welcome_text(),
        reply_markup=main_menu()
    )


# =========================
# EARN COINS
# =========================

@dp.callback_query(F.data == "earn")
async def earn_coins(call: CallbackQuery):

    if not await require_membership(call):
        return

    conn = get_db()

    orders = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE status='active'
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    conn.close()

    if not orders:

        await call.answer(
            "فعلاً سفارشی برای ثبت سین وجود ندارد.",
            show_alert=True
        )

        return

    buttons = []

    reward = reward_per_view()

    for order in orders:

        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"👁️ سفارش #{order['id']} "
                    f"— {order['current_views']}/"
                    f"{order['target_views']}"
                ),
                callback_data=f"view:{order['id']}"
            )
        ])

    await call.answer()

    await call.message.answer(
        f"👁️ ثبت سین\n\n"
        f"با ثبت موفق هر سفارش، "
        f"<b>{reward} سکه</b> دریافت می‌کنی.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


# =========================
# REGISTER VIEW
# =========================

@dp.callback_query(F.data.startswith("view:"))
async def register_view(call: CallbackQuery):

    if not await require_membership(call):
        return

    order_id = int(
        call.data.split(":")[1]
    )

    user_id = call.from_user.id

    conn = get_db()

    order = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE id=?
        AND status='active'
        """,
        (order_id,)
    ).fetchone()

    if not order:

        conn.close()

        await call.answer(
            "❌ این سفارش تمام شده است.",
            show_alert=True
        )

        return

    # جلوگیری از ثبت دوباره
    existing = conn.execute(
        """
        SELECT 1
        FROM views
        WHERE order_id=?
        AND user_id=?
        """,
        (
            order_id,
            user_id
        )
    ).fetchone()

    if existing:

        conn.close()

        await call.answer(
            "⚠️ قبلاً برای این سفارش ثبت سین کرده‌ای.",
            show_alert=True
        )

        return

    # ثبت سین
    conn.execute(
        """
        INSERT INTO views(
            order_id,
            user_id,
            created_at
        )
        VALUES(?,?,?)
        """,
        (
            order_id,
            user_id,
            datetime.utcnow().isoformat()
        )
    )

    new_count = (
        order["current_views"] + 1
    )

    reward = reward_per_view()

    conn.execute(
        """
        UPDATE orders
        SET current_views=?
        WHERE id=?
        """,
        (
            new_count,
            order_id
        )
    )

    conn.execute(
        """
        UPDATE users
        SET coins=coins+?
        WHERE telegram_id=?
        """,
        (
            reward,
            user_id
        )
    )

    completed = (
        new_count >= order["target_views"]
    )

    if completed:

        conn.execute(
            """
            UPDATE orders
            SET status='completed'
            WHERE id=?
            """,
            (order_id,)
        )

    conn.commit()
    conn.close()

    await call.answer(
        f"✅ ثبت شد!\n"
        f"+{reward} سکه",
        show_alert=True
    )

    # اگر سفارش کامل شده، پست حذف شود
    if completed:

        try:

            await bot.delete_message(
                TARGET_CHANNEL,
                order["message_id"]
            )

        except Exception:
            pass

        return

    # به‌روزرسانی دکمه
    try:

        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=(
                                f"👁️ ثبت سین +{reward} سکه | "
                                f"{new_count}/"
                                f"{order['target_views']}"
                            ),
                            callback_data=f"view:{order_id}"
                        )
                    ]
                ]
            )
        )

    except Exception:
        pass


# =========================
# ORDER
# =========================

@dp.callback_query(F.data == "order")
async def order_menu(
    call: CallbackQuery,
    state: FSMContext
):

    if not await require_membership(call):
        return

    conn = get_db()

    options = conn.execute(
        """
        SELECT *
        FROM order_options
        ORDER BY views
        """
    ).fetchall()

    conn.close()

    buttons = []

    for option in options:

        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"👁️ {option['views']} بازدید "
                    f"— {option['coins']} سکه"
                ),
                callback_data=(
                    f"target:{option['id']}"
                )
            )
        ])

    await call.answer()

    await call.message.answer(
        "📢 <b>سفارش بازدید</b>\n\n"
        "تعداد موردنظر را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


@dp.callback_query(F.data.startswith("target:"))
async def choose_order(
    call: CallbackQuery,
    state: FSMContext
):

    option_id = int(
        call.data.split(":")[1]
    )

    conn = get_db()

    option = conn.execute(
        """
        SELECT *
        FROM order_options
        WHERE id=?
        """,
        (option_id,)
    ).fetchone()

    user = conn.execute(
        """
        SELECT coins
        FROM users
        WHERE telegram_id=?
        """,
        (call.from_user.id,)
    ).fetchone()

    conn.close()

    if not option:

        await call.answer(
            "❌ گزینه پیدا نشد.",
            show_alert=True
        )

        return

    if not user or user["coins"] < option["coins"]:

        await call.answer(
            "❌ سکه کافی نداری.",
            show_alert=True
        )

        return

    await state.update_data(
        option_id=option_id
    )

    await state.set_state(
        OrderStates.waiting_post
    )

    await call.answer()

    await call.message.answer(
        f"✅ انتخاب شد:\n"
        f"👁️ {option['views']} بازدید\n"
        f"🪙 {option['coins']} سکه\n\n"
        f"حالا پستت را همینجا برای ربات ارسال کن.\n"
        f"می‌توانی عکس، ویدیو، متن یا فایل بفرستی."
    )


# =========================
# RECEIVE USER POST
# =========================

@dp.message(OrderStates.waiting_post)
async def receive_post(
    message: Message,
    state: FSMContext
):

    data = await state.get_data()

    option_id = data.get(
        "option_id"
    )

    conn = get_db()

    option = conn.execute(
        """
        SELECT *
        FROM order_options
        WHERE id=?
        """,
        (option_id,)
    ).fetchone()

    user = conn.execute(
        """
        SELECT coins
        FROM users
        WHERE telegram_id=?
        """,
        (message.from_user.id,)
    ).fetchone()

    conn.close()

    if not option:

        await state.clear()

        await message.answer(
            "❌ گزینه سفارش پیدا نشد."
        )

        return

    if not user or user["coins"] < option["coins"]:

        await state.clear()

        await message.answer(
            "❌ سکه کافی نیست."
        )

        return

    target_views = option["views"]
    cost = option["coins"]

    # کپی پست به کانال
    sent = await bot.copy_message(
        chat_id=TARGET_CHANNEL,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

    # ساخت سفارش
    conn = get_db()

    cursor = conn.execute(
        """
        INSERT INTO orders(
            user_id,
            message_id,
            target_views,
            current_views,
            status,
            created_at
        )
        VALUES(?,?,?,?,?,?)
        """,
        (
            message.from_user.id,
            sent.message_id,
            target_views,
            0,
            "active",
            datetime.utcnow().isoformat()
        )
    )

    order_id = cursor.lastrowid

    # کسر سکه
    conn.execute(
        """
        UPDATE users
        SET coins=coins-?
        WHERE telegram_id=?
        """,
        (
            cost,
            message.from_user.id
        )
    )

    conn.commit()
    conn.close()

    reward = reward_per_view()

    # اضافه کردن دکمه ثبت سین
    try:

        await bot.edit_message_reply_markup(
            chat_id=TARGET_CHANNEL,
            message_id=sent.message_id,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=(
                                f"👁️ ثبت سین +{reward} سکه | "
                                f"0/{target_views}"
                            ),
                            callback_data=f"view:{order_id}"
                        )
                    ]
                ]
            )
        )

    except Exception:

        # اگر اضافه کردن دکمه موفق نشد،
        # سفارش را لغو می‌کنیم و سکه را برمی‌گردانیم.
        conn = get_db()

        conn.execute(
            """
            DELETE FROM orders
            WHERE id=?
            """,
            (order_id,)
        )

        conn.execute(
            """
            UPDATE users
            SET coins=coins+?
            WHERE telegram_id=?
            """,
            (
                cost,
                message.from_user.id
            )
        )

        conn.commit()
        conn.close()

        try:
            await bot.delete_message(
                TARGET_CHANNEL,
                sent.message_id
            )
        except Exception:
            pass

        await state.clear()

        await message.answer(
            "❌ انتشار سفارش انجام نشد.\n"
            "مطمئن شو ربات در کانال ادمین است."
        )

        return

    await state.clear()

    await message.answer(
        f"🎉 سفارش با موفقیت ثبت شد!\n\n"
        f"📋 شماره سفارش: #{order_id}\n"
        f"👁️ تعداد: {target_views}\n"
        f"🪙 هزینه: {cost} سکه\n\n"
        f"پست در کانال منتشر شد."
    )


# =========================
# MY ORDERS
# =========================

@dp.callback_query(F.data == "myorders")
async def my_orders(call: CallbackQuery):

    if not await require_membership(call):
        return

    conn = get_db()

    rows = conn.execute(
        """
