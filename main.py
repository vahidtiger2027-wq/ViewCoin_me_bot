import os, sqlite3, random, logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, Update,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "5412332176"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
DB_NAME = os.getenv("DB_NAME", "viewcoin.db")

bot = (
    Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    if BOT_TOKEN else None
)

dp = Dispatcher()


# =========================
# DATABASE
# =========================

def con():
    c = sqlite3.connect(DB_NAME, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def q(sql, p=(), one=False, commit=False):
    c = con()
    try:
        r = c.execute(sql, p)
        x = r.fetchone() if one else r.fetchall()
        if commit:
            c.commit()
        return x
    finally:
        c.close()


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def s(k, d=""):
    r = q(
        "SELECT value FROM settings WHERE key=?",
        (k,),
        True
    )
    return r["value"] if r else d


def ss(k, v):
    q(
        """
        INSERT INTO settings(key,value)
        VALUES(?,?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
        """,
        (k, str(v)),
        commit=True
    )


def admin(uid):
    return uid == ADMIN_ID


def init():
    c = con()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        joined_at TEXT,
        view_coins INTEGER DEFAULT 0,
        member_diamonds INTEGER DEFAULT 0,
        earned_view INTEGER DEFAULT 0,
        earned_member INTEGER DEFAULT 0,
        spent_view INTEGER DEFAULT 0,
        spent_member INTEGER DEFAULT 0,
        referral_count INTEGER DEFAULT 0,
        referred_by INTEGER
    );

    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS mandatory_channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        link TEXT
    );

    CREATE TABLE IF NOT EXISTS order_options(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,
        amount INTEGER,
        price INTEGER,
        enabled INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        kind TEXT,
        target_link TEXT,
        target_amount INTEGER,
        price INTEGER,
        completed INTEGER DEFAULT 0,
        message_id INTEGER,
        channel TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        kind TEXT,
        verified INTEGER DEFAULT 0,
        rewarded INTEGER DEFAULT 0,
        created_at TEXT,
        UNIQUE(order_id,user_id)
    );

    CREATE TABLE IF NOT EXISTS coin_packages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        amount INTEGER,
        coins INTEGER,
        enabled INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        package_id INTEGER,
        amount INTEGER,
        coins INTEGER,
        status TEXT DEFAULT 'pending',
        receipt_file_id TEXT,
        created_at TEXT,
        approved_at TEXT
    );

    CREATE TABLE IF NOT EXISTS lotteries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        status TEXT DEFAULT 'open',
        winners INTEGER,
        prize_view INTEGER,
        prize_member INTEGER,
        created_at TEXT,
        drawn_at TEXT
    );

    CREATE TABLE IF NOT EXISTS lottery_tickets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lottery_id INTEGER,
        user_id INTEGER,
        payment_id INTEGER,
        created_at TEXT,
        UNIQUE(lottery_id,user_id)
    );
    """)

    defaults = {
        "view_enabled": "1",
        "member_enabled": "1",
        "coin_purchase_enabled": "0",
        "lottery_enabled": "1",

        "view_reward": "5",
        "member_reward": "5",

        "welcome_view_bonus": "40",
        "welcome_member_bonus": "40",

        "referral_reward": "1000",

        "view_channel": "@view_sin_channel",
        "member_channel": "@my_member_man",

        "card_number_1": "",
        "card_number_2": "",

        "payment_link": "",
        "merchant_id": "",
        "payment_api_enabled": "0"
    }

    for k, v in defaults.items():
        c.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (k, v)
        )

    # سفارش های ویو
    if c.execute(
        "SELECT COUNT(*) FROM order_options WHERE kind='view'"
    ).fetchone()[0] == 0:

        for amount, price in (
            (40, 40),
            (60, 60),
            (100, 100),
            (200, 200)
        ):
            c.execute(
                """
                INSERT INTO order_options(kind,amount,price)
                VALUES(?,?,?)
                """,
                ("view", amount, price)
            )

    # سفارش های ممبر
    if c.execute(
        "SELECT COUNT(*) FROM order_options WHERE kind='member'"
    ).fetchone()[0] == 0:

        for amount, price in (
            (10, 20),
            (20, 40),
            (30, 60),
            (40, 80),
            (50, 100)
        ):
            c.execute(
                """
                INSERT INTO order_options(kind,amount,price)
                VALUES(?,?,?)
                """,
                ("member", amount, price)
            )

    # بسته های خرید سکه
    if c.execute(
        "SELECT COUNT(*) FROM coin_packages"
    ).fetchone()[0] == 0:

        packages = (
            ("بسته ۱", 50000, 20000),
            ("بسته ۲", 100000, 40000),
            ("بسته ۳", 150000, 50000),
            ("بسته ۴", 200000, 200000)
        )

        for x in packages:
            c.execute(
                """
                INSERT INTO coin_packages(title,amount,coins)
                VALUES(?,?,?)
                """,
                x
            )

    c.commit()
    c.close()


# =========================
# USERS
# =========================

def adduser(u, ref=None):

    if q(
        "SELECT id FROM users WHERE id=?",
        (u.id,),
        True
    ):
        return False

    vb = int(s("welcome_view_bonus", "40"))
    mb = int(s("welcome_member_bonus", "40"))

    c = con()

    c.execute(
        """
        INSERT INTO users(
            id,name,username,joined_at,
            referred_by,
            view_coins,
            member_diamonds,
            earned_view,
            earned_member
        )
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            u.id,
            u.full_name,
            u.username or "",
            now(),
            ref,
            vb,
            mb,
            vb,
            mb
        )
    )

    c.commit()
    c.close()

    if ref and ref != u.id:

        if q(
            "SELECT id FROM users WHERE id=?",
            (ref,),
            True
        ):

            reward = int(
                s("referral_reward", "1000")
            )

            q(
                """
                UPDATE users
                SET
                    view_coins=view_coins+?,
                    earned_view=earned_view+?,
                    referral_count=referral_count+1
                WHERE id=?
                """,
                (reward, reward, ref),
                commit=True
            )

    return True


# =========================
# MENUS
# =========================

def menu():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 حساب کاربری")
            ],
            [
                KeyboardButton(text="🪙 جمع‌آوری سکه"),
                KeyboardButton(text="👁 ویوگیر")
            ],
            [
                KeyboardButton(text="👥 ممبرگیر"),
                KeyboardButton(text="📢 ثبت سفارش ویو")
            ],
            [
                KeyboardButton(text="👥 ثبت سفارش ممبر"),
                KeyboardButton(text="📋 سفارش‌های من")
            ],
            [
                KeyboardButton(text="💳 خرید سکه"),
                KeyboardButton(text="🎁 دعوت دوستان")
            ],
            [
                KeyboardButton(text="🎟️ قرعه‌کشی"),
                KeyboardButton(text="ℹ️ راهنما")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def amenu():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔗 عضویت اجباری"),
                KeyboardButton(text="🪙 مدیریت سکه")
            ],
            [
                KeyboardButton(text="📢 مدیریت سفارش‌ها"),
                KeyboardButton(text="👥 کاربران")
            ],
            [
                KeyboardButton(text="📊 آمار ربات"),
                KeyboardButton(text="⚙️ تنظیمات")
            ],
            [
                KeyboardButton(text="🎟️ قرعه‌کشی"),
                KeyboardButton(text="💳 پرداخت‌ها")
            ],
            [
                KeyboardButton(text="⬅️ منوی کاربر")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def mandatory_kb(rows):

    buttons = []

    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                text="عضویت در " + r["username"],
                url=r["link"]
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🔎 بررسی عضویت",
            callback_data="check_membership"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# =========================
# MEMBERSHIP
# =========================

async def member_ok(uid):

    if admin(uid):
        return True

    rows = q(
        "SELECT * FROM mandatory_channels"
    )

    for r in rows:

        try:

            m = await bot.get_chat_member(
                r["username"],
                uid
            )

            if m.status not in (
                "member",
                "administrator",
                "creator"
            ):
                return False

        except Exception:
            return False

    return True


async def gate(m):

    if await member_ok(m.from_user.id):
        return True

    rows = q(
        "SELECT * FROM mandatory_channels"
    )

    await m.answer(
        "🔒 ابتدا در کانال‌های اجباری عضو شو "
        "و سپس «بررسی عضویت» را بزن.",
        reply_markup=mandatory_kb(rows)
    )

    return False


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(m):

    args = m.text.split(maxsplit=1)

    ref = None

    if len(args) == 2:
        if args[1].isdigit():
            ref = int(args[1])

    new = adduser(
        m.from_user,
        ref
    )

    text = (
        "<b>به ViewCoin خوش آمدی 🌟</b>\n\n"
        "🪙 سکه ویو مخصوص ویوگیر است.\n"
        "💎 الماس ممبر مخصوص ممبرگیر است.\n"
    )

    if new:

        text += (
            "\n🎁 پاداش ورود:\n"
            f"🪙 {s('welcome_view_bonus','40')} سکه\n"
            f"💎 {s('welcome_member_bonus','40')} الماس"
        )

    await m.answer(
        text,
        reply_markup=menu()
    )

    if not await member_ok(
        m.from_user.id
    ):

        await m.answer(
            "🔒 عضویت اجباری:",
            reply_markup=mandatory_kb(
                q("SELECT * FROM mandatory_channels")
            )
        )


# =========================
# ADMIN
# =========================

@dp.message(Command("admin"))
async def admin_command(m):

    if admin(m.from_user.id):

        await m.answer(
            "👨‍💼 پنل مدیریت",
            reply_markup=amenu()
        )


@dp.message(F.text == "⬅️ منوی کاربر")
async def user_menu(m):

    await m.answer(
        "منوی کاربر 👇",
        reply_markup=menu()
    )


# =========================
# MEMBERSHIP CHECK
# =========================

@dp.callback_query(F.data == "check_membership")
async def check_membership(c):

    if await member_ok(c.from_user.id):

        await c.message.answer(
            "✅ عضویت تأیید شد.",
            reply_markup=menu()
        )

    else:

        await c.answer(
            "هنوز عضویت تأیید نشده.",
            show_alert=True
        )


# =========================
# ACCOUNT
# =========================

@dp.message(F.text == "👤 حساب کاربری")
async def account(m):

    if not await gate(m):
        return

    u = q(
        "SELECT * FROM users WHERE id=?",
        (m.from_user.id,),
        True
    )

    me = await bot.get_me()

    username = (
        "@" + u["username"]
        if u["username"]
        else "ندارد"
    )

    await m.answer(
        f"""
<b>👤 حساب کاربری</b>

👤 نام: {u['name']}
🔹 نام کاربری: {username}
🆔 آیدی عددی: {u['id']}
📅 تاریخ عضویت: {u['joined_at']}

🪙 سکه ویو: <b>{u['view_coins']}</b>
💎 الماس ممبر: <b>{u['member_diamonds']}</b>

📥 سکه دریافتی: {u['earned_view']}
📤 سکه مصرفی: {u['spent_view']}

📥 الماس دریافتی: {u['earned_member']}
📤 الماس مصرفی: {u['spent_member']}

🎁 تعداد دعوت‌ها: {u['referral_count']}

🔗 لینک دعوت:
https://t.me/{me.username}?start={u['id']}
"""
    )


# =========================
# REFERRAL
# =========================

@dp.message(F.text == "🎁 دعوت دوستان")
async def referral(m):

    me = await bot.get_me()

    reward = s(
        "referral_reward",
        "1000"
    )

    await m.answer(
        f"""
🎁 <b>دعوت دوستان</b>

💰 پاداش دعوت:
{reward} 🪙 سکه

🔗 لینک اختصاصی شما:

https://t.me/{me.username}?start={m.from_user.id}

هر کاربر فقط برای اولین ثبت‌نام از طریق لینک دعوت محاسبه می‌شود.
"""
    )


# =========================
# HELP
# =========================

@dp.message(F.text == "ℹ️ راهنما")
async def help_(m):

    await m.answer(
        """
<b>ℹ️ راهنمای ViewCoin</b>

👁 ویوگیر:
انجام وظایف و دریافت 🪙 سکه

👥 ممبرگیر:
عضویت در مقصد و دریافت 💎 الماس

📢 ثبت سفارش:
هزینه سفارش ویو از سکه ویو و
هزینه سفارش ممبر از الماس پرداخت می‌شود.

💳 خرید:
در صورت فعال بودن بخش خرید.

🎁 دعوت دوستان:
با دعوت کاربران جدید پاداش دریافت می‌کنی.

🎟️ قرعه‌کشی:
با خرید موفق می‌توانی بلیت دریافت کنی.
"""
    )


# =========================
# TASKS
# =========================

async def tasks(m, kind):

    if not await gate(m):
        return

    key = (
        "view_enabled"
        if kind == "view"
        else "member_enabled"
    )

    if s(key, "1") != "1":

        await m.answer(
            "این سیستم فعلاً خاموش است."
        )

        return

    orders = q(
        """
        SELECT *
        FROM orders
        WHERE kind=?
        AND completed=0
        ORDER BY id DESC
        LIMIT 10
        """,
        (kind,)
    )

    if not orders:

        await m.answer(
            "فعلاً سفارشی برای انجام وجود ندارد."
        )

        return

    for o in orders:

        if q(
            """
            SELECT *
            FROM tasks
            WHERE order_id=?
            AND user_id=?
            AND rewarded=1
            """,
            (
                o["id"],
                m.from_user.id
            ),
            True
        ):
            continue

        reward = int(
            s(
                "view_reward"
                if kind == "view"
                else "member_reward",
                "5"
            )
        )

        link = (
            o["target_link"]
            or s("view_channel")
        )

        if kind == "view":

            label = "👁 انجام ویو"
            reward_text = "🪙 دریافت سکه"

        else:

            label = "👥 عضویت"
            reward_text = "💎 دریافت الماس"

        buttons = []

        if link:

            buttons.append([
                InlineKeyboardButton(
                    text=label,
                    url=link
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                text=reward_text,
                callback_data=f"claim:{o['id']}"
            )
        ])

        await m.answer(
            f"""
<b>سفارش #{o['id']}</b>

🎯 هدف: {o['target_amount']}

🎁 پاداش: {reward}
""",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=buttons
            )
        )


@dp.message(
    F.text.in_(
        {
            "🪙 جمع‌آوری سکه",
            "👁 ویوگیر"
        }
    )
)
async def view_tasks(m):

    await tasks(m, "view")


@dp.message(F.text == "👥 ممبرگیر")
async def member_tasks(m):

    await tasks(m, "member")


# =========================
# CLAIM TASK
# =========================

@dp.callback_query(
    F.data.startswith("claim:")
)
async def claim(c):

    order_id = int(
        c.data.split(":")[1]
    )

    o = q(
        "SELECT * FROM orders WHERE id=?",
        (order_id,),
        True
    )

    if not o or o["completed"]:

        await c.answer(
            "سفارش تمام شده.",
            show_alert=True
        )

        return

    if q(
        """
        SELECT *
        FROM tasks
        WHERE order_id=?
        AND user_id=?
        AND rewarded=1
        """,
        (
            o["id"],
            c.from_user.id
        ),
        True
    ):

        await c.answer(
            "قبلاً پاداش گرفتی.",
            show_alert=True
        )

        return

    # بررسی ممبر
    if o["kind"] == "member":

        try:

            mm = await bot.get_chat_member(
                o["target_link"],
                c.from_user.id
            )

            if mm.status not in (
                "member",
                "administrator",
                "creator"
            ):
                raise Exception()

        except Exception:

            await c.answer(
                "عضویت قابل تأیید نیست. "
                "ربات باید دسترسی لازم داشته باشد.",
                show_alert=True
            )

            return

    reward = int(
        s(
            "view_reward"
            if o["kind"] == "view"
            else "member_reward",
            "5"
        )
    )

    db = con()

    try:

        db.execute(
            """
            INSERT INTO tasks(
                order_id,
                user_id,
                kind,
                verified,
                rewarded,
                created_at
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                o["id"],
                c.from_user.id,
                o["kind"],
                1,
                1,
                now()
            )
        )

        if o["kind"] == "view":

            db.execute(
                """
                UPDATE users
                SET
                    view_coins=view_coins+?,
                    earned_view=earned_view+?
                WHERE id=?
                """,
                (
                    reward,
                    reward,
                    c.from_user.id
                )
            )

        else:

            db.execute(
                """
                UPDATE users
                SET
                    member_diamonds=member_diamonds+?,
                    earned_member=earned_member+?
                WHERE id=?
                """,
                (
                    reward,
                    reward,
                    c.from_user.id
                )
            )

        count = db.execute(
            """
            SELECT COUNT(*)
            FROM tasks
            WHERE order_id=?
            AND rewarded=1
            """,
            (o["id"],)
        ).fetchone()[0]

        if count >= o["target_amount"]:

            db.execute(
                """
                UPDATE orders
                SET completed=1
                WHERE id=?
                """,
                (o["id"],)
            )

        db.commit()

    finally:

        db.close()

    await c.answer(
        "پاداش ثبت شد ✅"
    )

    await c.message.answer(
        f"🎉 +{reward} "
        + (
            "🪙"
            if o["kind"] == "view"
            else "💎"
        )
    )

    completed = q(
        "SELECT completed FROM orders WHERE id=?",
        (o["id"],),
        True
    )

    if (
        completed
        and completed["completed"]
        and o["message_id"]
    ):

        try:

            await bot.delete_message(
                o["channel"],
                o["message_id"]
            )

        except Exception:
            pass


# =========================
# ORDER STATES
# =========================

states = {}


async def options(m, kind):

    rows = q(
        """
        SELECT *
        FROM order_options
        WHERE kind=?
        AND enabled=1
        ORDER BY amount
        """,
        (kind,)
    )

    buttons = []

    for r in rows:

        buttons.append([
            InlineKeyboardButton(
                text=f"{r['amount']} عدد = {r['price']}",
                callback_data=f"new:{kind}:{r['id']}"
            )
        ])

    await m.answer(
        "گزینه سفارش را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


# =========================
# VIEW ORDER
# =========================

@dp.message(F.text == "📢 ثبت سفارش ویو")
async def order_view(m):

    if (
        await gate(m)
        and s("view_enabled") == "1"
    ):

        await options(m, "view")


# =========================
# MEMBER ORDER
# =========================

@dp.message(F.text == "👥 ثبت سفارش ممبر")
async def order_member(m):

    if (
        await gate(m)
        and s("member_enabled") == "1"
    ):

        await options(m, "member")


@dp.callback_query(
    F.data.startswith("new:")
)
async def neworder(c):

    _, kind, oid = c.data.split(":")

    o = q(
        """
        SELECT *
        FROM order_options
        WHERE id=?
        """,
        (int(oid),),
        True
    )

    if not o:
        await c.answer(
            "گزینه پیدا نشد.",
            show_alert=True
        )
        return

    states[c.from_user.id] = {
        "kind": kind,
        "amount": o["amount"],
        "price": o["price"]
    }

    if kind == "member":

        await c.message.answer(
            "🔗 لینک مقصد ممبر را بفرست."
        )

    else:

        await c.message.answer(
            "برای ثبت سفارش ویو، "
            "عبارت «تأیید» را بفرست."
        )

    await c.answer()


# =========================
# MY ORDERS
# =========================

@dp.message(F.text == "📋 سفارش‌های من")
async def mine(m):

    rows = q(
        """
        SELECT *
        FROM orders
        WHERE owner_id=?
        ORDER BY id DESC
        LIMIT 20
        """,
        (m.from_user.id,)
    )

    if not rows:

        await m.answer(
            "سفارشی نداری."
        )

        return

    text = []

    for x in rows:

        kind = (
            "ویو"
            if x["kind"] == "view"
            else "ممبر"
        )

        status = (
            "✅"
            if x["completed"]
            else "🟡"
        )

        text.append(
            f"#{x['id']} "
            f"{kind} "
            f"{x['target_amount']} "
            f"{status}"
        )

    await m.answer(
        "\n".join(text)
    )


# =========================
# ORDER STATE
# =========================

@dp.message()
async def state(m):

    st = states.get(
        m.from_user.id
    )

    if not st:
        return

    # سفارش ممبر
    if (
        st["kind"] == "member"
        and "link" not in st
    ):

        link = (
            m.text or ""
        ).strip()

        if not link:

            await m.answer(
                "لینک معتبر بفرست."
            )

            return

        st["link"] = link

        u = q(
            """
            SELECT member_diamonds
            FROM users
            WHERE id=?
            """,
            (m.from_user.id,),
            True
        )

        if u["member_diamonds"] < st["price"]:

            states.pop(
                m.from_user.id,
                None
            )

            await m.answer(
                "💎 الماس کافی نیست."
            )

            return

        q(
            """
            INSERT INTO orders(
                owner_id,
                kind,
                target_link,
                target_amount,
                price,
                created_at
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                m.from_user.id,
                "member",
                st["link"],
                st["amount"],
                st["price"],
                now()
            ),
            commit=True
        )

        q(
            """
            UPDATE users
            SET
                member_diamonds=member_diamonds-?,
                spent_member=spent_member+?
            WHERE id=?
            """,
            (
                st["price"],
                st["price"],
                m.from_user.id
            ),
            commit=True
        )

        states.pop(
            m.from_user.id,
            None
        )

        await m.answer(
            "✅ سفارش ممبر ثبت شد."
        )

        return

    # سفارش ویو
    if (
        st["kind"] == "view"
        and (m.text or "").strip() == "تأیید"
    ):

        u = q(
            """
            SELECT view_coins
            FROM users
            WHERE id=?
            """,
            (m.from_user.id,),
            True
        )

        if u["view_coins"] < st["price"]:

            states.pop(
                m.from_user.id,
                None
            )

            await m.answer(
                "🪙 سکه کافی نیست."
            )

            return

        q(
            """
            INSERT INTO orders(
                owner_id,
                kind,
                target_link,
                target_amount,
                price,
                created_at
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                m.from_user.id,
                "view",
                s("view_channel"),
                st["amount"],
                st["price"],
                now()
            ),
            commit=True
        )

        q(
            """
            UPDATE users
            SET
                view_coins=view_coins-?,
                spent_view=spent_view+?
            WHERE id=?
            """,
            (
                st["price"],
                st["price"],
                m.from_user.id
            ),
            commit=True
        )

        states.pop(
            m.from_user.id,
            None
        )

        await m.answer(
            "✅ سفارش ویو ثبت شد."
        )


# =========================
# BUY COINS
# =========================

@dp.message(F.text == "💳 خرید سکه")
async def buy(m):

    if s(
        "coin_purchase_enabled",
        "0"
    ) != "1":

        await m.answer(
            "💳 خرید سکه فعلاً خاموش است."
        )

        return

    rows = q(
        """
        SELECT *
        FROM coin_packages
        WHERE enabled=1
        """
    )

    buttons = []

    for x in rows:

        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{x['title']} — "
                    f"{x['amount']:,} تومان / "
                    f"{x['coins']} سکه"
                ),
                callback_data=f"pkg:{x['id']}"
            )
        ])

    await m.answer(
        "بسته را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


@dp.callback_query(
    F.data.startswith("pkg:")
)
async def pkg(c):

    p = q(
        """
        SELECT *
        FROM coin_packages
        WHERE id=?
        """,
        (int(c.data.split(":")[1]),),
        True
    )

    if not p:

        await c.answer(
            "بسته پیدا نشد.",
            show_alert=True
        )

        return

    buttons = []

    if s("payment_link"):

        buttons.append([
            InlineKeyboardButton(
                text="🌐 لینک پرداخت",
                url=s("payment_link")
            )
        ])

    if (
        s("card_number_1")
        or s("card_number_2")
    ):

        buttons.append([
            InlineKeyboardButton(
                text="💳 پرداخت دستی و ارسال رسید",
                callback_data=f"manual:{p['id']}"
            )
        ])

    await c.message.answer(
        f"""
<b>{p['title']}</b>

💰 مبلغ:
{p['amount']:,} تومان

🪙 سکه:
{p['coins']}
""",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await c.answer()


# =========================
# MANUAL PAYMENT
# =========================

@dp.callback_query(
    F.data.startswith("manual:")
)
async def manual(c):

    pid = int(
        c.data.split(":")[1]
    )

    p = q(
        """
        SELECT *
        FROM coin_packages
        WHERE id=?
        """,
        (pid,),
        True
    )

    q(
        """
        INSERT INTO payments(
            user_id,
            method,
            package_id,
            amount,
            coins,
            created_at
        )
        VALUES(?,?,?,?,?,?)
        """,
        (
            c.from_user.id,
            "manual",
            pid,
            p["amount"],
            p["coins"],
            now()
        ),
        commit=True
    )

    cards = "\n".join(
        x for x in [
            "💳 " + s("card_number_1"),
            "💳 " + s("card_number_2")
        ]
        if x != "💳 "
    )

    await c.message.answer(
        f"""
💰 مبلغ پرداخت:
{p['amount']:,} تومان

{cards}

بعد از واریز، عکس رسید را بفرست.
"""
    )

    await c.answer()


# =========================
# RECEIPT
# =========================

@dp.message(F.photo)
async def receipt(m):

    p = q(
        """
        SELECT *
        FROM payments
        WHERE user_id=?
        AND status='pending'
        ORDER BY id DESC
        LIMIT 1
        """,
        (m.from_user.id,),
        True
    )

    if not p:
        return

    file_id = m.photo[-1].file_id

    q(
        """
        UPDATE payments
        SET receipt_file_id=?
        WHERE id=?
        """,
        (
            file_id,
            p["id"]
        ),
        commit=True
    )

    await m.answer(
        "🧾 رسید دریافت شد؛ "
        "بعد از تأیید مدیر، پرداخت ثبت می‌شود."
    )

    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=(
            f"رسید #{p['id']}\n"
            f"کاربر: {m.from_user.id}\n"
            f"مبلغ: {p['amount']:,}\n"
            f"سکه: {p['coins']}"
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ تأیید",
                        callback_data=f"payok:{p['id']}"
                    ),
                    InlineKeyboardButton(
                        text="❌ رد",
                        callback_data=f"payno:{p['id']}"
                    )
                ]
            ]
        )
    )


# =========================
# LOTTERY TICKET
# =========================

async def ticket(uid, pid):

    if s(
        "lottery_enabled",
        "1"
    ) != "1":
        return

    l = q(
        """
        SELECT *
        FROM lotteries
        WHERE status='open'
        ORDER BY id DESC
        LIMIT 1
        """,
        one=True
    )

    if l:

        q(
            """
            INSERT OR IGNORE INTO lottery_tickets(
                lottery_id,
                user_id,
                payment_id,
                created_at
            )
            VALUES(?,?,?,?)
            """,
            (
                l["id"],
                uid,
                pid,
                now()
            ),
            commit=True
        )


# =========================
# PAYMENT APPROVAL
# =========================

@dp.callback_query(
    F.data.startswith("payok:")
)
async def payok(c):

    if not admin(c.from_user.id):
        return

    p = q(
        "SELECT * FROM payments WHERE id=?",
        (int(c.data.split(":")[1]),),
        True
    )

    if (
        not p
        or p["status"] != "pending"
    ):
        return

    q(
        """
        UPDATE payments
        SET
            status='approved',
            approved_at=?
        WHERE id=?
        """,
        (
            now(),
            p["id"]
        ),
        commit=True
    )

    q(
        """
        UPDATE users
        SET
            view_coins=view_coins+?,
            earned_view=earned_view+?
        WHERE id=?
        """,
        (
            p["coins"],
            p["coins"],
            p["user_id"]
        ),
        commit=True
    )

    await ticket(
        p["user_id"],
        p["id"]
    )

    await c.message.answer(
        "✅ پرداخت تأیید شد."
    )

    await c.answer(
        "تأیید شد"
    )

    try:

        await bot.send_message(
            p["user_id"],
            f"✅ پرداخت تأیید شد.\n"
            f"🪙 +{p['coins']} سکه"
        )

    except Exception:
        pass


@dp.callback_query(
    F.data.startswith("payno:")
)
async def payno(c):

    if not admin(c.from_user.id):
        return

    q(
        """
        UPDATE payments
        SET status='rejected'
        WHERE id=?
        AND status='pending'
        """,
        (
            int(c.data.split(":")[1]),
        ),
        commit=True
    )

    await c.message.answer(
        "❌ پرداخت رد شد."
    )

    await c.answer()


# =========================
# LOTTERY
# =========================

@dp.message(F.text == "🎟️ قرعه‌کشی")
async def lottery(m):

    if not admin(m.from_user.id):

        if s(
            "lottery_enabled",
            "1"
        ) != "1":

            await m.answer(
                "قرعه‌کشی خاموش است."
            )

            return

        l = q(
            """
            SELECT *
            FROM lotteries
            WHERE status='open'
            ORDER BY id DESC
            LIMIT 1
            """,
            one=True
        )

        if not l:

            await m.answer(
                "دوره فعالی نیست."
            )

            return

        t = q(
            """
            SELECT id
            FROM lottery_tickets
            WHERE lottery_id=?
            AND user_id=?
            """,
            (
                l["id"],
                m.from_user.id
            ),
            True
        )

        await m.answer(
            f"""
🎟️ {l['title']}

بلیت تو:
{'✅ داری' if t else '❌ نداری'}

برای هر دوره باید خرید موفق همان دوره را داشته باشی.
"""
        )

        return

    l = q(
        """
        SELECT *
        FROM lotteries
        ORDER BY id DESC
        LIMIT 1
        """,
        one=True
    )

    if l:

        text = (
            f"🎟️ {l['title']}\n"
            f"وضعیت: {l['status']}\n"
            f"برنده: {l['winners']}\n"
            f"🪙 جایزه: {l['prize_view']}\n"
            f"💎 جایزه: {l['prize_member']}\n\n"
        )

    else:

        text = "🎟️ دوره‌ای وجود ندارد.\n\n"

    text += (
        "/lottery_new عنوان|برندگان|سکه|الماس\n"
        "/lottery_draw"
    )

    await m.answer(text)


@dp.message(Command("lottery_new"))
async def lnew(m):

    if not admin(m.from_user.id):
        return

    p = (
        m.text
        .partition(" ")[2]
        .split("|")
    )

    if len(p) != 4:

        await m.answer(
            "فرمت:\n"
            "/lottery_new عنوان|برندگان|سکه|الماس"
        )

        return

    q(
        """
        UPDATE lotteries
        SET status='closed'
        WHERE status='open'
        """,
        commit=True
    )

    q(
        """
        INSERT INTO lotteries(
            title,
            status,
            winners,
            prize_view,
            prize_member,
            created_at
        )
        VALUES(?,?,?,?,?,?)
        """,
        (
            p[0],
            "open",
            int(p[1]),
            int(p[2]),
            int(p[3]),
            now()
        ),
        commit=True
    )

    await m.answer(
        "🎟️ دوره جدید فعال شد."
    )


@dp.message(Command("lottery_draw"))
async def ldraw(m):

    if not admin(m.from_user.id):
        return

    l = q(
        """
        SELECT *
        FROM lotteries
        WHERE status='open'
        ORDER BY id DESC
        LIMIT 1
        """,
        one=True
    )

    if not l:

        await m.answer(
            "دوره فعالی وجود ندارد."
        )

        return

    ids = [
        x["user_id"]
        for x in q(
            """
            SELECT user_id
            FROM lottery_tickets
            WHERE lottery_id=?
            """,
            (l["id"],)
        )
    ]

    if not ids:

        await m.answer(
            "بلیتی وجود ندارد."
        )

        return

    winners = random.sample(
        ids,
        min(
            l["winners"],
            len(ids)
        )
    )

    db = con()

    try:

        for uid in winners:

            db.execute(
                """
                UPDATE users
                SET
                    view_coins=view_coins+?,
                    member_diamonds=member_diamonds+?,
                    earned_view=earned_view+?,
                    earned_member=earned_member+?
                WHERE id=?
                """,
                (
                    l["prize_view"],
                    l["prize_member"],
                    l["prize_view"],
                    l["prize_member"],
                    uid
                )
            )

        db.execute(
            """
            UPDATE lotteries
            SET
                status='drawn',
                drawn_at=?
            WHERE id=?
            """,
            (
                now(),
                l["id"]
            )
        )

        db.commit()

    finally:

        db.close()

    await m.answer(
        "🎉 برندگان:\n"
        + "\n".join(
            map(str, winners)
        )
    )

    for uid in winners:

        try:

            await bot.send_message(
                uid,
                f"""
🎉 <b>تبریک!</b>

شما برنده قرعه‌کشی شدی.

🪙 +{l['prize_view']} سکه
💎 +{l['prize_member']} الماس
"""
            )

        except Exception:
            pass


# =========================
# ADMIN STATS
# =========================

@dp.message(F.text == "📊 آمار ربات")
async def stats(m):

    if not admin(m.from_user.id):
        return

    users = q(
        "SELECT COUNT(*) c FROM users",
        one=True
    )["c"]

    orders = q(
        "SELECT COUNT(*) c FROM orders",
        one=True
    )["c"]

    payments = q(
        """
        SELECT COUNT(*) c
        FROM payments
        WHERE status='approved'
        """,
        one=True
    )["c"]

    await m.answer(
        f"""
📊 <b>آمار ربات</b>

👥 کاربران: {users}
📢 سفارش‌ها: {orders}
💳 پرداخت‌های موفق: {payments}
"""
    )


# =========================
# ADMIN SETTINGS
# =========================

@dp.message(F.text == "⚙️ تنظیمات")
async def settings(m):

    if not admin(m.from_user.id):
        return

    await m.answer(
        f"""
⚙️ <b>تنظیمات</b>

👁 ویو:
{s('view_enabled')}

👥 ممبر:
{s('member_enabled')}

💳 خرید:
{s('coin_purchase_enabled')}

🎟️ قرعه:
{s('lottery_enabled')}

🪙 پاداش ویو:
{s('view_reward')}

💎 پاداش ممبر:
{s('member_reward')}

🎁 پاداش ورود:
{s('welcome_view_bonus')} / {s('welcome_member_bonus')}

🎁 پاداش دعوت:
{s('referral_reward')}

👁 کانال ویو:
{s('view_channel')}

👥 کانال ممبر:
{s('member_channel')}

برای تغییر:

/set کلید مقدار
"""
    )


# =========================
# COIN MANAGEMENT
# =========================

@dp.message(F.text == "🪙 مدیریت سکه")
async def coins(m):

    if not admin(m.from_user.id):
        return

    await m.answer(
        """
🪙 مدیریت پاداش‌ها

/set view_reward 5
/set member_reward 5
/set welcome_view_bonus 40
/set welcome_member_bonus 40
/set referral_reward 1000
"""
    )


# =========================
# MANDATORY CHANNEL
# =========================

@dp.message(F.text == "🔗 عضویت اجباری")
async def mand(m):

    if not admin(m.from_user.id):
        return

    rows = q(
        "SELECT * FROM mandatory_channels"
    )

    if not rows:

        await m.answer(
            "کانال اجباری ثبت نشده."
        )

        return

    await m.answer(
        "\n".join(
            f"#{r['id']} "
            f"{r['username']} "
            f"{r['link']}"
            for r in rows
        )
    )


# =========================
# USERS
# =========================

@dp.message(F.text == "👥 کاربران")
async def users(m):

    if not admin(m.from_user.id):
        return

    rows = q(
        """
        SELECT *
        FROM users
        ORDER BY id DESC
        LIMIT 30
        """
    )

    if not rows:

        await m.answer(
            "کاربری نیست."
        )

        return

    await m.answer(
        "\n".join(
            f"{u['id']} "
            f"🪙{u['view_coins']} "
            f"💎{u['member_diamonds']}"
            for u in rows
        )
    )


# =========================
# ORDER MANAGEMENT
# =========================

@dp.message(F.text == "📢 مدیریت سفارش‌ها")
async def admin_orders(m):

    if not admin(m.from_user.id):
        return

    rows = q(
        """
        SELECT *
        FROM order_options
        """
    )

    if not rows:

        await m.answer(
            "گزینه سفارشی نیست."
        )

        return

    await m.answer(
        "\n".join(
            f"#{x['id']} "
            f"{x['kind']} "
            f"{x['amount']}="
            f"{x['price']} "
            f"{'روشن' if x['enabled'] else 'خاموش'}"
            for x in rows
        )
    )


# =========================
# PAYMENTS
# =========================

@dp.message(F.text == "💳 پرداخت‌ها")
async def admin_payments(m):

    if not admin(m.from_user.id):
        return

    rows = q(
        """
        SELECT *
        FROM payments
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 30
        """
    )

    if not rows:

        await m.answer(
            "پرداخت معلقی نیست."
        )

        return

    await m.answer(
        "\n".join(
            f"#{x['id']} "
            f"user{x['user_id']} "
            f"{x['amount']:,} "
            f"{x['coins']} سکه"
            for x in rows
        )
    )


# =========================
# SET COMMAND
# =========================

@dp.message(Command("set"))
async def setcmd(m):

    if not admin(m.from_user.id):
        return

    p = m.text.split(
        maxsplit=2
    )

    if len(p) < 3:

        await m.answer(
            "فرمت:\n/set کلید مقدار"
        )

        return

    allowed = {
        "view_enabled",
        "member_enabled",
        "coin_purchase_enabled",
        "lottery_enabled",

        "view_reward",
        "member_reward",

        "welcome_view_bonus",
        "welcome_member_bonus",

        "referral_reward",

        "view_channel",
        "member_channel",

        "card_number_1",
        "card_number_2",

        "payment_link",
        "merchant_id",
        "payment_api_enabled"
    }

    if p[1] not in allowed:

        await m.answer(
            "❌ این کلید قابل تنظیم نیست."
        )

        return

    ss(
        p[1],
        p[2]
    )

    await m.answer(
        "✅ ذخیره شد."
    )


# =========================
# ADD MANDATORY CHANNEL
# =========================

@dp.message(Command("addchannel"))
async def addch(m):

    if not admin(m.from_user.id):
        return

    p = m.text.split()

    if len(p) < 3:

        await m.answer(
            "فرمت:\n"
            "/addchannel @channel https://t.me/channel"
        )

        return

    q(
        """
        INSERT INTO mandatory_channels(
            username,
            link
        )
        VALUES(?,?)
        """,
        (
            p[1],
            p[2]
        ),
        commit=True
    )

    await m.answer(
        "✅ کانال اضافه شد."
    )


# =========================
# DELETE MANDATORY CHANNEL
# =========================

@dp.message(Command("delchannel"))
async def delch(m):

    if not admin(m.from_user.id):
        return

    p = m.text.split()

    if len(p) < 2:

        await m.answer(
            "فرمت:\n/delchannel ID"
        )

        return

    q(
        """
        DELETE FROM mandatory_channels
        WHERE id=?
        """,
        (
            int(p[1]),
        ),
        commit=True
    )

    await m.answer(
        "✅ حذف شد."
    )


# =========================
# FASTAPI / WEBHOOK
# =========================

@asynccontextmanager
async def life(app):

    init()

    if bot and WEBHOOK_URL:

        try:

            await bot.set_webhook(
                WEBHOOK_URL + "/webhook",
                drop_pending_updates=True
            )

        except Exception:

            logging.exception(
                "webhook"
            )

    yield

    if bot:

        await bot.session.close()


app = FastAPI(
    title="ViewCoin",
    lifespan=life
)


@app.get("/")
async def root():

    return {
        "status": "ok",
        "bot": "ViewCoin"
    }


@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }


@app.post("/webhook")
async def webhook(request: Request):

    if not bot:

        return {
            "ok": False,
            "error": "BOT_TOKEN missing"
        }

    data = await request.json()

    update = Update.model_validate(
        data,
        context={"bot": bot}
    )

    await dp.feed_update(
        bot,
        update
    )

    return {
        "ok": True
    }
