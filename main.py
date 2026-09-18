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

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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
        username TEXT, name TEXT, coins INTEGER DEFAULT 0, diamonds INTEGER DEFAULT 0,
        gift INTEGER DEFAULT 0, total_views INTEGER DEFAULT 0, today_views INTEGER DEFAULT 0,
        last_view_day TEXT, referral_count INTEGER DEFAULT 0, referral_income INTEGER DEFAULT 0,
        prizes INTEGER DEFAULT 0, referred_by INTEGER, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);
    CREATE TABLE IF NOT EXISTS packages(
        kind TEXT, code TEXT PRIMARY KEY, cost INTEGER, target INTEGER, price INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, owner INTEGER, cost INTEGER,
        target INTEGER, current INTEGER DEFAULT 0, source_chat TEXT, source_message INTEGER,
        target_link TEXT, active INTEGER DEFAULT 1, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS claims(
        order_id INTEGER, user_id INTEGER, created_at TEXT, PRIMARY KEY(order_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, amount INTEGER,
        price INTEGER, status TEXT DEFAULT 'pending', receipt_chat INTEGER, receipt_message INTEGER,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, can_settings INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS ticket_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, price INTEGER, tickets INTEGER);
    CREATE TABLE IF NOT EXISTS lottery(
        id INTEGER PRIMARY KEY AUTOINCREMENT, active INTEGER DEFAULT 0, draw_at TEXT,
        round_no INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS prizes(
        place INTEGER PRIMARY KEY, coins INTEGER DEFAULT 0, diamonds INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS tickets(
        round_id INTEGER, user_id INTEGER, amount INTEGER DEFAULT 0,
        PRIMARY KEY(round_id,user_id)
    );
    """)
    defaults = {
        "bot_enabled":"1","daily_coins":"10","referral_coins":"200","member_reward":"1",
        "card_number":"145679965776","shop_enabled":"1","lottery_enabled":"1",
        "monthly_gift_amount":"0","monthly_gift_type":"coins","last_gift_month":""
    }
    for k,v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)",(k,v))
    views=[("v40",40,40),("v50",50,50),("v100",100,100),("v200",200,200)]
    members=[("m20",20,10),("m40",40,20),("m60",60,30),("m80",80,40),("m100",100,50)]
    coins=[("c20000",20000,0,50000),("c40000",40000,0,100000),
           ("c50000",50000,0,150000),("c200000",200000,0,200000)]
    diamonds=[("d100",100,0,25000),("d250",250,0,50000),("d500",500,0,100000),
              ("d1000",1000,0,200000),("d4000",4000,0,800000)]
    for x in views: c.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,0)",("view",*x))
    for x in members: c.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,0)",("member",*x))
    for x in coins: c.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)",("coinshop",x[0],x[1],x[2],x[3]))
    for x in diamonds: c.execute("INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)",("diamondshop",x[0],x[1],x[2],x[3]))
    for price,t in [(50000,2),(100000,4),(200000,6),(500000,10)]:
        c.execute("INSERT OR IGNORE INTO ticket_rules(price,tickets) VALUES(?,?)",(price,t))
    for p in (1,2,3):
        c.execute("INSERT OR IGNORE INTO prizes(place,coins,diamonds) VALUES(?,?,?)",(p,0,0))
    c.execute("INSERT OR IGNORE INTO admins(id,can_settings) VALUES(?,1)",(ADMIN_ID,))
    c.commit(); c.close()

def getset(k, default=""):
    c=db(); r=c.execute("SELECT v FROM settings WHERE k=?",(k,)).fetchone(); c.close()
    return r["v"] if r else default

def setset(k,v):
    c=db(); c.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)",(k,str(v))); c.commit(); c.close()

def is_admin(uid):
    c=db(); r=c.execute("SELECT 1 FROM admins WHERE id=?",(uid,)).fetchone(); c.close()
    return bool(r)

def now():
    return datetime.now(timezone.utc).isoformat()

def today():
    return datetime.now(timezone.utc).date().isoformat()

def ensure_user(u, ref=None):
    c=db()
    r=c.execute("SELECT * FROM users WHERE id=?",(u.id,)).fetchone()
    if not r:
        c.execute("""INSERT INTO users(id,username,name,coins,diamonds,referred_by,created_at)
                     VALUES(?,?,?,?,?,?,?)""",
                  (u.id,u.username,u.full_name,0,0,ref,now()))
        if ref and ref != u.id:
            rr=c.execute("SELECT id FROM users WHERE id=?",(ref,)).fetchone()
            if rr:
                reward=int(getset("referral_coins","200"))
                c.execute("UPDATE users SET coins=coins+?, referral_count=referral_count+1, referral_income=referral_income+? WHERE id=?", (reward,reward,ref))
    else:
        c.execute("UPDATE users SET username=?,name=? WHERE id=?",(u.username,u.full_name,u.id))
    c.commit(); c.close()

def main_menu(uid):
    rows=[
        [KeyboardButton(text="▪︎ جمع‌آوری سکه رایگان"),KeyboardButton(text="▪︎ حساب کاربری")],
        [KeyboardButton(text="▪︎ جذب زیر مجموعه"),KeyboardButton(text="▪︎ ثبت تبلیغ ویو گیر و ممبر گیر")],
        [KeyboardButton(text="▪︎ فروشگاه"),KeyboardButton(text="▪︎ انتقال سکه")],
        [KeyboardButton(text="▪︎ انتقال الماس"),KeyboardButton(text="▪︎ قرعه کشی")]
    ]
    if is_admin(uid): rows.append([KeyboardButton(text="▪︎ پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 بازگشت به منوی اصلی")]],resize_keyboard=True)

async def guard(m):
    if is_admin(m.from_user.id): return True
    if getset("bot_enabled","1")!="1":
        await m.answer("ربات موقتاً توسط مدیریت خاموش است.")
        return False
    return True

class Flow(StatesGroup):
    view_post=State(); member_link=State(); transfer_id=State(); transfer_amount=State()
    receipt=State(); admin_value=State(); admin_target=State(); admin_amount=State()

@dp.message(CommandStart())
async def start(m:Message):
    arg=m.text.split(maxsplit=1)[1] if len(m.text.split())>1 else ""
    ref=int(arg) if arg.isdigit() else None
    ensure_user(m.from_user,ref)
    if not await guard(m): return
    await m.answer("سلام 👋\nبه <b>ViewCoin</b> خوش آمدید.",reply_markup=main_menu(m.from_user.id))

@dp.message(Command("admin"))
async def admin_cmd(m:Message):
    ensure_user(m.from_user)
    if not is_admin(m.from_user.id):
        await m.answer("دسترسی ندارید."); return
    await admin_panel(m)

@dp.message(F.text=="🏠 بازگشت به منوی اصلی")
async def back(m:Message,state:FSMContext):
    await state.clear()
    await m.answer("منوی اصلی",reply_markup=main_menu(m.from_user.id))

@dp.message(F.text=="▪︎ جمع‌آوری سکه رایگان")
async def daily(m:Message):
    ensure_user(m.from_user)
    if not await guard(m): return
    c=db(); r=c.execute("SELECT * FROM users WHERE id=?",(m.from_user.id,)).fetchone()
    if r["last_view_day"]==today():
        c.close(); await m.answer("سکه روزانه امروز را قبلاً دریافت کرده‌اید.",reply_markup=main_menu(m.from_user.id)); return
    amount=int(getset("daily_coins","10"))
    c.execute("UPDATE users SET coins=coins+?,last_view_day=? WHERE id=?",(amount,today(),m.from_user.id))
    c.commit(); c.close()
    await m.answer(f"🎁 {amount} سکه رایگان دریافت کردید.",reply_markup=main_menu(m.from_user.id))

@dp.message(F.text=="▪︎ حساب کاربری")
async def account(m:Message):
    ensure_user(m.from_user)
    if not await guard(m): return
    c=db(); r=c.execute("SELECT * FROM users WHERE id=?",(m.from_user.id,)).fetchone(); c.close()
    s=f"👤 <b>حساب کاربری</b>\n\nنام: {r['name']}\n"
    if r["username"]: s+=f"یوزرنیم: @{r['username']}\n"
    s+=f"شناسه تلگرام: <code>{r['id']}</code>\n"
    s+=f"🎁 هدیه مدیریت: {r['gift']:,}\n👁 بازدیدهای شما: {r['total_views']:,}\n"
    s+=f"📅 بازدیدهای امروز: {r['today_views']:,}\n🏆 جوایز: {r['prizes']:,}\n"
    s+=f"👥 تعداد زیرمجموعه‌ها: {r['referral_count']:,}\n💰 دریافتی: {r['referral_income']:,}\n"
    s+=f"🪙 موجودی سکه شما: {r['coins']:,}\n💎 موجودی الماس شما: {r['diamonds']:,}"
    await m.answer(s,reply_markup=back_kb())

@dp.message(F.text=="▪︎ جذب زیر مجموعه")
async def referral(m:Message):
    ensure_user(m.from_user)
    if not await guard(m): return
    me=await bot.get_me()
    link=f"https://t.me/{me.username}?start={m.from_user.id}"
    await m.answer(
        f"👥 <b>زیرمجموعه‌گیری</b>\n\n"
        f"1️⃣ پاداش بازدید تبلیغات: قابل تنظیم توسط مدیریت\n"
        f"2️⃣ پاداش زیرمجموعه: {getset('referral_coins','200')} 🪙\n"
        f"3️⃣ سکه روزانه: {getset('daily_coins','10')} 🪙\n"
        f"4️⃣ سیستم ممبرگیر و ویوگیر فعال است.\n\n"
        f"لینک اختصاصی شما:\n<code>{link}</code>",reply_markup=back_kb())

@dp.message(F.text=="▪︎ ثبت تبلیغ ویو گیر و ممبر گیر")
async def ad_menu(m:Message):
    if not await guard(m): return
    kb=ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="ثبت تبلیغ ویوگیر"),KeyboardButton(text="ثبت تبلیغ ممبرگیر")],
        [KeyboardButton(text="🏠 بازگشت به منوی اصلی")]],resize_keyboard=True)
    await m.answer("نوع تبلیغ را انتخاب کنید:",reply_markup=kb)

@dp.message(F.text=="ثبت تبلیغ ویوگیر")
async def view_packages(m:Message):
    if not await guard(m): return
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind='view' ORDER BY cost").fetchall(); c.close()
    kb=[[KeyboardButton(text=f"{r['cost']} 🪙 ← {r['target']} بازدید")] for r in rs]
    kb.append([KeyboardButton(text="🏠 بازگشت به منوی اصلی")])
    await m.answer("پکیج ویوگیر:",reply_markup=ReplyKeyboardMarkup(keyboard=kb,resize_keyboard=True))

@dp.message(F.text.regexp(r"^\d+ 🪙 ← \d+ بازدید$"))
async def view_package_pick(m:Message,state:FSMContext):
    cost=int(m.text.split()[0]); target=int(m.text.split("←")[1].split()[0])
    c=db(); r=c.execute("SELECT coins FROM users WHERE id=?",(m.from_user.id,)).fetchone(); c.close()
    if not r or r["coins"]<cost: await m.answer("موجودی سکه کافی نیست."); return
    await state.update_data(cost=cost,target=target)
    await state.set_state(Flow.view_post)
    await m.answer("پست تبلیغاتی خود را همینجا ارسال کنید. متن، عکس، ویدئو و پست دارای لینک قابل قبول است.\nسپس «ثبت پست» را بزنید.",reply_markup=back_kb())

@dp.message(Flow.view_post)
async def receive_view(m:Message,state:FSMContext):
    if m.text=="🏠 بازگشت به منوی اصلی": return
    await state.update_data(source_chat=str(m.chat.id),source_message=m.message_id)
    await m.answer("پست دریافت شد. برای انتشار آن روی «ثبت پست» بزنید.",
                    reply_markup=ReplyKeyboardMarkup(keyboard=[
                        [KeyboardButton(text="ثبت پست")],[KeyboardButton(text="🏠 بازگشت به منوی اصلی")]],resize_keyboard=True))

@dp.message(F.text=="ثبت پست")
async def publish_view(m:Message,state:FSMContext):
    data=await state.get_data()
    if not data.get("source_message"): await m.answer("ابتدا پست را ارسال کنید."); return
    c=db(); r=c.execute("SELECT coins FROM users WHERE id=?",(m.from_user.id,)).fetchone()
    if not r or r["coins"]<data["cost"]: c.close(); await m.answer("موجودی کافی نیست."); return
    c.execute("UPDATE users SET coins=coins-? WHERE id=?",(data["cost"],m.from_user.id))
    c.execute("""INSERT INTO orders(kind,owner,cost,target,source_chat,source_message,created_at)
                 VALUES('view',?,?,?,?,?,?)""",
              (m.from_user.id,data["cost"],data["target"],data["source_chat"],data["source_message"],now()))
    oid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.commit(); c.close()
    try:
        sent=await bot.copy_message(chat_id=VIEW_CHANNEL,from_chat_id=int(data["source_chat"]),
                                    message_id=data["source_message"])
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ثبت بازدید 🪙",callback_data=f"vc:{oid}"),
             InlineKeyboardButton(text="ورود به ربات 🤖",url=f"https://t.me/{(await bot.get_me()).username}")]])
        await bot.edit_message_reply_markup(VIEW_CHANNEL,sent.message_id,reply_markup=kb)
        c=db(); c.execute("UPDATE orders SET source_chat=?,source_message=? WHERE id=?",(VIEW_CHANNEL,sent.message_id,oid)); c.commit(); c.close()
        await state.clear(); await m.answer("✅ پست با موفقیت منتشر شد.",reply_markup=main_menu(m.from_user.id))
    except Exception as e:
        c=db(); c.execute("UPDATE users SET coins=coins+? WHERE id=?",(data["cost"],m.from_user.id)); c.execute("DELETE FROM orders WHERE id=?",(oid,)); c.commit(); c.close()
        await m.answer("انتشار پست انجام نشد. مطمئن شوید ربات در کانال ویوگیر ادمین است.")

@dp.callback_query(F.data.startswith("vc:"))
async def view_claim(q:CallbackQuery):
    oid=int(q.data.split(":")[1]); uid=q.from_user.id; ensure_user(q.from_user)
    c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND active=1",(oid,)).fetchone()
    if not o: c.close(); await q.answer("این سفارش فعال نیست.",show_alert=True); return
    if o["owner"]==uid: c.close(); await q.answer("صاحب تبلیغ نمی‌تواند برای سفارش خودش پاداش بگیرد.",show_alert=True); return
    old=c.execute("SELECT 1 FROM claims WHERE order_id=? AND user_id=?",(oid,uid)).fetchone()
    if old: c.close(); await q.answer("قبلاً پاداش این سفارش را گرفته‌اید.",show_alert=True); return
    reward=1
    c.execute("INSERT INTO claims VALUES(?,?,?)",(oid,uid,now()))
    c.execute("UPDATE users SET coins=coins+?,total_views=total_views+1 WHERE id=?",(reward,uid))
    c.execute("UPDATE orders SET current=current+1 WHERE id=?",(oid,))
    cur=c.execute("SELECT current,target FROM orders WHERE id=?",(oid,)).fetchone()
    if cur["current"]>=cur["target"]: c.execute("UPDATE orders SET active=0 WHERE id=?",(oid,))
    c.commit(); c.close()
    await q.answer(f"{reward} سکه دریافت شد 🪙")
    try:
        await q.message.edit_reply_markup(reply_markup=q.message.reply_markup)
    except: pass

@dp.message(F.text=="ثبت تبلیغ ممبرگیر")
async def member_packages(m:Message):
    if not await guard(m): return
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind='member' ORDER BY cost").fetchall(); c.close()
    kb=[[KeyboardButton(text=f"{r['cost']} 💎 ← {r['target']} ممبر")] for r in rs]
    kb.append([KeyboardButton(text="🏠 بازگشت به منوی اصلی")])
    await m.answer("پکیج ممبرگیر:",reply_markup=ReplyKeyboardMarkup(keyboard=kb,resize_keyboard=True))

@dp.message(F.text.regexp(r"^\d+ 💎 ← \d+ ممبر$"))
async def member_pick(m:Message,state:FSMContext):
    cost=int(m.text.split()[0]); target=int(m.text.split("←")[1].split()[0])
    c=db(); r=c.execute("SELECT diamonds FROM users WHERE id=?",(m.from_user.id,)).fetchone(); c.close()
    if not r or r["diamonds"]<cost: await m.answer("موجودی الماس کافی نیست."); return
    await state.update_data(cost=cost,target=target); await state.set_state(Flow.member_link)
    await m.answer("لینک کانال یا گروه مقصد را ارسال کنید.\nسپس «ثبت لینک» را بزنید.",reply_markup=back_kb())

@dp.message(Flow.member_link)
async def receive_member(m:Message,state:FSMContext):
    if m.text=="🏠 بازگشت به منوی اصلی": return
    link=m.text.strip() if m.text else ""
    if not (link.startswith("https://t.me/") or link.startswith("http://t.me/")):
        await m.answer("لطفاً لینک معتبر تلگرام ارسال کنید."); return
    await state.update_data(link=link)
    await m.answer("لینک دریافت شد.",reply_markup=ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="ثبت لینک")],[KeyboardButton(text="🏠 بازگشت به منوی اصلی")]],resize_keyboard=True))

@dp.message(F.text=="ثبت لینک")
async def publish_member(m:Message,state:FSMContext):
    data=await state.get_data()
    if not data.get("link"): await m.answer("ابتدا لینک را بفرستید."); return
    c=db(); r=c.execute("SELECT diamonds FROM users WHERE id=?",(m.from_user.id,)).fetchone()
    if not r or r["diamonds"]<data["cost"]: c.close(); await m.answer("موجودی الماس کافی نیست."); return
    c.execute("UPDATE users SET diamonds=diamonds-? WHERE id=?",(data["cost"],m.from_user.id))
    c.execute("""INSERT INTO orders(kind,owner,cost,target,target_link,created_at)
                 VALUES('member',?,?,?,?,?)""",(m.from_user.id,data["cost"],data["target"],data["link"],now()))
    oid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.commit(); c.close()
    try:
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="جویین در کانال",url=data["link"])],
            [InlineKeyboardButton(text="دریافت الماس 💎",callback_data=f"mc:{oid}")],
            [InlineKeyboardButton(text="بازگشت به ربات",url=f"https://t.me/{(await bot.get_me()).username}")]])
        await bot.send_message(MEMBER_CHANNEL,f"📢 تبلیغ ممبرگیر\n\n{data['link']}",reply_markup=kb)
        await state.clear(); await m.answer("✅ تبلیغ ممبرگیر منتشر شد.",reply_markup=main_menu(m.from_user.id))
    except:
        c=db(); c.execute("UPDATE users SET diamonds=diamonds+? WHERE id=?",(data["cost"],m.from_user.id)); c.execute("DELETE FROM orders WHERE id=?",(oid,)); c.commit(); c.close()
        await m.answer("انتشار انجام نشد؛ ربات باید در کانال ممبرگیر ادمین باشد.")

@dp.callback_query(F.data.startswith("mc:"))
async def member_claim(q:CallbackQuery):
    oid=int(q.data.split(":")[1]); uid=q.from_user.id
    c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND active=1",(oid,)).fetchone()
    if not o: c.close(); await q.answer("سفارش فعال نیست.",show_alert=True); return
    if o["owner"]==uid: c.close(); await q.answer("صاحب سفارش نمی‌تواند پاداش بگیرد.",show_alert=True); return
    old=c.execute("SELECT 1 FROM claims WHERE order_id=? AND user_id=?",(oid,uid)).fetchone()
    if old: c.close(); await q.answer("قبلاً دریافت کرده‌اید.",show_alert=True); return
    link=o["target_link"]; username=link.rstrip("/").split("/")[-1]
    if username.startswith("+"):
        c.close(); await q.answer("لینک خصوصی قابل بررسی خودکار نیست؛ از لینک عمومی استفاده شود.",show_alert=True); return
    if username.startswith("@"): username=username[1:]
    try:
        member=await bot.get_chat_member(f"@{username}",uid)
        if member.status in ("left","kicked"):
            await q.answer("ابتدا وارد کانال/گروه شوید.",show_alert=True); c.close(); return
    except:
        await q.answer("بررسی عضویت انجام نشد؛ ربات باید در مقصد دسترسی لازم داشته باشد.",show_alert=True); c.close(); return
    reward=int(getset("member_reward","1"))
    c.execute("INSERT INTO claims VALUES(?,?,?)",(oid,uid,now()))
    c.execute("UPDATE users SET diamonds=diamonds+? WHERE id=?",(reward,uid))
    c.execute("UPDATE orders SET current=current+1 WHERE id=?",(oid,))
    cur=c.execute("SELECT current,target FROM orders WHERE id=?",(oid,)).fetchone()
    if cur["current"]>=cur["target"]: c.execute("UPDATE orders SET active=0 WHERE id=?",(oid,))
    c.commit(); c.close(); await q.answer(f"{reward} الماس دریافت شد 💎",show_alert=True)

@dp.message(F.text=="▪︎ فروشگاه")
async def shop(m:Message):
    if not await guard(m): return
    await m.answer("فروشگاه:",reply_markup=ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="خرید سکه ویوگیر"),KeyboardButton(text="خرید الماس ممبرگیر")],
        [KeyboardButton(text="🏠 بازگشت به منوی اصلی")]],resize_keyboard=True))

async def shop_list(m,kind,title):
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind=? ORDER BY cost",(kind,)).fetchall(); c.close()
    kb=[[InlineKeyboardButton(text=f"{r['cost']:,} → {r['price']:,} تومان",callback_data=f"buy:{kind}:{r['code']}")] for r in rs]
    await m.answer(title,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(F.text=="خرید سکه ویوگیر")
async def buycoins(m:Message):
    await shop_list(m,"coinshop","پکیج خرید سکه:")

@dp.message(F.text=="خرید الماس ممبرگیر")
async def buydiamonds(m:Message):
    await shop_list(m,"diamondshop","پکیج خرید الماس:")

@dp.callback_query(F.data.startswith("buy:"))
async def buy(q:CallbackQuery,state:FSMContext):
    _,kind,code=q.data.split(":")
    c=db(); r=c.execute("SELECT * FROM packages WHERE kind=? AND code=?",(kind,code)).fetchone(); c.close()
    if not r: await q.answer("پکیج پیدا نشد."); return
    await state.update_data(kind=kind,amount=r["cost"],price=r["price"])
    await state.set_state(Flow.receipt)
    await q.message.answer(f"مبلغ پرداخت: <b>{r['price']:,} تومان</b>\nشماره کارت: <code>{getset('card_number')}</code>\n\nپس از پرداخت، عکس رسید را ارسال کنید.",reply_markup=back_kb())
    await q.answer()

@dp.message(Flow.receipt,F.photo)
async def receipt(m:Message,state:FSMContext):
    data=await state.get_data()
    c=db(); c.execute("""INSERT INTO payments(user_id,kind,amount,price,status,receipt_chat,receipt_message,created_at)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (m.from_user.id,data["kind"],data["amount"],data["price"],"pending",m.chat.id,m.message_id,now()))
    pid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.commit(); c.close()
    try:
        await bot.send_photo(ADMIN_ID,m.photo[-1].file_id,caption=f"💳 پرداخت جدید #{pid}\nکاربر: {m.from_user.id}\nنوع: {data['kind']}\nمقدار: {data['amount']:,}\nمبلغ: {data['price']:,}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="تأیید",callback_data=f"payok:{pid}"),InlineKeyboardButton(text="رد",callback_data=f"payno:{pid}")]]))
    except: pass
    await state.clear(); await m.answer("رسید برای مدیریت ارسال شد. پس از تأیید، مبلغ خرید را مدیریت به‌صورت دستی به حساب شما اضافه می‌کند.",reply_markup=main_menu(m.from_user.id))

@dp.callback_query(F.data.startswith("payok:"))
async def payok(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(":")[1]); c=db(); p=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
    if not p or p["status"]!="pending": c.close(); await q.answer("قبلاً بررسی شده."); return
    c.execute("UPDATE payments SET status='approved' WHERE id=?",(pid,))
    lot=c.execute("SELECT id FROM lottery WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    if lot:
        rr=c.execute("SELECT tickets FROM ticket_rules WHERE price=?",(p["price"],)).fetchone()
        if rr:
            c.execute("INSERT INTO tickets(round_id,user_id,amount) VALUES(?,?,?) ON CONFLICT(round_id,user_id) DO UPDATE SET amount=amount+excluded.amount",(lot["id"],p["user_id"],rr["tickets"]))
    c.commit(); c.close()
    await bot.send_message(p["user_id"],"✅ پرداخت شما تأیید شد.\nتوجه: شارژ سکه/الماس طبق سیستم دستی توسط مدیریت انجام می‌شود.")
    await q.answer("تأیید شد.")

@dp.callback_query(F.data.startswith("payno:"))
async def payno(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(":")[1]); c=db(); p=c.execute("SELECT * FROM payments WHERE id=?",(pid,)).fetchone()
    if p: c.execute("UPDATE payments SET status='rejected' WHERE id=?",(pid,)); c.commit()
    c.close(); await bot.send_message(p["user_id"],"❌ رسید پرداخت شما رد شد."); await q.answer("رد شد.")

@dp.message(F.text=="▪︎ انتقال سکه")
async def transfer_coin(m:Message,state:FSMContext):
    await state.update_data(kind="coins"); await state.set_state(Flow.transfer_id)
    await m.answer("شناسه عددی گیرنده را ارسال کنید.",reply_markup=back_kb())

@dp.message(F.text=="▪︎ انتقال الماس")
async def transfer_diamond(m:Message,state:FSMContext):
    await state.update_data(kind="diamonds"); await state.set_state(Flow.transfer_id)
    await m.answer("شناسه عددی گیرنده را ارسال کنید.",reply_markup=back_kb())

@dp.message(Flow.transfer_id)
async def transfer_id(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit(): await m.answer("شناسه باید عددی باشد."); return
    await state.update_data(target=int(m.text)); await state.set_state(Flow.transfer_amount)
    await m.answer("مقدار را ارسال کنید.",reply_markup=back_kb())

@dp.message(Flow.transfer_amount)
async def transfer_amount(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit() or int(m.text)<=0: await m.answer("مقدار نامعتبر است."); return
    d=await state.get_data(); amount=int(m.text); uid=m.from_user.id
    c=db(); target=c.execute("SELECT id FROM users WHERE id=?",(d["target"],)).fetchone()
    if not target: c.close(); await m.answer("این کاربر در ربات ثبت نشده."); return
    if not is_admin(uid):
        r=c.execute(f"SELECT {d['kind']} FROM users WHERE id=?",(uid,)).fetchone()
        if not r or r[d["kind"]]<amount: c.close(); await m.answer("موجودی کافی نیست."); return
        c.execute(f"UPDATE users SET {d['kind']}={d['kind']}-? WHERE id=?",(amount,uid))
    c.execute(f"UPDATE users SET {d['kind']}={d['kind']}+? WHERE id=?",(amount,d["target"]))
    c.commit(); c.close(); await state.clear()
    await m.answer("✅ انتقال با موفقیت انجام شد.",reply_markup=main_menu(uid))

async def admin_panel(m):
    kb=ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="آمار"),KeyboardButton(text="لیست کاربران")],
        [KeyboardButton(text="تنظیم سکه روزانه"),KeyboardButton(text="تنظیم پاداش زیرمجموعه")],
        [KeyboardButton(text="تنظیم پاداش ممبر"),KeyboardButton(text="تنظیم شماره کارت")],
        [KeyboardButton(text="روشن/خاموش ربات"),KeyboardButton(text="تنظیم هدیه ماهانه")],
        [KeyboardButton(text="تنظیم جوایز قرعه کشی"),KeyboardButton(text="قرعه کشی جدید")],
        [KeyboardButton(text="تنظیم بلیت قرعه کشی"),KeyboardButton(text="اجرای قرعه کشی")],
        [KeyboardButton(text="افزودن ادمین"),KeyboardButton(text="🏠 بازگشت به منوی اصلی")]
    ],resize_keyboard=True)
    await m.answer("🛠 <b>پنل مدیریت</b>",reply_markup=kb)

@dp.message(F.text=="▪︎ پنل مدیریت")
async def admin_button(m:Message):
    if is_admin(m.from_user.id): await admin_panel(m)
    else: await m.answer("دسترسی ندارید.")

@dp.message(F.text=="آمار")
async def stats(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); u=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]; o=c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]; p=c.execute("SELECT COUNT(*) n FROM payments WHERE status='pending'").fetchone()["n"]; c.close()
    await m.answer(f"👥 کاربران: {u}\n📢 سفارش‌ها: {o}\n💳 پرداخت‌های در انتظار: {p}")

@dp.message(F.text=="تنظیم سکه روزانه")
async def set_daily(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    await state.update_data(setting="daily_coins"); await state.set_state(Flow.admin_value); await m.answer("مقدار جدید را عددی بفرستید.")

@dp.message(F.text=="تنظیم پاداش زیرمجموعه")
async def set_ref(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    await state.update_data(setting="referral_coins"); await state.set_state(Flow.admin_value); await m.answer("مقدار جدید را بفرستید.")

@dp.message(F.text=="تنظیم پاداش ممبر")
async def set_memreward(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    await state.update_data(setting="member_reward"); await state.set_state(Flow.admin_value); await m.answer("الماس هر عضویت را بفرستید.")

@dp.message(F.text=="تنظیم شماره کارت")
async def set_card(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    await state.update_data(setting="card_number"); await state.set_state(Flow.admin_value); await m.answer("شماره کارت جدید را بفرستید.")

@dp.message(F.text=="روشن/خاموش ربات")
async def toggle(m:Message):
    if is_admin(m.from_user.id):
        v="0" if getset("bot_enabled","1")=="1" else "1"; setset("bot_enabled",v)
        await m.answer("وضعیت ربات: "+("روشن ✅" if v=="1" else "خاموش ⛔"))

@dp.message(Flow.admin_value)
async def admin_value(m:Message,state:FSMContext):
    d=await state.get_data()
    if d.get("setting")=="card_number": setset("card_number",m.text.strip())
    else:
        if not m.text.isdigit(): await m.answer("فقط عدد بفرستید."); return
        setset(d["setting"],m.text)
    await state.clear(); await m.answer("✅ ذخیره شد.",reply_markup=main_menu(m.from_user.id))

@dp.message(F.text=="تنظیم هدیه ماهانه")
async def monthly(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    await state.update_data(setting="monthly_gift_amount"); await state.set_state(Flow.admin_value)
    await m.answer("مبلغ هدیه ماهانه را عددی بفرستید. برای غیرفعال کردن 0.")

@dp.message(F.text=="تنظیم جوایز قرعه کشی")
async def prizes(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute("SELECT * FROM prizes ORDER BY place").fetchall(); c.close()
    await m.answer("\n".join([f"{r['place']}️⃣ سکه: {r['coins']:,} | الماس: {r['diamonds']:,}" for r in rs])+
                    "\n\nبرای تغییر از دستورهای /setprize استفاده کنید.")

@dp.message(Command("setprize"))
async def setprize(m:Message):
    if not is_admin(m.from_user.id): return
    a=m.text.split()
    if len(a)!=4 or not all(x.isdigit() for x in a[1:]):
        await m.answer("فرمت: /setprize جایزه سکه الماس"); return
    place,coins,diamonds=map(int,a[1:])
    if place not in (1,2,3): await m.answer("جایزه باید 1 تا 3 باشد."); return
    c=db(); c.execute("UPDATE prizes SET coins=?,diamonds=? WHERE place=?",(coins,diamonds,place)); c.commit(); c.close(); await m.answer("ذخیره شد.")

@dp.message(F.text=="قرعه کشی جدید")
async def newlottery(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); c.execute("UPDATE lottery SET active=0"); c.execute("INSERT INTO lottery(active,round_no) VALUES(1,COALESCE((SELECT MAX(round_no)+1 FROM lottery),1))"); c.commit(); c.close()
    await m.answer("🎟 قرعه‌کشی جدید فعال شد. بلیت‌ها با پرداخت‌های تأییدشده ثبت می‌شوند.")

@dp.message(F.text=="تنظیم بلیت قرعه کشی")
async def ticketrules(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute("SELECT price,tickets FROM ticket_rules ORDER BY price").fetchall(); c.close()
    await m.answer("\n".join([f"{r['price']:,} تومان = {r['tickets']} بلیت" for r in rs])+
                    "\n\nتغییر: /setticket مبلغ تعداد")

@dp.message(Command("setticket"))
async def setticket(m:Message):
    if not is_admin(m.from_user.id): return
    a=m.text.split()
    if len(a)!=3 or not all(x.isdigit() for x in a[1:]): await m.answer("فرمت: /setticket مبلغ تعداد"); return
    c=db(); c.execute("INSERT INTO ticket_rules(price,tickets) VALUES(?,?)",(int(a[1]),int(a[2]))); c.commit(); c.close(); await m.answer("بلیت ذخیره شد.")

@dp.message(F.text=="اجرای قرعه کشی")
async def draw(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); lot=c.execute("SELECT * FROM lottery WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    if not lot: c.close(); await m.answer("قرعه‌کشی فعالی نیست."); return
    rs=c.execute("SELECT user_id,amount FROM tickets WHERE round_id=? AND amount>0",(lot["id"],)).fetchall()
    if not rs: c.close(); await m.answer("هیچ بلیتی ثبت نشده."); return
    pool=[]
    for r in rs: pool += [r["user_id"]]*r["amount"]
    winners=[]
    while pool and len(winners)<3:
        w=random.choice(pool); winners.append(w); pool=[x for x in pool if x!=w]
    prs=c.execute("SELECT * FROM prizes ORDER BY place").fetchall()
    for i,w in enumerate(winners,1):
        pr=next((x for x in prs if x["place"]==i),None)
        if pr:
            c.execute("UPDATE users SET coins=coins+?,diamonds=diamonds+?,prizes=prizes+1 WHERE id=?",(pr["coins"],pr["diamonds"],w))
    c.execute("UPDATE lottery SET active=0 WHERE id=?",(lot["id"],)); c.commit(); c.close()
    for i,w in enumerate(winners,1): await bot.send_message(w,f"🎉 شما برنده جایزه رتبه {i} قرعه‌کشی شدید!")
    await m.answer(f"قرعه‌کشی انجام شد. تعداد برندگان: {len(winners)}")

@dp.message(F.text=="لیست کاربران")
async def users(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute("SELECT id,name,coins,diamonds FROM users ORDER BY id DESC LIMIT 30").fetchall(); c.close()
    s="\n".join([f"{r['id']} | {r['name']} | 🪙{r['coins']:,} | 💎{r['diamonds']:,}" for r in rs]) or "کاربری نیست."
    await m.answer(s)

@dp.message(Command("gift"))
async def gift(m:Message):
    if not is_admin(m.from_user.id): return
    a=m.text.split()
    if len(a)!=3 or not a[1].isdigit() or not a[2].isdigit(): await m.answer("فرمت: /gift شناسه مبلغ"); return
    uid,amount=int(a[1]),int(a[2]); c=db(); c.execute("UPDATE users SET coins=coins+?,gift=gift+? WHERE id=?",(amount,amount,uid)); c.commit(); c.close(); await m.answer("هدیه ثبت شد.")

async def monthly_gift_task():
    while True:
        try:
            month=datetime.now(timezone.utc).strftime("%Y-%m")
            if getset("last_gift_month","")!=month:
                amount=int(getset("monthly_gift_amount","0"))
                if amount>0:
                    c=db()
                    winner=c.execute("SELECT id FROM users ORDER BY total_views DESC LIMIT 1").fetchone()
                    if winner:
                        typ=getset("monthly_gift_type","coins")
                        if typ=="diamonds": c.execute("UPDATE users SET diamonds=diamonds+?,gift=gift+? WHERE id=?",(amount,amount,winner["id"]))
                        else: c.execute("UPDATE users SET coins=coins+?,gift=gift+? WHERE id=?",(amount,amount,winner["id"]))
                        c.commit()
                setset("last_gift_month",month)
        except Exception:
            pass
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app):
    init_db()
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL.rstrip("/")+"/telegram/webhook")
    task=asyncio.create_task(monthly_gift_task())
    yield
    task.cancel()
    await bot.delete_webhook()
    await bot.session.close()

app=FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status":"ok","bot":"ViewCoin"}

@app.post("/telegram/webhook")
async def webhook(request:Request):
    data=await request.json()
    await dp.feed_raw_update(bot,data)
    return {"ok":True}
