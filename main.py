import os
import sqlite3
import asyncio
import random
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
VIEW_CHANNEL = os.getenv("VIEW_CHANNEL", "@view_sin_channel").strip()
MEMBER_CHANNEL = os.getenv("MEMBER_CHANNEL", "@my_member_man").strip()
DB_NAME = os.getenv("DB_NAME", "viewcoin.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())


def db():
    c = sqlite3.connect(DB_NAME)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        coins INTEGER DEFAULT 0,
        diamonds INTEGER DEFAULT 0,
        gift INTEGER DEFAULT 0,
        total_views INTEGER DEFAULT 0,
        today_views INTEGER DEFAULT 0,
        last_view_day TEXT,
        referral_count INTEGER DEFAULT 0,
        referral_income INTEGER DEFAULT 0,
        prizes INTEGER DEFAULT 0,
        referred_by INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS settings(
        k TEXT PRIMARY KEY,
        v TEXT
    );

    CREATE TABLE IF NOT EXISTS packages(
        kind TEXT,
        code TEXT PRIMARY KEY,
        cost INTEGER,
        target INTEGER,
        price INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,
        owner INTEGER,
        cost INTEGER,
        target INTEGER,
        current INTEGER DEFAULT 0,
        source_chat TEXT,
        source_message INTEGER,
        target_link TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS claims(
        order_id INTEGER,
        user_id INTEGER,
        created_at TEXT,
        PRIMARY KEY(order_id,user_id)
    );

    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        kind TEXT,
        amount INTEGER,
        price INTEGER,
        status TEXT DEFAULT 'pending',
        receipt_chat INTEGER,
        receipt_message INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS admins(
        id INTEGER PRIMARY KEY,
        can_settings INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS ticket_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price INTEGER,
        tickets INTEGER
    );

    CREATE TABLE IF NOT EXISTS lottery(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        active INTEGER DEFAULT 0,
        draw_at TEXT,
        round_no INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS prizes(
        place INTEGER PRIMARY KEY,
        coins INTEGER DEFAULT 0,
        diamonds INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS tickets(
        round_id INTEGER,
        user_id INTEGER,
        amount INTEGER DEFAULT 0,
        PRIMARY KEY(round_id,user_id)
    );
    """)

    defaults = {
        "bot_enabled": "1",
        "daily_coins": "10",
        "referral_coins": "200",
        "member_reward": "1",
        "card_number": "145679965776",
        "shop_enabled": "1",
        "lottery_enabled": "1",
        "monthly_gift_amount": "0",
        "monthly_gift_type": "coins",
        "last_gift_month": ""
    }

    for k, v in defaults.items():
        c.execute(
            "INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)",
            (k, v)
        )

    views = [
        ("v40", 40, 40),
        ("v50", 50, 50),
        ("v100", 100, 100),
        ("v200", 200, 200)
    ]

    members = [
        ("m20", 20, 10),
        ("m40", 40, 20),
        ("m60", 60, 30),
        ("m80", 80, 40),
        ("m100", 100, 50)
    ]

    coins = [
        ("c20000", 20000, 0, 50000),
        ("c40000", 40000, 0, 100000),
        ("c50000", 50000, 0, 150000),
        ("c200000", 200000, 0, 200000)
    ]

    diamonds = [
        ("d100", 100, 0, 25000),
        ("d250", 250, 0, 50000),
        ("d500", 500, 0, 100000),
        ("d1000", 1000, 0, 200000),
        ("d4000", 4000, 0, 800000)
    ]

    for x in views:
        c.execute(
            "INSERT OR IGNORE INTO packages VALUES(?,?,?,?,0)",
            ("view", *x)
        )

    for x in members:
        c.execute(
            "INSERT OR IGNORE INTO packages VALUES(?,?,?,?,0)",
            ("member", *x)
        )

    for x in coins:
        c.execute(
            "INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)",
            ("coinshop", x[0], x[1], x[2], x[3])
        )

    for x in diamonds:
        c.execute(
            "INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)",
            ("diamondshop", x[0], x[1], x[2], x[3])
        )

    for price, t in [
        (50000, 2),
        (100000, 4),
        (200000, 6),
        (500000, 10)
    ]:
        c.execute(
            "INSERT OR IGNORE INTO ticket_rules(price,tickets) VALUES(?,?)",
            (price, t)
        )

    for p in (1, 2, 3):
        c.execute(
            "INSERT OR IGNORE INTO prizes(place,coins,diamonds) VALUES(?,?,?)",
            (p, 0, 0)
        )

    c.execute(
        "INSERT OR IGNORE INTO admins(id,can_settings) VALUES(?,1)",
        (ADMIN_ID,)
    )

    c.commit()
    c.close()


def getset(k, default=""):
    c = db()
    r = c.execute(
        "SELECT v FROM settings WHERE k=?",
        (k,)
    ).fetchone()
    c.close()

    return r["v"] if r else default


def setset(k, v):
    c = db()
    c.execute(
        "INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)",
        (k, str(v))
    )
    c.commit()
    c.close()


def is_admin(uid):
    c = db()
    r = c.execute(
        "SELECT 1 FROM admins WHERE id=?",
        (uid,)
    ).fetchone()
    c.close()
    return bool(r)


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).date().isoformat()


def ensure_user(u, ref=None):
    c = db()

    r = c.execute(
        "SELECT * FROM users WHERE id=?",
        (u.id,)
    ).fetchone()

    if not r:
        c.execute(
            """
            INSERT INTO users(
                id,username,name,coins,diamonds,referred_by,created_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                u.id,
                u.username,
                u.full_name,
                0,
                0,
                ref,
                now()
            )
        )

        if ref and ref != u.id:
            rr = c.execute(
                "SELECT id FROM users WHERE id=?",
                (ref,)
            ).fetchone()

            if rr:
                reward = int(
                    getset("referral_coins", "200")
                )

                c.execute(
                    """
                    UPDATE users
                    SET
                        coins=coins+?,
                        referral_count=referral_count+1,
                        referral_income=referral_income+?
                    WHERE id=?
                    """,
                    (
                        reward,
                        reward,
                        ref
                    )
                )

    else:
        c.execute(
            """
            UPDATE users
            SET username=?,name=?
            WHERE id=?
            """,
            (
                u.username,
                u.full_name,
                u.id
            )
        )

    c.commit()
    c.close()


def main_menu(uid):
    rows = [
        [
            KeyboardButton(text="▪︎ جمع‌آوری سکه رایگان"),
            KeyboardButton(text="▪︎ حساب کاربری")
        ],
        [
            KeyboardButton(text="▪︎ جذب زیر مجموعه"),
            KeyboardButton(text="▪︎ ثبت تبلیغ ویو گیر و ممبر گیر")
        ],
        [
            KeyboardButton(text="▪︎ فروشگاه"),
            KeyboardButton(text="▪︎ انتقال سکه")
        ],
        [
            KeyboardButton(text="▪︎ انتقال الماس"),
            KeyboardButton(text="▪︎ قرعه کشی")
        ]
    ]

    if is_admin(uid):
        rows.append([
            KeyboardButton(text="▪︎ پنل مدیریت")
        ])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True
    )


def back_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🏠 بازگشت به منوی اصلی"
                )
            ]
        ],
        resize_keyboard=True
    )


async def guard(m):
    if is_admin(m.from_user.id):
        return True

    if getset("bot_enabled", "1") != "1":
        await m.answer(
            "ربات موقتاً توسط مدیریت خاموش است."
        )
        return False

    return True


class Flow(StatesGroup):
    view_post = State()
    member_link = State()
    transfer_id = State()
    transfer_amount = State()
    receipt = State()
    admin_value = State()
    admin_target = State()
    admin_amount = State()


async def membership_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 کانال ویوگیر",
                    url="https://t.me/view_sin_channel"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 کانال ممبرگیر",
                    url="https://t.me/my_member_man"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ بررسی عضویت",
                    callback_data="check_membership"
                )
            ]
        ]
    )


async def check_required_membership(uid: int) -> bool:
    if is_admin(uid):
        return True

    for chat in (
        VIEW_CHANNEL,
        MEMBER_CHANNEL
    ):
        try:
            member = await bot.get_chat_member(
                chat,
                uid
            )

            if member.status in (
                "left",
                "kicked"
            ):
                return False

        except Exception:
            return False

    return True


@dp.callback_query(
    F.data == "check_membership"
)
async def check_membership_callback(
    q: CallbackQuery
):
    if await check_required_membership(
        q.from_user.id
    ):
        ensure_user(q.from_user)

        await q.message.answer(
            "✅ عضویت شما تأیید شد. خوش آمدید 🌹",
            reply_markup=main_menu(
                q.from_user.id
            )
        )

        await q.answer(
            "عضویت هر دو کانال تأیید شد ✅"
        )

    else:
        await q.answer(
            "هنوز در هر دو کانال عضو نشده‌اید.",
            show_alert=True
        )


@dp.message(CommandStart())
async def start(m: Message):
    arg = (
        m.text.split(maxsplit=1)[1]
        if len(m.text.split()) > 1
        else ""
    )

    ref = int(arg) if arg.isdigit() else None

    ensure_user(
        m.from_user,
        ref
    )

    if not await check_required_membership(
        m.from_user.id
    ):
        await m.answer(
            "👋 <b>به ربات ویوگیر و ممبر گیر خوش آمدید</b> 🎉\n\n"
            "برای شروع در لینک‌های زیر عضو شوید.\n"
            "عضویت در هر دو کانال اجباری است. 🔐\n\n"
            "📢 کانال ویوگیر: @view_sin_channel\n"
            "👥 کانال ممبرگیر: @my_member_man\n\n"
            "بعد از عضویت روی «بررسی عضویت» بزنید 👇",
            reply_markup=await membership_keyboard()
        )
        return

    if not await guard(m):
        return

    await m.answer(
        "🎉 <b>به ربات ویوگیر و ممبر گیر خوش آمدید</b>\n\n"
        "از منوی زیر شروع کنید 👇",
        reply_markup=main_menu(
            m.from_user.id
        )
    )


@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    ensure_user(m.from_user)

    if not is_admin(m.from_user.id):
        await m.answer("دسترسی ندارید.")
        return

    await admin_panel(m)
ه

@dp.message(
    F.text == "🏠 بازگشت به منوی اصلی"
)
async def back(
    m: Message,
    state: FSMContext
):
    await state.clear()

    await m.answer(
        "منوی اصلی",
        reply_markup=main_menu(
            m.from_user.id
        )
    )    c.execute(
        "UPDATE users SET coins=coins-? WHERE id=?",
        (data["cost"], m.from_user.id)
    )

    c.execute(
        """
        INSERT INTO orders(
            kind,owner,cost,target,
            source_chat,source_message,created_at
        )
        VALUES('view',?,?,?,?,?,?)
        """,
        (
            m.from_user.id,
            data["cost"],
            data["target"],
            data["source_chat"],
            data["source_message"],
            now()
        )
    )

    oid = c.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    c.commit()
    c.close()

    try:
        sent = await bot.copy_message(
            chat_id=VIEW_CHANNEL,
            from_chat_id=int(data["source_chat"]),
            message_id=data["source_message"]
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ثبت بازدید 🪙",
                        callback_data=f"vc:{oid}"
                    ),
                    InlineKeyboardButton(
                        text="ورود به ربات 🤖",
                        url=f"https://t.me/{(await bot.get_me()).username}"
                    )
                ]
            ]
        )

        await bot.edit_message_reply_markup(
            VIEW_CHANNEL,
            sent.message_id,
            reply_markup=kb
        )

        c = db()

        c.execute(
            """
            UPDATE orders
            SET source_chat=?,source_message=?
            WHERE id=?
            """,
            (
                VIEW_CHANNEL,
                sent.message_id,
                oid
            )
        )

        c.commit()
        c.close()

        await state.clear()

        await m.answer(
            "✅ پست با موفقیت منتشر شد.",
            reply_markup=main_menu(
                m.from_user.id
            )
        )

    except Exception:
        c = db()

        c.execute(
            "UPDATE users SET coins=coins+? WHERE id=?",
            (
                data["cost"],
                m.from_user.id
            )
        )

        c.execute(
            "DELETE FROM orders WHERE id=?",
            (oid,)
        )

        c.commit()
        c.close()

        await m.answer(
            "انتشار پست انجام نشد. "
            "مطمئن شوید ربات در کانال ویوگیر ادمین است."
        )


@dp.callback_query(
    F.data.startswith("vc:")
)
async def view_claim(q: CallbackQuery):

    oid = int(q.data.split(":")[1])
    uid = q.from_user.id

    ensure_user(q.from_user)

    c = db()

    o = c.execute(
        """
        SELECT *
        FROM orders
        WHERE id=? AND active=1
        """,
        (oid,)
    ).fetchone()

    if not o:
        c.close()

        await q.answer(
            "این سفارش فعال نیست.",
            show_alert=True
        )

        return

    if o["owner"] == uid:
        c.close()

        await q.answer(
            "صاحب تبلیغ نمی‌تواند "
            "برای سفارش خودش پاداش بگیرد.",
            show_alert=True
        )

        return

    old = c.execute(
        """
        SELECT 1
        FROM claims
        WHERE order_id=? AND user_id=?
        """,
        (
            oid,
            uid
        )
    ).fetchone()

    if old:
        c.close()

        await q.answer(
            "قبلاً پاداش این سفارش را گرفته‌اید.",
            show_alert=True
        )

        return

    reward = 1

    c.execute(
        """
        INSERT INTO claims
        VALUES(?,?,?)
        """,
        (
            oid,
            uid,
            now()
        )
    )

    c.execute(
        """
        UPDATE users
        SET
            coins=coins+?,
            total_views=total_views+1
        WHERE id=?
        """,
        (
            reward,
            uid
        )
    )

    c.execute(
        """
        UPDATE orders
        SET current=current+1
        WHERE id=?
        """,
        (oid,)
    )

    cur = c.execute(
        """
        SELECT current,target
        FROM orders
        WHERE id=?
        """,
        (oid,)
    ).fetchone()

    if cur["current"] >= cur["target"]:
        c.execute(
            """
            UPDATE orders
            SET active=0
            WHERE id=?
            """,
            (oid,)
        )

    c.commit()
    c.close()

    await q.answer(
        f"{reward} سکه دریافت شد 🪙"
    )

    try:
        if cur["current"] >= cur["target"]:
            await q.message.delete()
    except Exception:
        pass


@dp.message(
    F.text == "ثبت تبلیغ ممبرگیر"
)
async def member_packages(
    m: Message
):
    if not await guard(m):
        return

    c = db()

    rs = c.execute(
        """
        SELECT *
        FROM packages
        WHERE kind='member'
        ORDER BY cost
        """
    ).fetchall()

    c.close()

    kb = [
        [
            KeyboardButton(
                text=f"{r['cost']} 💎 ← {r['target']} ممبر"
            )
        ]
        for r in rs
    ]

    kb.append(
        [
            KeyboardButton(
                text="🏠 بازگشت به منوی اصلی"
            )
        ]
    )

    await m.answer(
        "پکیج ممبرگیر:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True
        )
    )


@dp.message(
    F.text.regexp(
        r"^\d+ 💎 ← \d+ ممبر$"
    )
)
async def member_package_pick(
    m: Message,
    state: FSMContext
):

    cost = int(
        m.text.split()[0]
    )

    target = int(
        m.text.split("←")[1]
        .split()[0]
    )

    c = db()

    r = c.execute(
        """
        SELECT diamonds
        FROM users
        WHERE id=?
        """,
        (m.from_user.id,)
    ).fetchone()

    c.close()

    if not r or r["diamonds"] < cost:
        await m.answer(
            "موجودی الماس کافی نیست."
        )
        return

    await state.update_data(
        cost=cost,
        target=target
    )

    await state.set_state(
        Flow.member_link
    )

    await m.answer(
        "🔗 لینک کانال یا گروه موردنظر "
        "را ارسال کنید.\n\n"
        "بعد از ارسال لینک، گزینه «ثبت لینک» "
        "نمایش داده می‌شود.",
        reply_markup=back_kb()
    )


@dp.message(
    Flow.member_link
)
async def receive_member_link(
    m: Message,
    state: FSMContext
):

    if m.text == "🏠 بازگشت به منوی اصلی":
        await state.clear()

        await m.answer(
            "منوی اصلی",
            reply_markup=main_menu(
                m.from_user.id
            )
        )

        return

    if not m.text:
        await m.answer(
            "لطفاً لینک کانال یا گروه را ارسال کنید."
        )
        return

    link = m.text.strip()

    if not (
        link.startswith("https://t.me/")
        or link.startswith("http://t.me/")
        or link.startswith("@")
    ):
        await m.answer(
            "❌ لینک معتبر نیست.\n"
            "مثال:\n"
            "https://t.me/example"
        )
        return

    await state.update_data(
        link=link
    )

    await m.answer(
        f"🔗 لینک دریافت شد:\n\n"
        f"<code>{link}</code>\n\n"
        "اگر درست است روی «ثبت لینک» بزنید.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="ثبت لینک"
                    )
                ],
                [
                    KeyboardButton(
                        text="🏠 بازگشت به منوی اصلی"
                    )
                ]
            ],
            resize_keyboard=True
        )
    )


@dp.message(
    F.text == "ثبت لینک"
)
async def publish_member(
    m: Message,
    state: FSMContext
):

    data = await state.get_data()

    if not data.get("link"):
        await m.answer(
            "ابتدا لینک کانال یا گروه را ارسال کنید."
        )
        return

    c = db()

    r = c.execute(
        """
        SELECT diamonds
        FROM users
        WHERE id=?
        """,
        (m.from_user.id,)
    ).fetchone()

    if not r or r["diamonds"] < data["cost"]:
        c.close()

        await m.answer(
            "موجودی الماس کافی نیست."
        )

        return

    c.execute(
        """
        UPDATE users
        SET diamonds=diamonds-?
        WHERE id=?
        """,
        (
            data["cost"],
            m.from_user.id
        )
    )

    c.execute(
        """
        INSERT INTO orders(
            kind,owner,cost,target,
            target_link,created_at
        )
        VALUES('member',?,?,?,?,?)
        """,
        (
            m.from_user.id,
            data["cost"],
            data["target"],
            data["link"],
            now()
        )
    )

    oid = c.execute(
        "SELECT last_insert_rowid()"
    ).fetchone()[0]

    c.commit()
    c.close()

    try:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="جویین در کانال 👥",
                        url=data["link"]
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="دریافت الماس 💎",
                        callback_data=f"mc:{oid}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="بازگشت به ربات 🤖",
                        url=f"https://t.me/{(await bot.get_me()).username}"
                    )
                ]
            ]
        )

        await bot.send_message(
            MEMBER_CHANNEL,
            f"📢 تبلیغ ممبرگیر\n\n"
            f"{data['link']}",
            reply_markup=kb
        )

        await state.clear()

        await m.answer(
            "✅ تبلیغ ممبرگیر منتشر شد.",
            reply_markup=main_menu(
                m.from_user.id
            )
        )

    except Exception:
        c = db()

        c.execute(
            """
            UPDATE users
            SET diamonds=diamonds+?
            WHERE id=?
            """,
            (
                data["cost"],
                m.from_user.id
            )
        )

        c.execute(
            "DELETE FROM orders WHERE id=?",
            (oid,)
        )

        c.commit()
        c.close()

        await m.answer(
            "انتشار انجام نشد؛ ربات باید "
            "در کانال ممبرگیر ادمین باشد."
        )    if setting=='new_admin':
        if not m.text or not m.text.isdigit(): await m.answer('شناسه باید عددی باشد.'); return
        c=db(); c.execute('INSERT OR REPLACE INTO admins(id,can_settings) VALUES(?,1)',(int(m.text),)); c.commit(); c.close(); await state.clear(); await m.answer('✅ ادمین اضافه شد.',reply_markup=main_menu(m.from_user.id)); return
    if setting in ('card_number','gateway_url'):
        v=m.text.strip() if m.text else ''
        if setting=='gateway_url' and v=='0': v=''
    else:
        if not m.text or not m.text.isdigit(): await m.answer('فقط عدد بفرستید.'); return
        v=m.text
    setset(setting,v); await state.clear(); await m.answer('✅ ذخیره شد.',reply_markup=await admin_reply())

async def admin_reply(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='🛠 بازگشت به پنل مدیریت')],[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True)

@dp.message(F.text=='🛠 بازگشت به پنل مدیریت')
async def admin_back(m:Message):
    if is_admin(m.from_user.id): await admin_panel(m)

@dp.message(F.text=='تنظیمات فروشگاه')
async def shop_settings(m:Message):
    if not is_admin(m.from_user.id): return
    await m.answer(f"تنظیمات فروشگاه\n\nشماره کارت: {getset('card_number')}\nلینک درگاه: {getset('gateway_url') or 'تنظیم نشده'}",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='تنظیم لینک درگاه'),KeyboardButton(text='تنظیم شماره کارت')],[KeyboardButton(text='🛠 بازگشت به پنل مدیریت')]],resize_keyboard=True))

async def package_menu(kind):
    c=db(); rs=c.execute('SELECT * FROM packages WHERE kind=? ORDER BY code',(kind,)).fetchall(); c.close(); rows=[]
    for r in rs: rows.append([InlineKeyboardButton(text=f"{r['cost']} → {r['target']}",callback_data=f'pkg:{kind}:{r["code"]}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(F.text=='تنظیم سفارش ویو گیر')
async def view_settings(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind='view' ORDER BY cost").fetchall(); c.close(); await m.answer('تنظیم سفارش ویو گیر\n\n'+ '\n'.join(f"{r['cost']} سکه → {r['target']} ویو" for r in rs),reply_markup=await package_menu('view'))

@dp.message(F.text=='تنظیم سفارشات ممبرگیر')
async def member_settings(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind='member' ORDER BY cost").fetchall(); c.close(); await m.answer('تنظیم سفارشات ممبرگیر\n\n'+'\n'.join(f"{r['cost']} الماس → {r['target']} ممبر" for r in rs),reply_markup=await package_menu('member'))

@dp.callback_query(F.data.startswith('pkg:'))
async def package_pick(q:CallbackQuery,state:FSMContext):
    _,kind,code=q.data.split(':'); await state.update_data(pkg_kind=kind,pkg_code=code); await state.set_state(Flow.package_edit); await q.message.answer('مقادیر جدید را به شکل «هزینه هدف» ارسال کنید. مثال: 50 50\nبعد از آن دکمه اعمال تغییرات نمایش داده می‌شود.'); await q.answer()

@dp.message(Flow.package_edit)
async def package_edit(m:Message,state:FSMContext):
    if not m.text or not re.match(r'^\d+\s+\d+$',m.text.strip()): await m.answer('فرمت درست: 50 50'); return
    d=await state.get_data(); cost,target=map(int,m.text.split()); await state.update_data(new_cost=cost,new_target=target)
    await m.answer(f'تغییر آماده است: {cost} → {target}',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='اعمال تغییرات')],[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True))

@dp.message(F.text=='اعمال تغییرات')
async def apply_package(m:Message,state:FSMContext):
    d=await state.get_data();
    if not d.get('pkg_code'): await m.answer('ابتدا یک ردیف را انتخاب کنید.'); return
    c=db(); c.execute('UPDATE packages SET cost=?,target=? WHERE kind=? AND code=?',(d['new_cost'],d['new_target'],d['pkg_kind'],d['pkg_code'])); c.commit(); c.close(); await state.clear(); await m.answer('✅ تغییرات اعمال شد.',reply_markup=main_menu(m.from_user.id))

@dp.message(F.text=='تنظیم لینک‌های جویین اجباری')
async def mandatory_settings(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute('SELECT * FROM mandatory_channels ORDER BY id').fetchall(); c.close(); status='روشن ✅' if getset('mandatory_enabled','1')=='1' else 'خاموش ⛔'; text=f'تنظیم لینک‌های جویین اجباری\nوضعیت: {status}\nحداکثر ۱۰ لینک\n\n'; text+='\n'.join(f"{r['id']}. {r['link']} {'✅' if r['enabled'] else '⛔'}" for r in rs) or 'هنوز لینکی ثبت نشده.'
    kb=[[InlineKeyboardButton(text='روشن/خاموش',callback_data='mtoggle')],[InlineKeyboardButton(text='➕ افزودن لینک',callback_data='madd')]]
    for r in rs: kb.append([InlineKeyboardButton(text=f"❌ حذف {r['id']}",callback_data=f'mdel:{r["id"]}')])
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data=='mtoggle')
async def mtoggle(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    v='0' if getset('mandatory_enabled','1')=='1' else '1'; setset('mandatory_enabled',v); await q.answer('تغییر کرد'); await q.message.edit_reply_markup(reply_markup=None); await mandatory_settings(q.message)

@dp.callback_query(F.data=='madd')
async def madd(q:CallbackQuery,state:FSMContext):
    if not is_admin(q.from_user.id): return
    c=db(); n=c.execute('SELECT COUNT(*) n FROM mandatory_channels').fetchone()['n']; c.close()
    if n>=10: await q.answer('حداکثر ۱۰ لینک تنظیم شده است.',show_alert=True); return
    await state.set_state(Flow.mandatory_add); await q.message.answer('لینک کانال/گروه را بفرستید. مثال: @channel یا https://t.me/channel'); await q.answer()

@dp.message(Flow.mandatory_add)
async def mandatory_add(m:Message,state:FSMContext):
    link=(m.text or '').strip();
    if not (link.startswith('@') or re.match(r'^https?://t\.me/[^\s]+$',link)): await m.answer('لینک معتبر ارسال کنید.'); return
    title='کانال اجباری'; c=db()
    try: c.execute('INSERT INTO mandatory_channels(link,title,enabled) VALUES(?,?,1)',(link,title)); c.commit(); ok=True
    except sqlite3.IntegrityError: ok=False
    c.close(); await state.clear(); await m.answer('✅ لینک اضافه شد.' if ok else 'این لینک قبلاً ثبت شده.',reply_markup=main_menu(m.from_user.id))

@dp.callback_query(F.data.startswith('mdel:'))
async def mdel(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    rid=int(q.data.split(':')[1]); c=db(); c.execute('DELETE FROM mandatory_channels WHERE id=?',(rid,)); c.commit(); c.close(); await q.answer('حذف شد'); await q.message.delete()

@dp.message(F.text=='تنظیمات قرعه کشی')
async def lottery_settings(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute('SELECT * FROM prizes ORDER BY place').fetchall(); c.close(); en='روشن ✅' if getset('lottery_enabled','1')=='1' else 'خاموش ⛔'; period={'weekly':'هفتگی','15days':'۱۵ روزه','monthly':'ماهیانه'}.get(getset('lottery_period','weekly'),'هفتگی'); nextd=getset('lottery_next','تنظیم نشده')
    text=f'تنظیمات قرعه کشی\nوضعیت: {en}\nدوره: {period}\nقرعه بعدی: {nextd}\n\nجایزه اول: 🪙{rs[0]["coins"]:,} 💎{rs[0]["diamonds"]:,}\nجایزه دوم: 🪙{rs[1]["coins"]:,} 💎{rs[1]["diamonds"]:,}\nجایزه سوم: 🪙{rs[2]["coins"]:,} 💎{rs[2]["diamonds"]:,}'
    kb=[[InlineKeyboardButton(text='خاموش / روشن',callback_data='ltoggle')],[InlineKeyboardButton(text='تنظیم تاریخ قرعه کشی',callback_data='lperiod')],[InlineKeyboardButton(text='جایزه نفر اول',callback_data='prize:1')],[InlineKeyboardButton(text='جایزه نفر دوم',callback_data='prize:2')],[InlineKeyboardButton(text='جایزه نفر سوم',callback_data='prize:3')],[InlineKeyboardButton(text='اجرای قرعه کشی الان',callback_data='ldraw')]]
    await m.answer(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data=='ltoggle')
async def ltoggle(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    v='0' if getset('lottery_enabled','1')=='1' else '1'; setset('lottery_enabled',v)
    if v=='1' and not getset('lottery_next',''): set_next_lottery()
    await q.answer('تغییر کرد'); await q.message.delete(); await lottery_settings(q.message)

def set_next_lottery(base=None):
    period=getset('lottery_period','weekly'); dt=base or datetime.now(timezone.utc); days={'weekly':7,'15days':15,'monthly':30}.get(period,7); nxt=dt+timedelta(days=days); setset('lottery_next',nxt.isoformat()); return nxt

@dp.callback_query(F.data=='lperiod')
async def lperiod(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    await q.message.answer('دوره قرعه کشی را انتخاب کنید:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='هفتگی',callback_data='period:weekly')],[InlineKeyboardButton(text='۱۵ روزه',callback_data='period:15days')],[InlineKeyboardButton(text='ماهیانه',callback_data='period:monthly')]])); await q.answer()

@dp.callback_query(F.data.startswith('period:'))
async def period(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    p=q.data.split(':')[1]; setset('lottery_period',p); set_next_lottery(); await q.answer('دوره ذخیره شد'); await q.message.edit_text('✅ دوره قرعه کشی ذخیره شد.')

@dp.callback_query(F.data.startswith('prize:'))
async def prize_pick(q:CallbackQuery,state:FSMContext):
    if not is_admin(q.from_user.id): return
    place=int(q.data.split(':')[1]); await state.update_data(prize_place=place); await q.message.answer(f'جایزه نفر {place} را انتخاب کنید:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='جایزه الماس',callback_data='ptype:diamonds')],[InlineKeyboardButton(text='جایزه سکه',callback_data='ptype:coins')]])); await q.answer()

@dp.callback_query(F.data.startswith('ptype:'))
async def prize_type(q:CallbackQuery,state:FSMContext):
    if not is_admin(q.from_user.id): return
    typ=q.data.split(':')[1]; await state.update_data(prize_type=typ); await state.set_state(Flow.prize_value); await q.message.answer('مقدار جایزه را بفرستید.'); await q.answer()

@dp.message(Flow.prize_value)
async def prize_value(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit(): await m.answer('فقط عدد بفرستید.'); return
    d=await state.get_data(); c=db(); col='diamonds' if d['prize_type']=='diamonds' else 'coins'; c.execute(f'UPDATE prizes SET {col}=? WHERE place=?',(int(m.text),d['prize_place'])); c.commit(); c.close(); await state.clear(); await m.answer('✅ جایزه ذخیره شد.',reply_markup=main_menu(m.from_user.id))

async def draw_lottery(notify_admin=False):
    if getset('lottery_enabled','1')!='1': return False,'قرعه‌کشی خاموش است.'
    c=db(); lot=c.execute('SELECT * FROM lottery WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone()
    if not lot:
        c.execute('INSERT INTO lottery(active,round_no,draw_at) VALUES(1,COALESCE((SELECT MAX(round_no)+1 FROM lottery),1),?)',(getset('lottery_next',''),)); lot=c.execute('SELECT * FROM lottery ORDER BY id DESC LIMIT 1').fetchone()
    rs=c.execute('SELECT user_id,amount FROM tickets WHERE round_id=? AND amount>0',(lot['id'],)).fetchall()
    if not rs: c.close(); return False,'هیچ بلیتی ثبت نشده.'
    pool=[]
    for r in rs: pool.extend([r['user_id']]*r['amount'])
    winners=[]
    while pool and len(winners)<3:
        w=random.choice(pool); winners.append(w); pool=[x for x in pool if x!=w]
    prs=c.execute('SELECT * FROM prizes ORDER BY place').fetchall()
    for i,w in enumerate(winners,1):
        pr=next((x for x in prs if x['place']==i),None)
        if pr: c.execute('UPDATE users SET coins=coins+?,diamonds=diamonds+?,prizes=prizes+1 WHERE id=?',(pr['coins'],pr['diamonds'],w))
    c.execute('UPDATE lottery SET active=0 WHERE id=?',(lot['id'],)); c.commit(); c.close()
    for i,w in enumerate(winners,1):
        try: await bot.send_message(w,f'🎉 شما برنده جایزه رتبه {i} قرعه‌کشی شدید!')
        except Exception: pass
    set_next_lottery(); return True,f'قرعه‌کشی انجام شد. تعداد برندگان: {len(winners)}'

@dp.callback_query(F.data=='ldraw')
async def ldraw(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    ok,msg=await draw_lottery(); await q.message.answer(('✅ ' if ok else '⚠️ ')+msg); await q.answer()

@dp.message(F.text=='روشن/خاموش ربات')
async def toggle_bot(m:Message):
    if is_admin(m.from_user.id): v='0' if getset('bot_enabled','1')=='1' else '1'; setset('bot_enabled',v); await m.answer('وضعیت ربات: '+('روشن ✅' if v=='1' else 'خاموش ⛔'))

@dp.message(F.text=='تنظیم هدیه ماهانه')
async def monthly(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='monthly_gift_amount'); await state.set_state(Flow.admin_value); await m.answer('مقدار هدیه ماهانه را عددی بفرستید. برای غیرفعال کردن 0.')

@dp.message(F.text=='افزودن ادمین')
async def add_admin(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='new_admin'); await state.set_state(Flow.admin_value); await m.answer('شناسه عددی ادمین جدید را بفرستید.')

@dp.message(Command('gift'))
async def gift(m:Message):
    if not is_admin(m.from_user.id): return
    a=m.text.split();
    if len(a)!=3 or not a[1].isdigit() or not a[2].isdigit(): await m.answer('فرمت: /gift شناسه مبلغ'); return
    c=db(); c.execute('UPDATE users SET coins=coins+?,gift=gift+? WHERE id=?',(int(a[2]),int(a[2]),int(a[1]))); c.commit(); c.close(); await m.answer('هدیه ثبت شد.')

async def admin_value_override(m:Message,state:FSMContext):
    pass

# add-admin handling before generic admin_value is intentionally registered separately through filter below
@dp.message(Flow.admin_value,F.text)
async def admin_value_extra(m:Message,state:FSMContext):
    d=await state.get_data();
    if d.get('setting')!='new_admin': return
    if not m.text.isdigit(): await m.answer('شناسه باید عددی باشد.'); return
    c=db(); c.execute('INSERT OR REPLACE INTO admins(id,can_settings) VALUES(?,1)',(int(m.text),)); c.commit(); c.close(); await state.clear(); await m.answer('✅ ادمین اضافه شد.',reply_markup=main_menu(m.from_user.id))

async def scheduler():
    while True:
        try:
            if getset('lottery_enabled','1')=='1':
                nxt=getset('lottery_next','')
                if nxt:
                    try: due=datetime.fromisoformat(nxt); due=due if due.tzinfo else due.replace(tzinfo=timezone.utc)
                    except Exception: due=None
                    if due and datetime.now(timezone.utc)>=due: await draw_lottery()
                else: set_next_lottery()
            month=datetime.now(timezone.utc).strftime('%Y-%m')
            if getset('last_gift_month','')!=month:
                amount=int(getset('monthly_gift_amount','0'))
                if amount>0:
                    c=db(); winner=c.execute('SELECT id FROM users ORDER BY total_views DESC LIMIT 1').fetchone()
                    if winner:
                        typ=getset('monthly_gift_type','coins'); field='diamonds' if typ=='diamonds' else 'coins'; c.execute(f'UPDATE users SET {field}={field}+?,gift=gift+? WHERE id=?',(amount,amount,winner['id'])); c.commit()
                    c.close()
                setset('last_gift_month',month)
        except Exception: pass
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app):
    init_db()
    if WEBHOOK_URL: await bot.set_webhook(WEBHOOK_URL.rstrip('/')+'/telegram/webhook')
    task=asyncio.create_task(scheduler()); yield; task.cancel(); await bot.delete_webhook(); await bot.session.close()

app=FastAPI(lifespan=lifespan)

@app.get('/')
async def root(): return {'status':'ok','bot':'ViewCoin'}

@app.post('/telegram/webhook')
async def webhook(request:Request):
    data=await request.json()
    await dp.feed_raw_update(bot,data)
    return {'ok':True}
