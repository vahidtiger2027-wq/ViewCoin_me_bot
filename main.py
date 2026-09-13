import os
import sqlite3
from datetime import datetime
from contextlib import asynccontextmanager

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
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@view_sin_channel")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
DB_NAME = "viewcoin.db"


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
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
        username TEXT NOT NULL UNIQUE,
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

    conn.execute(
        "INSERT OR IGNORE INTO settings(key,value) VALUES('reward_per_view','5')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO settings(key,value) VALUES('coin_purchase_enabled','0')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO settings(key,value) VALUES('card_number','')"
    )

    for views, coins in [(20, 20), (40, 40), (60, 60), (100, 100), (200, 200)]:
        conn.execute(
            "INSERT OR IGNORE INTO order_options(views,coins) VALUES(?,?)",
            (views, coins),
        )

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute("""
        INSERT INTO settings(key,value)
        VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def reward_per_view():
    return int(get_setting("reward_per_view", "5"))


# =========================
# USERS
# =========================

def register_user(user):
    conn = get_db()
    conn.execute("""
        INSERT INTO users(telegram_id, username, created_at)
        VALUES(?,?,?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET username=excluded.username
    """, (user.id, user.username or "", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_user_coins(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT coins FROM users WHERE telegram_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row["coins"] if row else 0


# =========================
# MENUS
# =========================

def main_menu():
    buttons = [
        [InlineKeyboardButton(text="🪙 موجودی سکه", callback_data="balance")],
        [InlineKeyboardButton(text="👁️ کسب سکه / ثبت سین", callback_data="earn")],
        [InlineKeyboardButton(text="📢 سفارش بازدید", callback_data="order")],
        [InlineKeyboardButton(text="📋 سفارش‌های من", callback_data="myorders")],
        [InlineKeyboardButton(text="💳 خرید سکه", callback_data="buycoins")],
        [InlineKeyboardButton(text="ℹ️ راهنما و قوانین", callback_data="help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 عضویت اجباری", callback_data="adm_channels")],
        [InlineKeyboardButton(text="🪙 مدیریت سکه", callback_data="adm_coins")],
        [InlineKeyboardButton(text="📢 مدیریت سفارش‌ها", callback_data="adm_orders")],
        [InlineKeyboardButton(text="👥 کاربران", callback_data="adm_users")],
        [InlineKeyboardButton(text="📊 آمار ربات", callback_data="adm_stats")],
        [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm_settings")],
    ])


def is_admin(user_id):
    return user_id == ADMIN_ID


# =========================
# TEXT
# =========================

def welcome_text():
    return """<b>👋 به ViewCoin خوش آمدی</b>

📢 کانال اصلی:
@view_sin_channel

🪙 با ثبت تعامل روی سفارش‌های دیگر کاربران سکه دریافت کن و با سکه برای پست خودت سفارش بازدید بگیر.

👁️ هر ثبت سین موفق، ۵ سکه به حسابت اضافه می‌کند.

📜 <b>قوانین</b>
• هر کاربر برای هر سفارش فقط یک‌بار پاداش می‌گیرد.
• ساخت حساب‌های متعدد برای جمع‌آوری سکه ممنوع است.
• سکه‌ها قابل انتقال نیستند.
• سفارش‌های خلاف قوانین ممکن است حذف شوند.
• ثبت سین در این ربات به معنی ثبت تعامل در سیستم ربات است و تضمینی برای افزایش عدد View واقعی تلگرام نیست.
"""


# =========================
# MANDATORY MEMBERSHIP
# =========================

def get_mandatory_channels():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM mandatory_channels ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


async def check_membership(user_id):
    missing = []
    for channel in get_mandatory_channels():
        try:
            member = await bot.get_chat_member(channel["username"], user_id)
            if member.status in ("left", "kicked"):
                missing.append(channel)
            elif member.status == "restricted" and not getattr(member, "is_member", False):
                missing.append(channel)
        except Exception:
            missing.append(channel)
    return missing


def membership_keyboard():
    buttons = []
    channels = get_mandatory_channels()

    for i, channel in enumerate(channels, 1):
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 عضویت در کانال {i}",
                url=channel["link"]
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="✅ بررسی عضویت",
            callback_data="check_membership"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def require_membership(event):
    user_id = event.from_user.id

    if is_admin(user_id):
        return True

    missing = await check_membership(user_id)
    if not missing:
        return True

    text = "🔒 برای استفاده از ربات ابتدا در کانال‌های الزامی عضو شو."
    keyboard = membership_keyboard()

    if isinstance(event, Message):
        await event.answer(text, reply_markup=keyboard)
    else:
        await event.answer(
            "❌ ابتدا در کانال‌های الزامی عضو شو.",
            show_alert=True
        )
        if event.message:
            await event.message.answer(text, reply_markup=keyboard)

    return False


# =========================
# STATES
# =========================

class OrderStates(StatesGroup):
    waiting_post = State()


class AdminStates(StatesGroup):
    waiting_channel = State()
    waiting_reward = State()
    waiting_card = State()
    waiting_coin_package = State()


# =========================
# START / ADMIN
# =========================

@dp.message(CommandStart())
async def start(message: Message):
    register_user(message.from_user)

    if not await require_membership(message):
        return

    await message.answer(welcome_text(), reply_markup=main_menu())


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👑 <b>پنل مدیریت ViewCoin</b>",
        reply_markup=admin_menu()
    )


@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ عملیات لغو شد.", reply_markup=main_menu())


# =========================
# MEMBERSHIP
# =========================

@dp.callback_query(F.data == "check_membership")
async def check_membership_callback(call: CallbackQuery):
    missing = await check_membership(call.from_user.id)

    if missing:
        await call.answer(
            "❌ هنوز در همه کانال‌ها عضو نشده‌ای.",
            show_alert=True
        )
        return

    await call.answer("✅ عضویت تأیید شد.")
    await call.message.answer(
        "🎉 عضویت تأیید شد!",
        reply_markup=main_menu()
    )


# =========================
# USER MENU
# =========================

@dp.callback_query(F.data == "balance")
async def balance(call: CallbackQuery):
    if not await require_membership(call):
        return

    register_user(call.from_user)
    coins = get_user_coins(call.from_user.id)

    await call.answer()
    await call.message.answer(f"🪙 موجودی شما:\n\n<b>{coins} سکه</b>")


@dp.callback_query(F.data == "help")
async def help_callback(call: CallbackQuery):
    if not await require_membership(call):
        return

    await call.answer()
    await call.message.answer(welcome_text(), reply_markup=main_menu())


@dp.callback_query(F.data == "earn")
async def earn_coins(call: CallbackQuery):
    if not await require_membership(call):
        return

    conn = get_db()
    orders = conn.execute("""
        SELECT *
        FROM orders
        WHERE status='active'
        AND current_views < target_views
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    if not orders:
        await call.answer(
            "فعلاً سفارشی برای ثبت سین وجود ندارد.",
            show_alert=True
        )
        return

    reward = reward_per_view()
    buttons = []

    for order in orders:
        buttons.append([
            InlineKeyboardButton(
                text=f"👁️ سفارش #{order['id']} — {order['current_views']}/{order['target_views']}",
                callback_data=f"view:{order['id']}"
            )
        ])

    await call.answer()
    await call.message.answer(
        f"👁️ <b>کسب سکه</b>\n\n"
        f"با ثبت موفق هر سفارش <b>{reward} سکه</b> می‌گیری.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


# =========================
# REGISTER VIEW
# =========================

@dp.callback_query(F.data.startswith("view:"))
async def register_view(call: CallbackQuery):
    if not await require_membership(call):
        return

    register_user(call.from_user)
    order_id = int(call.data.split(":")[1])
    user_id = call.from_user.id

    # اطمینان از عضویت در کانال اصلی
    try:
        member = await bot.get_chat_member(TARGET_CHANNEL, user_id)
        if member.status in ("left", "kicked"):
            await call.answer(
                "❌ ابتدا در کانال اصلی عضو شو.",
                show_alert=True
            )
            return
    except Exception:
        await call.answer(
            "⚠️ عضویت کانال قابل بررسی نیست. بعداً دوباره امتحان کن.",
            show_alert=True
        )
        return

    reward = reward_per_view()
    conn = get_db()

    try:
        conn.execute("BEGIN IMMEDIATE")

        order = conn.execute("""
            SELECT *
            FROM orders
            WHERE id=? AND status='active'
        """, (order_id,)).fetchone()

        if not order or order["current_views"] >= order["target_views"]:
            conn.rollback()
            await call.answer(
                "❌ این سفارش تمام شده است.",
                show_alert=True
            )
            return

        inserted = conn.execute("""
            INSERT OR IGNORE INTO views(order_id,user_id,created_at)
            VALUES(?,?,?)
        """, (order_id, user_id, datetime.utcnow().isoformat()))

        if inserted.rowcount == 0:
            conn.rollback()
            await call.answer(
                "⚠️ قبلاً برای این سفارش سکه گرفته‌ای.",
                show_alert=True
            )
            return

        updated = conn.execute("""
            UPDATE orders
            SET current_views=current_views+1
            WHERE id=? AND status='active'
            AND current_views < target_views
        """, (order_id,))

        if updated.rowcount == 0:
            conn.rollback()
            await call.answer(
                "❌ ظرفیت سفارش تکمیل شده است.",
                show_alert=True
            )
            return

        conn.execute("""
            UPDATE users
            SET coins=coins+?
            WHERE telegram_id=?
        """, (reward, user_id))

        new_count = order["current_views"] + 1
        completed = new_count >= order["target_views"]

        if completed:
            conn.execute(
                "UPDATE orders SET status='completed' WHERE id=?",
                (order_id,)
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    await call.answer(f"✅ ثبت شد! +{reward} سکه", show_alert=True)

    if completed:
        try:
            await bot.delete_message(TARGET_CHANNEL, order["message_id"])
        except Exception:
            pass
        return

    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"👁️ ثبت سین +{reward} سکه | {new_count}/{order['target_views']}",
                    callback_data=f"view:{order_id}"
                )
            ]])
        )
    except Exception:
        pass


# =========================
# ORDER
# =========================

@dp.callback_query(F.data == "order")
async def order_menu(call: CallbackQuery):
    if not await require_membership(call):
        return

    conn = get_db()
    options = conn.execute(
        "SELECT * FROM order_options ORDER BY views"
    ).fetchall()
    conn.close()

    buttons = []
    for option in options:
        buttons.append([
            InlineKeyboardButton(
                text=f"👁️ {option['views']} بازدید — {option['coins']} سکه",
                callback_data=f"target:{option['id']}"
            )
        ])

    await call.answer()
    await call.message.answer(
        "📢 <b>سفارش بازدید</b>\n\nتعداد موردنظر را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("target:"))
async def choose_order(call: CallbackQuery, state: FSMContext):
    if not await require_membership(call):
        return

    option_id = int(call.data.split(":")[1])

    conn = get_db()
    option = conn.execute(
        "SELECT * FROM order_options WHERE id=?", (option_id,)
    ).fetchone()
    user = conn.execute(
        "SELECT coins FROM users WHERE telegram_id=?",
        (call.from_user.id,)
    ).fetchone()
    conn.close()

    if not option:
        await call.answer("❌ گزینه پیدا نشد.", show_alert=True)
        return

    if not user or user["coins"] < option["coins"]:
        await call.answer("❌ سکه کافی نداری.", show_alert=True)
        return

    await state.update_data(option_id=option_id)
    await state.set_state(OrderStates.waiting_post)

    await call.answer()
    await call.message.answer(
        f"✅ انتخاب شد:\n"
        f"👁️ {option['views']} بازدید\n"
        f"🪙 {option['coins']} سکه\n\n"
        f"حالا پستت را همینجا بفرست.\n"
        f"عکس، ویدیو یا متن قابل قبول است.\n\n"
        f"برای لغو: /cancel"
    )


@dp.message(OrderStates.waiting_post)
async def receive_post(message: Message, state: FSMContext):
    if not await require_membership(message):
        return

    data = await state.get_data()
    option_id = data.get("option_id")

    conn = get_db()
    option = conn.execute(
        "SELECT * FROM order_options WHERE id=?", (option_id,)
    ).fetchone()
    user = conn.execute(
        "SELECT coins FROM users WHERE telegram_id=?",
        (message.from_user.id,)
    ).fetchone()
    conn.close()

    if not option:
        await state.clear()
        await message.answer("❌ گزینه سفارش پیدا نشد.")
        return

    if not user or user["coins"] < option["coins"]:
        await state.clear()
        await message.answer("❌ سکه کافی نیست.")
        return

    target_views = option["views"]
    cost = option["coins"]

    try:
        sent = await bot.copy_message(
            chat_id=TARGET_CHANNEL,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except Exception:
        await state.clear()
        await message.answer(
            "❌ انتشار در کانال انجام نشد.\n"
            "مطمئن شو ربات در کانال اصلی ادمین است."
        )
        return

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")

        changed = conn.execute("""
            UPDATE users
            SET coins=coins-?
            WHERE telegram_id=? AND coins>=?
        """, (cost, message.from_user.id, cost))

        if changed.rowcount == 0:
            conn.rollback()
            raise RuntimeError("not enough coins")

        cursor = conn.execute("""
            INSERT INTO orders(
                user_id,message_id,target_views,current_views,status,created_at
            )
            VALUES(?,?,?,?,?,?)
        """, (
            message.from_user.id,
            sent.message_id,
            target_views,
            0,
            "active",
            datetime.utcnow().isoformat()
        ))

        order_id = cursor.lastrowid
        conn.commit()

    except Exception:
        conn.rollback()
        try:
            await bot.delete_message(TARGET_CHANNEL, sent.message_id)
        except Exception:
            pass
        await state.clear()
        conn.close()
        await message.answer("❌ ثبت سفارش انجام نشد و سکه کسر نشد.")
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass

    reward = reward_per_view()

    try:
        await bot.edit_message_reply_markup(
            chat_id=TARGET_CHANNEL,
            message_id=sent.message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"👁️ ثبت سین +{reward} سکه | 0/{target_views}",
                    callback_data=f"view:{order_id}"
                )
            ]])
        )
    except Exception:
        conn = get_db()
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
        conn.execute(
            "UPDATE users SET coins=coins+? WHERE telegram_id=?",
            (cost, message.from_user.id)
        )
        conn.commit()
        conn.close()

        try:
            await bot.delete_message(TARGET_CHANNEL, sent.message_id)
        except Exception:
            pass

        await state.clear()
        await message.answer(
            "❌ دکمه سفارش روی پست قرار نگرفت.\n"
            "مطمئن شو ربات در کانال دسترسی ادمین دارد."
        )
        return

    await state.clear()

    await message.answer(
        f"🎉 <b>سفارش ثبت شد!</b>\n\n"
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
    rows = conn.execute("""
        SELECT *
        FROM orders
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 20
    """, (call.from_user.id,)).fetchall()
    conn.close()

    if not rows:
        await call.answer(
            "هنوز سفارشی ثبت نکرده‌ای.",
            show_alert=True
        )
        return

    status_names = {
        "active": "🟢 فعال",
        "completed": "✅ تکمیل‌شده",
        "cancelled": "❌ لغوشده",
    }

    text = "📋 <b>سفارش‌های من</b>\n\n"

    for row in rows:
        status = status_names.get(row["status"], row["status"])
        text += (
            f"#{row['id']} — "
            f"{row['current_views']}/{row['target_views']} "
            f"— {status}\n"
        )

    await call.answer()
    await call.message.answer(text)


# =========================
# BUY COINS - CARD
# =========================

@dp.callback_query(F.data == "buycoins")
async def buy_coins(call: CallbackQuery):
    if not await require_membership(call):
        return

    card = get_setting("card_number", "")

    if not card:
        await call.answer(
            "فعلاً خرید سکه فعال نشده است.",
            show_alert=True
        )
        return

    conn = get_db()
    packages = conn.execute("""
        SELECT * FROM coin_packages
        WHERE active=1
        ORDER BY coins
    """).fetchall()
    conn.close()

    text = "💳 <b>خرید سکه</b>\n\n"
    if packages:
        for p in packages:
            text += f"🪙 {p['coins']} سکه — {p['price']}\n"
    else:
        text += "بسته‌های خرید هنوز تنظیم نشده‌اند.\n"

    text += (
        f"\n💳 شماره کارت:\n"
        f"<code>{card}</code>\n\n"
        f"پس از واریز، رسید را برای مدیریت ارسال کن."
    )

    await call.answer()
    await call.message.answer(text)


# =========================
# ADMIN - CHANNELS
# =========================

@dp.callback_query(F.data == "adm_channels")
async def admin_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    channels = get_mandatory_channels()

    text = "🔗 <b>عضویت اجباری</b>\n\n"
    if channels:
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch['username']}\n"
    else:
        text += "هیچ کانالی اضافه نشده.\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن کانال", callback_data="adm_add_channel")],
        [InlineKeyboardButton(text="🗑 حذف کانال", callback_data="adm_del_channel")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="adm_back")],
    ])

    await call.answer()
    await call.message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "adm_add_channel")
async def admin_add_channel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await state.set_state(AdminStates.waiting_channel)
    await call.answer()
    await call.message.answer(
        "📢 آیدی عمومی کانال را بفرست، مثلاً:\n"
        "<code>@mychannel</code>\n\n"
        "ربات باید در آن کانال ادمین باشد.\n"
        "فعلاً لینک‌های خصوصی پشتیبانی نمی‌شوند.\n\n"
        "لغو: /cancel"
    )


@dp.message(AdminStates.waiting_channel)
async def save_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    value = message.text.strip()
    if value.startswith("https://t.me/"):
        username = "@" + value.split("https://t.me/", 1)[1].strip("/").split("/")[0]
    elif value.startswith("http://t.me/"):
        username = "@" + value.split("http://t.me/", 1)[1].strip("/").split("/")[0]
    elif value.startswith("@"):
        username = value.split()[0]
    else:
        username = "@" + value.split()[0]

    try:
        chat = await bot.get_chat(username)
        bot_me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat.id, bot_me.id)

        if bot_member.status not in ("administrator", "creator"):
            await message.answer(
                "❌ ربات در این کانال ادمین نیست.\n"
                "اول ربات را ادمین کن و دوباره بفرست."
            )
            return

        actual_username = chat.username
        if not actual_username:
            await message.answer(
                "❌ این کانال عمومی نیست. فعلاً یک کانال با @username بفرست."
            )
            return

        link = f"https://t.me/{actual_username}"

        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO mandatory_channels(username,link) VALUES(?,?)",
            (f"@{actual_username}", link)
        )
        conn.commit()
        conn.close()

        await state.clear()
        await message.answer(
            f"✅ کانال <b>@{actual_username}</b> به عضویت اجباری اضافه شد.",
            reply_markup=admin_menu()
        )

    except Exception as e:
        await message.answer(
            "❌ کانال پیدا نشد یا دسترسی ربات کافی نیست.\n"
            "آیدی را مثل <code>@channel</code> بفرست."
        )


@dp.callback_query(F.data == "adm_del_channel")
async def admin_delete_channel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    channels = get_mandatory_channels()
    if not channels:
        await call.answer("کانالی برای حذف وجود ندارد.", show_alert=True)
        return

    buttons = []
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {ch['username']}",
                callback_data=f"delch:{ch['id']}"
            )
        ])

    await call.answer()
    await call.message.answer(
        "کانالی که می‌خواهی حذف شود انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("delch:"))
async def delete_channel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    channel_id = int(call.data.split(":")[1])

    conn = get_db()
    conn.execute(
        "DELETE FROM mandatory_channels WHERE id=?",
        (channel_id,)
    )
    conn.commit()
    conn.close()

    await call.answer("✅ کانال حذف شد.", show_alert=True)
    await call.message.answer(
        "🔗 عضویت اجباری",
        reply_markup=admin_menu()
    )


# =========================
# ADMIN - COINS
# =========================

@dp.callback_query(F.data == "adm_coins")
async def admin_coins(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    await call.answer()
    await call.message.answer(
        "🪙 <b>مدیریت سکه</b>\n\n"
        "برای شارژ سکه خودت جهت تست:\n"
        "<code>/addcoins 1000</code>\n\n"
        f"پاداش هر ثبت سین: <b>{reward_per_view()} سکه</b>\n\n"
        "برای تغییر پاداش از پنل تنظیمات استفاده کن.",
        reply_markup=admin_menu()
    )


@dp.message(Command("addcoins"))
async def add_coins(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("مثال: <code>/addcoins 1000</code>")
        return

    try:
        amount = int(parts[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ مقدار سکه صحیح نیست.")
        return

    conn = get_db()
    conn.execute(
        "UPDATE users SET coins=coins+? WHERE telegram_id=?",
        (amount, message.from_user.id)
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ {amount} سکه اضافه شد.\n"
        f"موجودی جدید: {get_user_coins(message.from_user.id)}"
    )


# =========================
# ADMIN - ORDERS
# =========================

@dp.callback_query(F.data == "adm_orders")
async def admin_orders(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    conn = get_db()
    active = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE status='active'"
    ).fetchone()["c"]
    completed = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE status='completed'"
    ).fetchone()["c"]
    conn.close()

    await call.answer()
    await call.message.answer(
        f"📢 <b>مدیریت سفارش‌ها</b>\n\n"
        f"🟢 فعال: {active}\n"
        f"✅ تکمیل‌شده: {completed}\n\n"
        f"برای دیدن جزئیات بیشتر می‌توانیم در مرحله بعد مدیریت کامل سفارش‌ها را اضافه کنیم.",
        reply_markup=admin_menu()
    )


# =========================
# ADMIN - USERS
# =========================

@dp.callback_query(F.data == "adm_users")
async def admin_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]
    total_coins = conn.execute(
        "SELECT COALESCE(SUM(coins),0) AS c FROM users"
    ).fetchone()["c"]
    conn.close()

    await call.answer()
    await call.message.answer(
        f"👥 <b>کاربران</b>\n\n"
        f"تعداد کاربران: {count}\n"
        f"مجموع سکه موجود کاربران: {total_coins}",
        reply_markup=admin_menu()
    )


# =========================
# ADMIN - STATS
# =========================

@dp.callback_query(F.data == "adm_stats")
async def admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    conn = get_db()
    users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    orders = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    views = conn.execute("SELECT COUNT(*) AS c FROM views").fetchone()["c"]
    active = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE status='active'"
    ).fetchone()["c"]
    conn.close()

    await call.answer()
    await call.message.answer(
        f"📊 <b>آمار ربات</b>\n\n"
        f"👥 کاربران: {users}\n"
        f"📢 کل سفارش‌ها: {orders}\n"
        f"👁️ کل ثبت سین‌ها: {views}\n"
        f"🟢 سفارش‌های فعال: {active}",
        reply_markup=admin_menu()
    )


# =========================
# ADMIN - SETTINGS
# =========================

@dp.callback_query(F.data == "adm_settings")
async def admin_settings(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    card = get_setting("card_number", "")
    reward = reward_per_view()

    await call.answer()
    await call.message.answer(
        f"⚙️ <b>تنظیمات</b>\n\n"
        f"🪙 پاداش هر ثبت سین: {reward}\n"
        f"💳 شماره کارت: {card or 'ثبت نشده'}\n\n"
        f"از گزینه‌های زیر استفاده کن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🪙 تغییر پاداش", callback_data="set_reward")],
            [InlineKeyboardButton(text="💳 تغییر شماره کارت", callback_data="set_card")],
            [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="adm_back")],
        ])
    )


@dp.callback_query(F.data == "set_reward")
async def set_reward_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await state.set_state(AdminStates.waiting_reward)
    await call.answer()
    await call.message.answer(
        "🪙 مقدار پاداش هر ثبت سین را به عدد بفرست.\n"
        "مثال: <code>5</code>\n\n"
        "لغو: /cancel"
    )


@dp.message(AdminStates.waiting_reward)
async def set_reward_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        value = int(message.text.strip())
        if value <= 0 or value > 1000:
            raise ValueError
    except ValueError:
        await message.answer("❌ یک عدد بین 1 تا 1000 بفرست.")
        return

    set_setting("reward_per_view", value)
    await state.clear()

    await message.answer(
        f"✅ پاداش هر ثبت سین روی {value} سکه تنظیم شد.",
        reply_markup=admin_menu()
    )


@dp.callback_query(F.data == "set_card")
async def set_card_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await state.set_state(AdminStates.waiting_card)
    await call.answer()
    await call.message.answer(
        "💳 شماره کارت را بفرست.\n"
        "مثال: <code>6037xxxxxxxxxxxx</code>\n\n"
        "لغو: /cancel"
    )


@dp.message(AdminStates.waiting_card)
async def set_card_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    card = message.text.strip().replace(" ", "")

    if not card.isdigit() or len(card) != 16:
        await message.answer("❌ شماره کارت باید 16 رقم باشد.")
        return

    set_setting("card_number", card)
    set_setting("coin_purchase_enabled", "1")
    await state.clear()

    await message.answer(
        "✅ شماره کارت ذخیره شد و بخش خرید سکه فعال شد.",
        reply_markup=admin_menu()
    )


@dp.callback_query(F.data == "adm_back")
async def admin_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    await call.answer()
    await call.message.answer(
        "👑 <b>پنل مدیریت ViewCoin</b>",
        reply_markup=admin_menu()
    )


# =========================
# FALLBACK FOR ADMIN MENU ITEMS
# =========================

@dp.callback_query(F.data == "adm_settings")
async def admin_settings_duplicate(call: CallbackQuery):
    # این هندلر عمداً وجود ندارد؛ هندلر اصلی بالاتر آن را مدیریت می‌کند.
    pass


# =========================
# WEBHOOK / FASTAPI
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    if WEBHOOK_URL:
        await bot.set_webhook(
            f"{WEBHOOK_URL}/webhook",
            allowed_updates=dp.resolve_used_update_types()
        )

    yield

    if WEBHOOK_URL:
        try:
            await bot.delete_webhook()
        except Exception:
            pass

    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "ViewCoin"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}
