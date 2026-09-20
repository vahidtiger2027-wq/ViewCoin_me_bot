import os, sqlite3, asyncio, random, re
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN=os.getenv('BOT_TOKEN','').strip(); ADMIN_ID=int(os.getenv('ADMIN_ID','0') or 0)
WEBHOOK_URL=os.getenv('WEBHOOK_URL','').strip(); VIEW_CHANNEL=os.getenv('VIEW_CHANNEL','@view_sin_channel').strip(); MEMBER_CHANNEL=os.getenv('MEMBER_CHANNEL','@my_member_man').strip(); DB_NAME=os.getenv('DB_NAME','viewcoin.db')
if not BOT_TOKEN: raise RuntimeError('BOT_TOKEN is not set')
bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML)); dp=Dispatcher(storage=MemoryStorage())

def db():
    c=sqlite3.connect(DB_NAME); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone.utc).date().isoformat()
def getset(k,d=''):
    c=db(); r=c.execute('SELECT v FROM settings WHERE k=?',(k,)).fetchone(); c.close(); return r['v'] if r else d
def setset(k,v):
    c=db(); c.execute('INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)',(k,str(v))); c.commit(); c.close()
def is_admin(uid):
    c=db(); r=c.execute('SELECT 1 FROM admins WHERE id=?',(uid,)).fetchone(); c.close(); return bool(r)

def init_db():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT,name TEXT,coins INTEGER DEFAULT 0,diamonds INTEGER DEFAULT 0,gift INTEGER DEFAULT 0,total_views INTEGER DEFAULT 0,today_views INTEGER DEFAULT 0,last_view_day TEXT,referral_count INTEGER DEFAULT 0,referral_income INTEGER DEFAULT 0,prizes INTEGER DEFAULT 0,referred_by INTEGER,created_at TEXT);
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);
    CREATE TABLE IF NOT EXISTS packages(kind TEXT,code TEXT PRIMARY KEY,cost INTEGER,target INTEGER,price INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,owner INTEGER,cost INTEGER,target INTEGER,current INTEGER DEFAULT 0,source_chat TEXT,source_message INTEGER,target_link TEXT,active INTEGER DEFAULT 1,created_at TEXT);
    CREATE TABLE IF NOT EXISTS claims(order_id INTEGER,user_id INTEGER,created_at TEXT,PRIMARY KEY(order_id,user_id));
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,amount INTEGER,price INTEGER,status TEXT DEFAULT 'pending',receipt_chat INTEGER,receipt_message INTEGER,created_at TEXT);
    CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY,can_settings INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS ticket_rules(id INTEGER PRIMARY KEY AUTOINCREMENT,price INTEGER,tickets INTEGER);
    CREATE TABLE IF NOT EXISTS lottery(id INTEGER PRIMARY KEY AUTOINCREMENT,active INTEGER DEFAULT 0,draw_at TEXT,round_no INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS prizes(place INTEGER PRIMARY KEY,coins INTEGER DEFAULT 0,diamonds INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS tickets(round_id INTEGER,user_id INTEGER,amount INTEGER DEFAULT 0,PRIMARY KEY(round_id,user_id));
    CREATE TABLE IF NOT EXISTS mandatory_channels(id INTEGER PRIMARY KEY AUTOINCREMENT,link TEXT UNIQUE,title TEXT,enabled INTEGER DEFAULT 1);
    ''')
    defaults={'bot_enabled':'1','daily_coins':'10','referral_coins':'200','view_reward':'1','member_reward':'1','card_number':'145679965776','gateway_url':'','shop_enabled':'1','lottery_enabled':'1','lottery_period':'weekly','lottery_next':'','mandatory_enabled':'1','monthly_gift_amount':'0','monthly_gift_type':'coins','last_gift_month':''}
    for k,v in defaults.items(): c.execute('INSERT OR IGNORE INTO settings(k,v) VALUES(?,?)',(k,v))
    views=[('v40',40,40),('v50',50,50),('v100',100,100),('v200',200,200)]; members=[('m20',20,10),('m40',40,20),('m60',60,30),('m80',80,40),('m100',100,50)]
    coins=[('c20000',20000,0,50000),('c40000',40000,0,100000),('c50000',50000,0,150000),('c200000',200000,0,200000)]
    diamonds=[('d100',100,0,25000),('d250',250,0,50000),('d500',500,0,100000),('d1000',1000,0,200000),('d4000',4000,0,800000)]
    for x in views: c.execute('INSERT OR IGNORE INTO packages VALUES(?,?,?,?,0)',('view',*x))
    for x in members: c.execute('INSERT OR IGNORE INTO packages VALUES(?,?,?,?,0)',('member',*x))
    for x in coins: c.execute('INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)',('coinshop',*x))
    for x in diamonds: c.execute('INSERT OR IGNORE INTO packages VALUES(?,?,?,?,?)',('diamondshop',*x))
    for price,t in [(50000,2),(100000,4),(200000,6),(500000,10)]: c.execute('INSERT OR IGNORE INTO ticket_rules(price,tickets) VALUES(?,?)',(price,t))
    for p in (1,2,3): c.execute('INSERT OR IGNORE INTO prizes(place,coins,diamonds) VALUES(?,?,?)',(p,0,0))
    c.execute('INSERT OR IGNORE INTO admins(id,can_settings) VALUES(?,1)',(ADMIN_ID,))
    defaults_channels=[('@my_member_man','کانال ممبر گیر سونیک'),('@view_sin_channel','کانال ویوگیر سونیک')]
    for link,title in defaults_channels: c.execute('INSERT OR IGNORE INTO mandatory_channels(link,title,enabled) VALUES(?,?,1)',(link,title))
    c.commit(); c.close()

def ensure_user(u,ref=None):
    c=db(); r=c.execute('SELECT * FROM users WHERE id=?',(u.id,)).fetchone()
    if not r:
        c.execute('INSERT INTO users(id,username,name,coins,diamonds,referred_by,created_at) VALUES(?,?,?,?,?,?,?)',(u.id,u.username,u.full_name,0,0,ref,now()))
        if ref and ref!=u.id and c.execute('SELECT id FROM users WHERE id=?',(ref,)).fetchone():
            reward=int(getset('referral_coins','200')); c.execute('UPDATE users SET coins=coins+?,referral_count=referral_count+1,referral_income=referral_income+? WHERE id=?',(reward,reward,ref))
    else: c.execute('UPDATE users SET username=?,name=? WHERE id=?',(u.username,u.full_name,u.id))
    c.commit(); c.close()

def main_menu(uid):
    rows=[[KeyboardButton(text='▪︎ جمع‌آوری سکه رایگان'),KeyboardButton(text='▪︎ حساب کاربری')],[KeyboardButton(text='▪︎ جذب زیر مجموعه'),KeyboardButton(text='▪︎ ثبت تبلیغ ویو گیر و ممبر گیر')],[KeyboardButton(text='▪︎ فروشگاه'),KeyboardButton(text='▪︎ انتقال سکه')],[KeyboardButton(text='▪︎ انتقال الماس'),KeyboardButton(text='▪︎ قرعه کشی')]]
    if is_admin(uid): rows.append([KeyboardButton(text='▪︎ پنل مدیریت')])
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True)
def back_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True)
async def guard(m):
    if is_admin(m.from_user.id): return True
    if getset('bot_enabled','1')!='1': await m.answer('ربات موقتاً توسط مدیریت خاموش است.'); return False
    return True

class Flow(StatesGroup):
    view_post=State(); member_link=State(); transfer_id=State(); transfer_amount=State(); receipt=State(); admin_value=State(); mandatory_add=State(); package_edit=State(); prize_value=State(); period_date=State()

async def required_channels():
    c=db(); rs=c.execute('SELECT * FROM mandatory_channels WHERE enabled=1 ORDER BY id').fetchall(); c.close(); return rs[:10]
async def membership_keyboard():
    rows=[]
    for r in await required_channels():
        link=r['link']; url=link if link.startswith('http') else 'https://t.me/'+link.lstrip('@')
        rows.append([InlineKeyboardButton(text='📢 '+(r['title'] or link),url=url)])
    rows.append([InlineKeyboardButton(text='✅ بررسی عضویت',callback_data='check_membership')]); return InlineKeyboardMarkup(inline_keyboard=rows)
async def check_required_membership(uid):
    if is_admin(uid) or getset('mandatory_enabled','1')!='1': return True
    for r in await required_channels():
        link=r['link'].strip(); chat=link
        if link.startswith('https://t.me/'): chat='@'+link.rstrip('/').split('/')[-1]
        elif link.startswith('http://t.me/'): chat='@'+link.rstrip('/').split('/')[-1]
        if not str(chat).startswith('@') and not str(chat).lstrip('-').isdigit(): return False
        try:
            member=await bot.get_chat_member(chat,uid)
            if member.status in ('left','kicked'): return False
        except Exception: return False
    return True

@dp.callback_query(F.data=='check_membership')
async def check_membership(q:CallbackQuery):
    if await check_required_membership(q.from_user.id):
        ensure_user(q.from_user); await q.message.answer('✅ عضویت شما تأیید شد. خوش آمدید 🌹',reply_markup=main_menu(q.from_user.id)); await q.answer('عضویت تأیید شد ✅')
    else: await q.answer('هنوز در کانال‌های اجباری عضو نشده‌اید.',show_alert=True)

@dp.message(CommandStart())
async def start(m:Message):
    arg=m.text.split(maxsplit=1)[1] if len(m.text.split())>1 else ''; ref=int(arg) if arg.isdigit() else None; ensure_user(m.from_user,ref)
    if not await check_required_membership(m.from_user.id):
        await m.answer('سلام به ربات ممبرگیر و ویوگیر سونیک خوشامدید 🌹\nبرای استارت ربات در کانال های ما عضو شوید\n\n📢 @my_member_man  کانال ممبر گیر سونیک\n📢 @view_sin_channel  کانال ویوگیر سونیک\n\nبرای ادامه کار با ربات، لطفاً در کانال‌های زیر عضو شوید.',reply_markup=await membership_keyboard()); return
    if not await guard(m): return
    await m.answer('سلام به ربات ممبرگیر و ویوگیر سونیک خوشامدید 🌹\nاز منوی زیر شروع کنید 👇',reply_markup=main_menu(m.from_user.id))

@dp.message(Command('admin'))
async def admin_cmd(m:Message):
    ensure_user(m.from_user)
    if is_admin(m.from_user.id): await admin_panel(m)
    else: await m.answer('دسترسی ندارید.')

@dp.message(F.text=='🏠 بازگشت به منوی اصلی')
async def back(m:Message,state:FSMContext): await state.clear(); await m.answer('منوی اصلی',reply_markup=main_menu(m.from_user.id))

@dp.message(F.text.contains('جمع‌آوری سکه رایگان'))
async def daily(m:Message):
    ensure_user(m.from_user)
    if not await guard(m): return
    c=db(); r=c.execute('SELECT * FROM users WHERE id=?',(m.from_user.id,)).fetchone()
    if r['last_view_day']==today(): c.close(); await m.answer('سکه روزانه امروز را قبلاً دریافت کرده‌اید.',reply_markup=main_menu(m.from_user.id)); return
    amount=int(getset('daily_coins','10')); c.execute('UPDATE users SET coins=coins+?,last_view_day=? WHERE id=?',(amount,today(),m.from_user.id)); c.commit(); c.close(); await m.answer(f'🎁 {amount} سکه رایگان دریافت کردید.',reply_markup=main_menu(m.from_user.id))

@dp.message(F.text.contains('حساب کاربری'))
async def account(m:Message):
    ensure_user(m.from_user)
    if not await guard(m): return
    c=db(); r=c.execute('SELECT * FROM users WHERE id=?',(m.from_user.id,)).fetchone(); c.close(); bal='9,999,999' if is_admin(m.from_user.id) else f"{r['coins']:,}"; dia='9,999,999' if is_admin(m.from_user.id) else f"{r['diamonds']:,}"
    s=f"👤 <b>حساب کاربری</b>\n\nنام: {r['name']}\n"+(f"یوزرنیم: @{r['username']}\n" if r['username'] else '')+f"شناسه تلگرام: <code>{r['id']}</code>\n🎁 هدیه مدیریت: {r['gift']:,}\n👁 بازدیدهای شما: {r['total_views']:,}\n📅 بازدیدهای امروز: {r['today_views']:,}\n🏆 جوایز: {r['prizes']:,}\n👥 تعداد زیرمجموعه‌ها: {r['referral_count']:,}\n💰 دریافتی: {r['referral_income']:,}\n🪙 موجودی سکه شما: {bal}\n💎 موجودی الماس شما: {dia}"
    await m.answer(s,reply_markup=back_kb())

@dp.message(F.text.contains('جذب زیر مجموعه'))
async def referral(m:Message):
    ensure_user(m.from_user)
    if not await guard(m): return
    me=await bot.get_me(); link=f'https://t.me/{me.username}?start={m.from_user.id}'
    await m.answer(f"👥 <b>زیرمجموعه‌گیری</b>\n\n🪙 پاداش هر بازدید: {getset('view_reward','1')} سکه\n👥 پاداش زیرمجموعه: {getset('referral_coins','200')} سکه\n🎁 سکه روزانه: {getset('daily_coins','10')}\n💎 پاداش ممبر: {getset('member_reward','1')} الماس\n\nلینک اختصاصی شما:\n<code>{link}</code>",reply_markup=back_kb())

@dp.message(F.text.contains('ثبت تبلیغ ویو گیر و ممبر گیر'))
async def ad_menu(m:Message):
    if not await guard(m): return
    await m.answer('نوع تبلیغ را انتخاب کنید:',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='ثبت تبلیغ ویوگیر'),KeyboardButton(text='ثبت تبلیغ ممبرگیر')],[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True))

@dp.message(F.text=='ثبت تبلیغ ویوگیر')
async def view_packages(m:Message):
    if not await guard(m): return
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind='view' ORDER BY cost").fetchall(); c.close(); kb=[[KeyboardButton(text=f"{r['cost']} 🪙 ← {r['target']} بازدید")] for r in rs]; kb.append([KeyboardButton(text='🏠 بازگشت به منوی اصلی')]); await m.answer('پکیج ویوگیر:',reply_markup=ReplyKeyboardMarkup(keyboard=kb,resize_keyboard=True))

@dp.message(F.text.regexp(r'^\d+ 🪙 ← \d+ بازدید$'))
async def view_pick(m:Message,state:FSMContext):
    cost=int(m.text.split()[0]); target=int(m.text.split('←')[1].split()[0]); c=db(); r=c.execute('SELECT coins FROM users WHERE id=?',(m.from_user.id,)).fetchone(); c.close()
    if not r or r['coins']<cost: await m.answer('موجودی سکه کافی نیست.'); return
    await state.update_data(cost=cost,target=target); await state.set_state(Flow.view_post); await m.answer('پست تبلیغاتی خود را ارسال کنید. متن، لینک، عکس و ویدئو قابل قبول است. سپس «ثبت پست» را بزنید.',reply_markup=back_kb())

@dp.message(Flow.view_post)
async def receive_view(m:Message,state:FSMContext):
    await state.update_data(source_chat=str(m.chat.id),source_message=m.message_id); await m.answer('پست دریافت شد. برای انتشار روی «ثبت پست» بزنید.',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='ثبت پست')],[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True))

@dp.message(F.text=='ثبت پست')
async def publish_view(m:Message,state:FSMContext):
    d=await state.get_data()
    if not d.get('source_message'): await m.answer('ابتدا پست را ارسال کنید.'); return
    c=db(); r=c.execute('SELECT coins FROM users WHERE id=?',(m.from_user.id,)).fetchone()
    if not r or r['coins']<d['cost']: c.close(); await m.answer('موجودی کافی نیست.'); return
    c.execute('UPDATE users SET coins=coins-? WHERE id=?',(d['cost'],m.from_user.id)); c.execute("INSERT INTO orders(kind,owner,cost,target,source_chat,source_message,created_at) VALUES('view',?,?,?,?,?,?)",(m.from_user.id,d['cost'],d['target'],d['source_chat'],d['source_message'],now())); oid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; c.commit(); c.close()
    try:
        sent=await bot.copy_message(VIEW_CHANNEL,int(d['source_chat']),d['source_message']); me=await bot.get_me(); kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ثبت بازدید 🪙',callback_data=f'vc:{oid}'),InlineKeyboardButton(text='ورود به ربات 🤖',url=f'https://t.me/{me.username}')]])
        await bot.edit_message_reply_markup(VIEW_CHANNEL,sent.message_id,reply_markup=kb); c=db(); c.execute('UPDATE orders SET source_chat=?,source_message=? WHERE id=?',(VIEW_CHANNEL,sent.message_id,oid)); c.commit(); c.close(); await state.clear(); await m.answer('✅ پست با موفقیت در کانال ویوگیر منتشر شد.',reply_markup=main_menu(m.from_user.id))
    except Exception: c=db(); c.execute('UPDATE users SET coins=coins+? WHERE id=?',(d['cost'],m.from_user.id)); c.execute('DELETE FROM orders WHERE id=?',(oid,)); c.commit(); c.close(); await m.answer('انتشار پست انجام نشد؛ ربات باید در کانال ویوگیر ادمین باشد.')

@dp.callback_query(F.data.startswith('vc:'))
async def view_claim(q:CallbackQuery):
    oid=int(q.data.split(':')[1]); uid=q.from_user.id; ensure_user(q.from_user); c=db(); o=c.execute('SELECT * FROM orders WHERE id=? AND active=1',(oid,)).fetchone()
    if not o: c.close(); await q.answer('این سفارش فعال نیست.',show_alert=True); return
    if o['owner']==uid: c.close(); await q.answer('صاحب تبلیغ نمی‌تواند برای سفارش خودش پاداش بگیرد.',show_alert=True); return
    if c.execute('SELECT 1 FROM claims WHERE order_id=? AND user_id=?',(oid,uid)).fetchone(): c.close(); await q.answer('قبلاً پاداش این سفارش را گرفته‌اید.',show_alert=True); return
    reward=int(getset('view_reward','1')); c.execute('INSERT INTO claims VALUES(?,?,?)',(oid,uid,now())); c.execute('UPDATE users SET coins=coins+?,total_views=total_views+1,today_views=CASE WHEN last_view_day=? THEN today_views+1 ELSE 1 END,last_view_day=? WHERE id=?',(reward,today(),today(),uid)); c.execute('UPDATE orders SET current=current+1 WHERE id=?',(oid,)); cur=c.execute('SELECT current,target,source_chat,source_message FROM orders WHERE id=?',(oid,)).fetchone(); done=cur['current']>=cur['target'];
    if done: c.execute('UPDATE orders SET active=0 WHERE id=?',(oid,))
    c.commit(); c.close(); await q.answer(f'{reward} سکه دریافت شد 🪙',show_alert=True)
    if done:
        try: await bot.delete_message(cur['source_chat'],cur['source_message'])
        except Exception: pass

@dp.message(F.text=='ثبت تبلیغ ممبرگیر')
async def member_packages(m:Message):
    if not await guard(m): return
    c=db(); rs=c.execute("SELECT * FROM packages WHERE kind='member' ORDER BY cost").fetchall(); c.close(); kb=[[KeyboardButton(text=f"{r['cost']} 💎 ← {r['target']} ممبر")] for r in rs]; kb.append([KeyboardButton(text='🏠 بازگشت به منوی اصلی')]); await m.answer('پکیج ممبرگیر:',reply_markup=ReplyKeyboardMarkup(keyboard=kb,resize_keyboard=True))

@dp.message(F.text.regexp(r'^\d+ 💎 ← \d+ ممبر$'))
async def member_pick(m:Message,state:FSMContext):
    cost=int(m.text.split()[0]); target=int(m.text.split('←')[1].split()[0]); c=db(); r=c.execute('SELECT diamonds FROM users WHERE id=?',(m.from_user.id,)).fetchone(); c.close()
    if not r or r['diamonds']<cost: await m.answer('موجودی الماس کافی نیست.'); return
    await state.update_data(cost=cost,target=target); await state.set_state(Flow.member_link); await m.answer('لینک کانال یا گروه مقصد را ارسال کنید. سپس «ثبت لینک» را بزنید.',reply_markup=back_kb())

@dp.message(Flow.member_link)
async def receive_member(m:Message,state:FSMContext):
    link=(m.text or '').strip()
    if not re.match(r'^https?://t\.me/[^\s]+$',link): await m.answer('لطفاً لینک معتبر تلگرام مثل https://t.me/channel ارسال کنید.'); return
    await state.update_data(link=link); await m.answer('لینک دریافت شد.',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='ثبت لینک')],[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True))

@dp.message(F.text=='ثبت لینک')
async def publish_member(m:Message,state:FSMContext):
    d=await state.get_data()
    if not d.get('link'): await m.answer('ابتدا لینک را بفرستید.'); return
    c=db(); r=c.execute('SELECT diamonds FROM users WHERE id=?',(m.from_user.id,)).fetchone()
    if not r or r['diamonds']<d['cost']: c.close(); await m.answer('موجودی الماس کافی نیست.'); return
    c.execute('UPDATE users SET diamonds=diamonds-? WHERE id=?',(d['cost'],m.from_user.id)); c.execute("INSERT INTO orders(kind,owner,cost,target,target_link,created_at) VALUES('member',?,?,?,?,?)",(m.from_user.id,d['cost'],d['target'],d['link'],now())); oid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; c.commit(); c.close()
    try:
        me=await bot.get_me(); kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='جویین در کانال',url=d['link'])],[InlineKeyboardButton(text='دریافت الماس 💎',callback_data=f'mc:{oid}')],[InlineKeyboardButton(text='بازگشت به ربات',url=f'https://t.me/{me.username}')]])
        sent=await bot.send_message(MEMBER_CHANNEL,f"📢 تبلیغ ممبرگیر\n\n{d['link']}",reply_markup=kb); c=db(); c.execute('UPDATE orders SET source_chat=?,source_message=? WHERE id=?',(MEMBER_CHANNEL,sent.message_id,oid)); c.commit(); c.close(); await state.clear(); await m.answer('✅ تبلیغ ممبرگیر منتشر شد.',reply_markup=main_menu(m.from_user.id))
    except Exception: c=db(); c.execute('UPDATE users SET diamonds=diamonds+? WHERE id=?',(d['cost'],m.from_user.id)); c.execute('DELETE FROM orders WHERE id=?',(oid,)); c.commit(); c.close(); await m.answer('انتشار انجام نشد؛ ربات باید در کانال ممبرگیر دسترسی ارسال پیام داشته باشد.')

def target_chat_from_link(link):
    p=urlparse(link); path=p.path.strip('/').split('/'); return '@'+path[0] if path and path[0] and not path[0].startswith('+') else None

@dp.callback_query(F.data.startswith('mc:'))
async def member_claim(q:CallbackQuery):
    oid=int(q.data.split(':')[1]); uid=q.from_user.id; c=db(); o=c.execute('SELECT * FROM orders WHERE id=? AND active=1',(oid,)).fetchone()
    if not o: c.close(); await q.answer('سفارش فعال نیست.',show_alert=True); return
    if o['owner']==uid: c.close(); await q.answer('صاحب سفارش نمی‌تواند پاداش بگیرد.',show_alert=True); return
    if c.execute('SELECT 1 FROM claims WHERE order_id=? AND user_id=?',(oid,uid)).fetchone(): c.close(); await q.answer('قبلاً دریافت کرده‌اید.',show_alert=True); return
    chat=target_chat_from_link(o['target_link'])
    if not chat: c.close(); await q.answer('لینک خصوصی قابل بررسی خودکار نیست؛ لینک عمومی استفاده کنید.',show_alert=True); return
    try:
        member=await bot.get_chat_member(chat,uid)
        if member.status in ('left','kicked'): c.close(); await q.answer('ابتدا وارد کانال/گروه شوید.',show_alert=True); return
    except Exception: c.close(); await q.answer('بررسی عضویت انجام نشد؛ ربات باید در مقصد دسترسی لازم را داشته باشد.',show_alert=True); return
    reward=int(getset('member_reward','1')); c.execute('INSERT INTO claims VALUES(?,?,?)',(oid,uid,now())); c.execute('UPDATE users SET diamonds=diamonds+? WHERE id=?',(reward,uid)); c.execute('UPDATE orders SET current=current+1 WHERE id=?',(oid,)); cur=c.execute('SELECT current,target,source_chat,source_message FROM orders WHERE id=?',(oid,)).fetchone(); done=cur['current']>=cur['target'];
    if done: c.execute('UPDATE orders SET active=0 WHERE id=?',(oid,))
    c.commit(); c.close(); await q.answer(f'{reward} الماس دریافت شد 💎',show_alert=True)
    if done:
        try: await bot.delete_message(cur['source_chat'],cur['source_message'])
        except Exception: pass

@dp.message(F.text.contains('فروشگاه'))
async def shop(m:Message):
    if not await guard(m): return
    if getset('shop_enabled','1')!='1': await m.answer('فروشگاه موقتاً خاموش است.',reply_markup=back_kb()); return
    await m.answer('فروشگاه:',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='خرید سکه ویوگیر'),KeyboardButton(text='خرید الماس ممبرگیر')],[KeyboardButton(text='🏠 بازگشت به منوی اصلی')]],resize_keyboard=True))
async def shop_list(m,kind,title):
    c=db(); rs=c.execute('SELECT * FROM packages WHERE kind=? ORDER BY cost',(kind,)).fetchall(); c.close(); await m.answer(title+'\n\n'+('\n'.join(f"{r['cost']:,} = {r['price']:,} تومان" for r in rs)),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{r['cost']:,} → {r['price']:,} تومان",callback_data=f'buy:{kind}:{r["code"]}')] for r in rs]))
@dp.message(F.text=='خرید سکه ویوگیر')
async def buycoins(m:Message): await shop_list(m,'coinshop','پکیج خرید سکه:')
@dp.message(F.text=='خرید الماس ممبرگیر')
async def buydiamonds(m:Message): await shop_list(m,'diamondshop','پکیج خرید الماس:')
@dp.callback_query(F.data.startswith('buy:'))
async def buy(q:CallbackQuery,state:FSMContext):
    _,kind,code=q.data.split(':'); c=db(); r=c.execute('SELECT * FROM packages WHERE kind=? AND code=?',(kind,code)).fetchone(); c.close()
    if not r: await q.answer('پکیج پیدا نشد.'); return
    await state.update_data(kind=kind,amount=r['cost'],price=r['price']); await state.set_state(Flow.receipt)
    gateway=getset('gateway_url','').strip(); txt=f"مبلغ پرداخت: <b>{r['price']:,} تومان</b>\nشماره کارت: <code>{getset('card_number')}</code>"
    if gateway: txt+=f"\nلینک درگاه: {gateway}"
    txt+='\n\nپس از پرداخت، عکس رسید را ارسال کنید.'; await q.message.answer(txt,reply_markup=back_kb()); await q.answer()
@dp.message(Flow.receipt,F.photo)
async def receipt(m:Message,state:FSMContext):
    d=await state.get_data(); c=db(); c.execute('INSERT INTO payments(user_id,kind,amount,price,status,receipt_chat,receipt_message,created_at) VALUES(?,?,?,?,?,?,?,?)',(m.from_user.id,d['kind'],d['amount'],d['price'],'pending',m.chat.id,m.message_id,now())); pid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; c.commit(); c.close()
    try: await bot.send_photo(ADMIN_ID,m.photo[-1].file_id,caption=f"💳 پرداخت جدید #{pid}\nکاربر: {m.from_user.id}\nنوع: {d['kind']}\nمقدار: {d['amount']:,}\nمبلغ: {d['price']:,}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='تأیید',callback_data=f'payok:{pid}'),InlineKeyboardButton(text='رد',callback_data=f'payno:{pid}')]]))
    except Exception: pass
    await state.clear(); await m.answer('رسید برای مدیریت ارسال شد. پس از تأیید، شارژ توسط مدیریت به‌صورت دستی انجام می‌شود.',reply_markup=main_menu(m.from_user.id))
@dp.callback_query(F.data.startswith('payok:'))
async def payok(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(':')[1]); c=db(); p=c.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
    if not p or p['status']!='pending': c.close(); await q.answer('قبلاً بررسی شده.'); return
    c.execute("UPDATE payments SET status='approved' WHERE id=?",(pid,)); lot=c.execute('SELECT id FROM lottery WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone(); rr=c.execute('SELECT tickets FROM ticket_rules WHERE price=?',(p['price'],)).fetchone() if lot else None
    if lot and rr: c.execute('INSERT INTO tickets(round_id,user_id,amount) VALUES(?,?,?) ON CONFLICT(round_id,user_id) DO UPDATE SET amount=amount+excluded.amount',(lot['id'],p['user_id'],rr['tickets']))
    c.commit(); c.close(); await bot.send_message(p['user_id'],'✅ پرداخت شما تأیید شد. شارژ سکه/الماس توسط مدیریت انجام می‌شود.'); await q.answer('تأیید شد.')
@dp.callback_query(F.data.startswith('payno:'))
async def payno(q:CallbackQuery):
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(':')[1]); c=db(); p=c.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone();
    if p: c.execute("UPDATE payments SET status='rejected' WHERE id=?",(pid,)); c.commit()
    c.close();
    if p: await bot.send_message(p['user_id'],'❌ رسید پرداخت شما رد شد.')
    await q.answer('رد شد.')

@dp.message(F.text.contains('انتقال سکه'))
async def transfer_coin(m:Message,state:FSMContext): await state.update_data(kind='coins'); await state.set_state(Flow.transfer_id); await m.answer('شناسه عددی گیرنده را ارسال کنید.',reply_markup=back_kb())
@dp.message(F.text.contains('انتقال الماس'))
async def transfer_diamond(m:Message,state:FSMContext): await state.update_data(kind='diamonds'); await state.set_state(Flow.transfer_id); await m.answer('شناسه عددی گیرنده را ارسال کنید.',reply_markup=back_kb())
@dp.message(Flow.transfer_id)
async def transfer_id(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit(): await m.answer('شناسه باید عددی باشد.'); return
    await state.update_data(target=int(m.text)); await state.set_state(Flow.transfer_amount); await m.answer('مقدار را ارسال کنید.',reply_markup=back_kb())
@dp.message(Flow.transfer_amount)
async def transfer_amount(m:Message,state:FSMContext):
    if not m.text or not m.text.isdigit() or int(m.text)<=0: await m.answer('مقدار نامعتبر است.'); return
    d=await state.get_data(); amount=int(m.text); uid=m.from_user.id; c=db(); target=c.execute('SELECT id FROM users WHERE id=?',(d['target'],)).fetchone()
    if not target: c.close(); await m.answer('این کاربر در ربات ثبت نشده.'); return
    if not is_admin(uid):
        r=c.execute(f"SELECT {d['kind']} FROM users WHERE id=?",(uid,)).fetchone()
        if not r or r[d['kind']]<amount: c.close(); await m.answer('موجودی کافی نیست.'); return
        c.execute(f"UPDATE users SET {d['kind']}={d['kind']}-? WHERE id=?",(amount,uid))
    c.execute(f"UPDATE users SET {d['kind']}={d['kind']}+? WHERE id=?",(amount,d['target'])); c.commit(); c.close(); await state.clear(); await m.answer('✅ انتقال با موفقیت انجام شد.',reply_markup=main_menu(uid))

async def admin_panel(m):
    kb=[[KeyboardButton(text='آمار'),KeyboardButton(text='لیست کاربران')],[KeyboardButton(text='تنظیم سکه روزانه'),KeyboardButton(text='تنظیم پاداش زیرمجموعه')],[KeyboardButton(text='تنظیمات مقدار سکه دریافتی از کانال ویوو گیر'),KeyboardButton(text='تنظیمات مقدار الماس دریافتی کانال ممبر')],[KeyboardButton(text='تنظیم سفارش ویو گیر'),KeyboardButton(text='تنظیم سفارشات ممبرگیر')],[KeyboardButton(text='تنظیمات فروشگاه'),KeyboardButton(text='تنظیم لینک‌های جویین اجباری')],[KeyboardButton(text='تنظیمات قرعه کشی'),KeyboardButton(text='روشن/خاموش ربات'),KeyboardButton(text='تنظیم هدیه ماهانه')],[KeyboardButton(text='افزودن ادمین'),KeyboardButton(text='🏠 بازگشت به منوی اصلی')]]
    await m.answer('🛠 <b>پنل مدیریت</b>',reply_markup=ReplyKeyboardMarkup(keyboard=kb,resize_keyboard=True))
@dp.message(F.text.contains('پنل مدیریت'))
async def admin_button(m:Message):
    if is_admin(m.from_user.id): await admin_panel(m)
    else: await m.answer('دسترسی ندارید.')
@dp.message(F.text=='آمار')
async def stats(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); u=c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']; o=c.execute('SELECT COUNT(*) n FROM orders').fetchone()['n']; p=c.execute("SELECT COUNT(*) n FROM payments WHERE status='pending'").fetchone()['n']; c.close(); await m.answer(f'👥 کاربران: {u}\n📢 سفارش‌ها: {o}\n💳 پرداخت‌های در انتظار: {p}')
@dp.message(F.text=='لیست کاربران')
async def users(m:Message):
    if not is_admin(m.from_user.id): return
    c=db(); rs=c.execute('SELECT id,name,coins,diamonds FROM users ORDER BY id DESC LIMIT 30').fetchall(); c.close(); await m.answer('\n'.join(f"{r['id']} | {r['name']} | 🪙{r['coins']:,} | 💎{r['diamonds']:,}" for r in rs) or 'کاربری نیست.')

@dp.message(F.text=='تنظیم سکه روزانه')
async def set_daily(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='daily_coins'); await state.set_state(Flow.admin_value); await m.answer('مقدار جدید سکه روزانه را بفرستید.')
@dp.message(F.text=='تنظیم پاداش زیرمجموعه')
async def set_ref(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='referral_coins'); await state.set_state(Flow.admin_value); await m.answer('مقدار پاداش زیرمجموعه را بفرستید.')
@dp.message(F.text=='تنظیمات مقدار سکه دریافتی از کانال ویوو گیر')
async def set_view_reward(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='view_reward'); await state.set_state(Flow.admin_value); await m.answer('مقدار هر سکه بازدید را بفرستید.')
@dp.message(F.text=='تنظیمات مقدار الماس دریافتی کانال ممبر')
async def set_member_reward(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='member_reward'); await state.set_state(Flow.admin_value); await m.answer('مقدار الماس دریافتی هر عضویت را بفرستید.')
@dp.message(F.text=='تنظیم شماره کارت')
async def set_card(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='card_number'); await state.set_state(Flow.admin_value); await m.answer('شماره کارت جدید را بفرستید.')
@dp.message(F.text=='تنظیم لینک درگاه')
async def set_gateway(m:Message,state:FSMContext):
    if is_admin(m.from_user.id): await state.update_data(setting='gateway_url'); await state.set_state(Flow.admin_value); await m.answer('لینک درگاه را بفرستید. برای حذف لینک، 0 ارسال کنید.')
@dp.message(Flow.admin_value)
async def admin_value(m:Message,state:FSMContext):
    d=await state.get_data(); setting=d.get('setting');
    if not setting: return
    if setting=='new_admin':
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
async def webhook(request:Request): data=await request.json(); await dp.feed_raw_update(bot,data); return {'ok':True}
