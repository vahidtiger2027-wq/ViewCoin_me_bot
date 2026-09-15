import os, sqlite3, random, logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
BOT_TOKEN=os.getenv('BOT_TOKEN','').strip(); ADMIN_ID=int(os.getenv('ADMIN_ID','5412332176')); WEBHOOK_URL=os.getenv('WEBHOOK_URL','').rstrip('/'); DB_NAME=os.getenv('DB_NAME','viewcoin.db')
bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if BOT_TOKEN else None
dp=Dispatcher()

def con():
 c=sqlite3.connect(DB_NAME,check_same_thread=False); c.row_factory=sqlite3.Row; return c
def q(sql,p=(),one=False,commit=False):
 c=con()
 try:
  r=c.execute(sql,p); x=r.fetchone() if one else r.fetchall()
  if commit:c.commit()
  return x
 finally:c.close()
def now():return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
def s(k,d=''):
 r=q('select value from settings where key=?',(k,),True); return r['value'] if r else d
def ss(k,v):q('insert into settings(key,value) values(?,?) on conflict(key) do update set value=excluded.value',(k,str(v)),commit=True)
def admin(uid):return uid==ADMIN_ID

def init():
 c=con(); c.executescript('''
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,username TEXT,joined_at TEXT,view_coins INTEGER DEFAULT 0,member_diamonds INTEGER DEFAULT 0,earned_view INTEGER DEFAULT 0,earned_member INTEGER DEFAULT 0,spent_view INTEGER DEFAULT 0,spent_member INTEGER DEFAULT 0,referral_count INTEGER DEFAULT 0,referred_by INTEGER);
 CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
 CREATE TABLE IF NOT EXISTS mandatory_channels(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT,link TEXT);
 CREATE TABLE IF NOT EXISTS order_options(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,amount INTEGER,price INTEGER,enabled INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER,kind TEXT,target_link TEXT,target_amount INTEGER,price INTEGER,completed INTEGER DEFAULT 0,message_id INTEGER,channel TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,user_id INTEGER,kind TEXT,verified INTEGER DEFAULT 0,rewarded INTEGER DEFAULT 0,created_at TEXT,UNIQUE(order_id,user_id));
 CREATE TABLE IF NOT EXISTS coin_packages(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,amount INTEGER,coins INTEGER,enabled INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,method TEXT,package_id INTEGER,amount INTEGER,coins INTEGER,status TEXT DEFAULT 'pending',receipt_file_id TEXT,created_at TEXT,approved_at TEXT);
 CREATE TABLE IF NOT EXISTS lotteries(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,status TEXT DEFAULT 'open',winners INTEGER,prize_view INTEGER,prize_member INTEGER,created_at TEXT,drawn_at TEXT);
 CREATE TABLE IF NOT EXISTS lottery_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,lottery_id INTEGER,user_id INTEGER,payment_id INTEGER,created_at TEXT,UNIQUE(lottery_id,user_id));''')
 defaults={'view_enabled':'1','member_enabled':'1','coin_purchase_enabled':'0','lottery_enabled':'1','view_reward':'5','member_reward':'5','welcome_view_bonus':'40','welcome_member_bonus':'40','referral_reward':'1000','view_channel':'@view_sin_channel','member_channel':'@my_member_man','card_number_1':'','card_number_2':'','payment_link':'','merchant_id':'','payment_api_enabled':'0'}
 for k,v in defaults.items():c.execute('insert or ignore into settings(key,value) values(?,?)',(k,v))
 if c.execute('select count(*) from order_options').fetchone()[0]==0:
  for kind in ('view','member'):
   for a,p in ((40,40),(60,60),(100,100),(200,200)):c.execute('insert into order_options(kind,amount,price) values(?,?,?)',(kind,a,p))
 if c.execute('select count(*) from coin_packages').fetchone()[0]==0:
  for x in (('بسته ۱',10000,1000),('بسته ۲',20000,2200),('بسته ۳',50000,6000)):c.execute('insert into coin_packages(title,amount,coins) values(?,?,?)',x)
 c.commit();c.close()

def adduser(u,ref=None):
 if q('select id from users where id=?',(u.id,),True):return False
 vb,mb=int(s('welcome_view_bonus','40')),int(s('welcome_member_bonus','40'))
 q('insert into users(id,name,username,joined_at,referred_by,view_coins,member_diamonds,earned_view,earned_member) values(?,?,?,?,?,?,?,?,?)',(u.id,u.full_name,u.username or '',now(),ref,vb,mb,vb,mb),commit=True)
 if ref and ref!=u.id and q('select id from users where id=?',(ref,),True):
  r=int(s('referral_reward','1000'));q('update users set view_coins=view_coins+?,earned_view=earned_view+?,referral_count=referral_count+1 where id=?',(r,r,ref),commit=True)
 return True

def menu():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='👤 حساب کاربری')],[KeyboardButton(text='🪙 جمع‌آوری سکه'),KeyboardButton(text='👁 ویوگیر')],[KeyboardButton(text='👥 ممبرگیر'),KeyboardButton(text='📢 ثبت سفارش ویو')],[KeyboardButton(text='👥 ثبت سفارش ممبر'),KeyboardButton(text='📋 سفارش‌های من')],[KeyboardButton(text='💳 خرید سکه'),KeyboardButton(text='🎁 دعوت دوستان')],[KeyboardButton(text='🎟️ قرعه‌کشی'),KeyboardButton(text='ℹ️ راهنما')]],resize_keyboard=True,is_persistent=True)
def amenu():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='🔗 عضویت اجباری'),KeyboardButton(text='🪙 مدیریت سکه')],[KeyboardButton(text='📢 مدیریت سفارش‌ها'),KeyboardButton(text='👥 کاربران')],[KeyboardButton(text='📊 آمار ربات'),KeyboardButton(text='⚙️ تنظیمات')],[KeyboardButton(text='🎟️ قرعه‌کشی'),KeyboardButton(text='💳 پرداخت‌ها')],[KeyboardButton(text='⬅️ منوی کاربر')]],resize_keyboard=True,is_persistent=True)

def mandatory_kb(rows):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='عضویت در '+r['username'],url=r['link'])] for r in rows]+[[InlineKeyboardButton(text='🔎 بررسی عضویت',callback_data='check_membership')]])
async def member_ok(uid):
 if admin(uid):return True
 for r in q('select * from mandatory_channels'):
  try:
   m=await bot.get_chat_member(r['username'],uid)
   if m.status not in ('member','administrator','creator'):return False
  except:return False
 return True
async def gate(m):
 if await member_ok(m.from_user.id):return True
 rows=q('select * from mandatory_channels');await m.answer('🔒 ابتدا در کانال‌های اجباری عضو شو و سپس بررسی عضویت را بزن.',reply_markup=mandatory_kb(rows));return False

@dp.message(CommandStart())
async def start(m):
 a=m.text.split(maxsplit=1);ref=int(a[1]) if len(a)==2 and a[1].isdigit() else None;new=adduser(m.from_user,ref)
 text='<b>به ViewCoin خوش آمدی 🌟</b>\n\n🪙 سکه ویو مخصوص ویوگیر است.\n💎 الماس ممبر مخصوص ممبرگیر است.\n'
 if new:text+=f"\n🎁 پاداش ورود: 🪙 {s('welcome_view_bonus','40')} سکه و 💎 {s('welcome_member_bonus','40')} الماس"
 await m.answer(text,reply_markup=menu())
 if not await member_ok(m.from_user.id):await m.answer('🔒 عضویت اجباری:',reply_markup=mandatory_kb(q('select * from mandatory_channels')))
@dp.message(Command('admin'))
async def ac(m):
 if admin(m.from_user.id):await m.answer('👨‍💼 پنل مدیریت',reply_markup=amenu())
@dp.message(F.text=='⬅️ منوی کاربر')
async def um(m):await m.answer('منوی کاربر 👇',reply_markup=menu())
@dp.callback_query(F.data=='check_membership')
async def chk(c):
 if await member_ok(c.from_user.id):await c.message.answer('✅ عضویت تأیید شد.',reply_markup=menu())
 else:await c.answer('هنوز عضویت تأیید نشده.',show_alert=True)
@dp.message(F.text=='👤 حساب کاربری')
async def account(m):
 if not await gate(m):return
 u=q('select * from users where id=?',(m.from_user.id,),True); me=await bot.get_me()
 await m.answer(f"<b>👤 حساب کاربری</b>\n\n🆔 {u['id']}\n👤 {u['name']}\n📅 {u['joined_at']}\n\n🪙 سکه: <b>{u['view_coins']}</b>\n💎 الماس: <b>{u['member_diamonds']}</b>\n\n📥 سکه دریافتی: {u['earned_view']}\n📤 سکه مصرفی: {u['spent_view']}\n📥 الماس دریافتی: {u['earned_member']}\n📤 الماس مصرفی: {u['spent_member']}\n🎁 دعوت‌ها: {u['referral_count']}\n🔗 https://t.me/{me.username}?start={u['id']}")
@dp.message(F.text=='🎁 دعوت دوستان')
async def ref(m):
 me=await bot.get_me();await m.answer(f"🎁 پاداش دعوت: {s('referral_reward','1000')} سکه\n\n🔗 https://t.me/{me.username}?start={m.from_user.id}")
@dp.message(F.text=='ℹ️ راهنما')
async def help_(m):await m.answer('👁 ویوگیر: انجام وظایف ویو و دریافت 🪙\n👥 ممبرگیر: عضویت واقعی و دریافت 💎\n📢 ثبت سفارش: با ارز همان سیستم\n💳 خرید سکه: در صورت فعال بودن\n🎟️ هر خرید موفق یک بلیت دوره فعال می‌دهد.')

async def tasks(m,kind):
 if not await gate(m):return
 key='view_enabled' if kind=='view' else 'member_enabled'
 if s(key,'1')!='1':await m.answer('این سیستم فعلاً خاموش است.');return
 for o in q("select * from orders where kind=? and completed=0 order by id desc limit 10",(kind,)):
  if q('select * from tasks where order_id=? and user_id=? and rewarded=1',(o['id'],m.from_user.id),True):continue
  reward=int(s('view_reward' if kind=='view' else 'member_reward','5'));link=o['target_link'] or s('view_channel')
  label='👁 انجام ویو' if kind=='view' else '👥 عضویت'
  cb='claim:'+str(o['id']);kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label,url=link)] if link else [],[InlineKeyboardButton(text=('🪙 دریافت سکه' if kind=='view' else '💎 دریافت الماس'),callback_data=cb)]])
  await m.answer(f"<b>سفارش #{o['id']}</b>\nهدف: {o['target_amount']}\nپاداش: {reward}",reply_markup=kb)
@dp.message(F.text.in_({'🪙 جمع‌آوری سکه','👁 ویوگیر'}))
async def vt(m):await tasks(m,'view')
@dp.message(F.text=='👥 ممبرگیر')
async def mt(m):await tasks(m,'member')
@dp.callback_query(F.data.startswith('claim:'))
async def claim(c):
 o=q('select * from orders where id=?',(int(c.data.split(':')[1]),),True)
 if not o or o['completed']:await c.answer('سفارش تمام شده.',show_alert=True);return
 if q('select * from tasks where order_id=? and user_id=? and rewarded=1',(o['id'],c.from_user.id),True):await c.answer('قبلاً پاداش گرفتی.',show_alert=True);return
 if o['kind']=='member':
  try:
   mm=await bot.get_chat_member(o['target_link'],c.from_user.id)
   if mm.status not in ('member','administrator','creator'):raise Exception()
  except:await c.answer('عضویت قابل تأیید نیست؛ مقصد باید عمومی/قابل بررسی باشد و ربات دسترسی لازم داشته باشد.',show_alert=True);return
 reward=int(s('view_reward' if o['kind']=='view' else 'member_reward','5'));cdb=con()
 try:
  cdb.execute('insert into tasks(order_id,user_id,kind,verified,rewarded,created_at) values(?,?,?,?,?,?)',(o['id'],c.from_user.id,o['kind'],1,1,now()))
  if o['kind']=='view':cdb.execute('update users set view_coins=view_coins+?,earned_view=earned_view+? where id=?',(reward,reward,c.from_user.id))
  else:cdb.execute('update users set member_diamonds=member_diamonds+?,earned_member=earned_member+? where id=?',(reward,reward,c.from_user.id))
  n=cdb.execute('select count(*) from tasks where order_id=? and rewarded=1',(o['id'],)).fetchone()[0]
  if n>=o['target_amount']:cdb.execute('update orders set completed=1 where id=?',(o['id'],))
  cdb.commit()
 finally:cdb.close()
 await c.answer('پاداش ثبت شد ✅');await c.message.answer(f"🎉 +{reward} {'🪙' if o['kind']=='view' else '💎'}")
 if q('select completed from orders where id=?',(o['id'],),True)['completed'] and o['message_id']:
  try:await bot.delete_message(o['channel'],o['message_id'])
  except:pass

states={}
async def options(m,kind):
 rows=q('select * from order_options where kind=? and enabled=1 order by amount',(kind,));kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{r['amount']} عدد = {r['price']}",callback_data=f'new:{kind}:{r["id"]}')] for r in rows]);await m.answer('گزینه سفارش را انتخاب کن:',reply_markup=kb)
@dp.message(F.text=='📢 ثبت سفارش ویو')
async def ov(m):
 if await gate(m) and s('view_enabled')=='1':await options(m,'view')
@dp.message(F.text=='👥 ثبت سفارش ممبر')
async def om(m):
 if await gate(m) and s('member_enabled')=='1':await options(m,'member')
@dp.callback_query(F.data.startswith('new:'))
async def neworder(c):
 _,kind,oid=c.data.split(':');o=q('select * from order_options where id=?',(int(oid),),True);states[c.from_user.id]={'kind':kind,'amount':o['amount'],'price':o['price']}
 await c.message.answer('🔗 لینک مقصد را بفرست.' if kind=='member' else 'برای ثبت سفارش عبارت «تأیید» را بفرست.');await c.answer()
@dp.message(F.text=='📋 سفارش‌های من')
async def mine(m):
 rows=q('select * from orders where owner_id=? order by id desc limit 20',(m.from_user.id,));await m.answer('\n'.join([f"#{x['id']} {'ویو' if x['kind']=='view' else 'ممبر'} {x['target_amount']} {'✅' if x['completed'] else '🟡'}" for x in rows]) or 'سفارشی نداری.')
@dp.message()
async def state(m):
 st=states.get(m.from_user.id)
 if not st:return
 if st['kind']=='member' and 'link' not in st:
  st['link']=(m.text or '').strip();cur='member_diamonds';u=q('select member_diamonds from users where id=?',(m.from_user.id,),True)
  if u[cur]<st['price']:states.pop(m.from_user.id);await m.answer('💎 الماس کافی نیست.');return
  q('insert into orders(owner_id,kind,target_link,target_amount,price,created_at) values(?,?,?,?,?,?)',(m.from_user.id,'member',st['link'],st['amount'],st['price'],now()),commit=True);q('update users set member_diamonds=member_diamonds-?,spent_member=spent_member+? where id=?',(st['price'],st['price'],m.from_user.id),commit=True);states.pop(m.from_user.id);await m.answer('✅ سفارش ممبر ثبت شد.');return
 if st['kind']=='view' and (m.text or '').strip()=='تأیید':
  u=q('select view_coins from users where id=?',(m.from_user.id,),True)
  if u['view_coins']<st['price']:states.pop(m.from_user.id);await m.answer('🪙 سکه کافی نیست.');return
  q('insert into orders(owner_id,kind,target_link,target_amount,price,created_at) values(?,?,?,?,?,?)',(m.from_user.id,'view',s('view_channel'),st['amount'],st['price'],now()),commit=True);q('update users set view_coins=view_coins-?,spent_view=spent_view+? where id=?',(st['price'],st['price'],m.from_user.id),commit=True);states.pop(m.from_user.id);await m.answer('✅ سفارش ویو ثبت شد.')

@dp.message(F.text=='💳 خرید سکه')
async def buy(m):
 if s('coin_purchase_enabled','0')!='1':await m.answer('💳 خرید سکه فعلاً خاموش است.');return
 rows=q('select * from coin_packages where enabled=1');await m.answer('بسته را انتخاب کن:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{x['title']} — {x['amount']:,} تومان / {x['coins']} سکه",callback_data=f'pkg:{x["id"]}')] for x in rows]))
@dp.callback_query(F.data.startswith('pkg:'))
async def pkg(c):
 p=q('select * from coin_packages where id=?',(int(c.data.split(':')[1]),),True);buttons=[]
 if s('payment_link'):buttons.append([InlineKeyboardButton(text='🌐 لینک پرداخت',url=s('payment_link'))])
 if s('card_number_1') or s('card_number_2'):buttons.append([InlineKeyboardButton(text='💳 پرداخت دستی و ارسال رسید',callback_data='manual:'+str(p['id']))])
 await c.message.answer(f"{p['title']}\nمبلغ: {p['amount']:,}\nسکه: {p['coins']}",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons));await c.answer()
@dp.callback_query(F.data.startswith('manual:'))
async def manual(c):
 pid=int(c.data.split(':')[1]);p=q('select * from coin_packages where id=?',(pid,),True);q('insert into payments(user_id,method,package_id,amount,coins,created_at) values(?,?,?,?,?,?)',(c.from_user.id,'manual',pid,p['amount'],p['coins'],now()),commit=True);cards='\n'.join(x for x in ['💳 '+s('card_number_1'),'💳 '+s('card_number_2')] if x!='💳 ');await c.message.answer(f"{p['amount']:,} تومان پرداخت کن.\n{cards}\n\nسپس عکس رسید را بفرست.");await c.answer()
@dp.message(F.photo)
async def receipt(m):
 p=q("select * from payments where user_id=? and status='pending' order by id desc limit 1",(m.from_user.id,),True)
 if not p:return
 q('update payments set receipt_file_id=? where id=?',(m.photo[-1].file_id,p['id']),commit=True)
 await m.answer('🧾 رسید دریافت شد؛ بعد از تأیید مدیر سکه اضافه می‌شود.')
 await bot.send_photo(ADMIN_ID,m.photo[-1].file_id,caption=f"رسید #{p['id']} | کاربر {m.from_user.id} | {p['amount']:,} | {p['coins']} سکه",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ تأیید',callback_data=f'payok:{p["id"]}'),InlineKeyboardButton(text='❌ رد',callback_data=f'payno:{p["id"]}')]]))
async def ticket(uid,pid):
 if s('lottery_enabled','1')!='1':return
 l=q("select * from lotteries where status='open' order by id desc limit 1",one=True)
 if l:q('insert or ignore into lottery_tickets(lottery_id,user_id,payment_id,created_at) values(?,?,?,?)',(l['id'],uid,pid,now()),commit=True)
@dp.callback_query(F.data.startswith('payok:'))
async def payok(c):
 if not admin(c.from_user.id):return
 p=q('select * from payments where id=?',(int(c.data.split(':')[1]),),True)
 if not p or p['status']!='pending':return
 q('update payments set status="approved",approved_at=? where id=?',(now(),p['id']),commit=True);q('update users set view_coins=view_coins+?,earned_view=earned_view+? where id=?',(p['coins'],p['coins'],p['user_id']),commit=True);await ticket(p['user_id'],p['id']);await c.message.answer('✅ پرداخت تأیید شد.');await c.answer('تأیید شد')
 try:await bot.send_message(p['user_id'],f"✅ پرداخت تأیید شد. 🪙 +{p['coins']} سکه")
 except:pass
@dp.callback_query(F.data.startswith('payno:'))
async def payno(c):
 if admin(c.from_user.id):q('update payments set status="rejected" where id=? and status="pending"',(int(c.data.split(':')[1]),),commit=True);await c.message.answer('❌ پرداخت رد شد.');await c.answer()

@dp.message(F.text=='🎟️ قرعه‌کشی')
async def lottery(m):
 if not admin(m.from_user.id):
  if s('lottery_enabled','1')!='1':await m.answer('قرعه‌کشی خاموش است.');return
  l=q("select * from lotteries where status='open' order by id desc limit 1",one=True)
  if not l:await m.answer('دوره فعالی نیست.');return
  t=q('select id from lottery_tickets where lottery_id=? and user_id=?',(l['id'],m.from_user.id),True);await m.answer(f"🎟️ {l['title']}\nبلیت تو: {'✅ داری' if t else '❌ نداری'}\n\nبرای هر دوره باید خرید موفق همان دوره را داشته باشی.");return
 l=q('select * from lotteries order by id desc limit 1',one=True);await m.answer((f"🎟️ {l['title']} | {l['status']} | برنده {l['winners']} | 🪙{l['prize_view']} | 💎{l['prize_member']}" if l else 'دوره‌ای نیست.')+'\n/lottery_new عنوان|برندگان|سکه|الماس\n/lottery_draw')
@dp.message(Command('lottery_new'))
async def lnew(m):
 if not admin(m.from_user.id):return
 p=m.text.partition(' ')[2].split('|')
 if len(p)!=4:return
 q("update lotteries set status='closed' where status='open'",commit=True);q('insert into lotteries(title,status,winners,prize_view,prize_member,created_at) values(?,?,?,?,?,?)',(p[0],'open',int(p[1]),int(p[2]),int(p[3]),now()),commit=True);await m.answer('🎟️ دوره جدید فعال شد.')
@dp.message(Command('lottery_draw'))
async def ldraw(m):
 if not admin(m.from_user.id):return
 l=q("select * from lotteries where status='open' order by id desc limit 1",one=True);ids=[x['user_id'] for x in q('select user_id from lottery_tickets where lottery_id=?',(l['id'],))] if l else []
 if not ids:await m.answer('بلیتی وجود ندارد.');return
 win=random.sample(ids,min(l['winners'],len(ids)));c=con()
 for uid in win:c.execute('update users set view_coins=view_coins+?,member_diamonds=member_diamonds+?,earned_view=earned_view+?,earned_member=earned_member+? where id=?',(l['prize_view'],l['prize_member'],l['prize_view'],l['prize_member'],uid))
 c.execute("update lotteries set status='drawn',drawn_at=? where id=?",(now(),l['id']));c.commit();c.close();await m.answer('🎉 برندگان: '+', '.join(map(str,win)))
 for uid in win:
  try:await bot.send_message(uid,f"🎉 برنده شدی! 🪙 +{l['prize_view']} | 💎 +{l['prize_member']}")
  except:pass

@dp.message(F.text=='📊 آمار ربات')
async def stats(m):
 if not admin(m.from_user.id):return
 users=q('select count(*) c from users',one=True)['c']; orders=q('select count(*) c from orders',one=True)['c']; pays=q("select count(*) c from payments where status='approved'",one=True)['c']; await m.answer(f'📊 کاربران: {users}\n📢 سفارش‌ها: {orders}\n💳 پرداخت موفق: {pays}')
@dp.message(F.text=='⚙️ تنظیمات')
async def settings(m):
 if not admin(m.from_user.id):return
 await m.answer(f"👁 ویو: {s('view_enabled')} | 👥 ممبر: {s('member_enabled')} | 💳 خرید: {s('coin_purchase_enabled')} | 🎟️ قرعه: {s('lottery_enabled')}\n🪙 پاداش ویو: {s('view_reward')}\n💎 پاداش ممبر: {s('member_reward')}\n🎁 ورود: {s('welcome_view_bonus')} / {s('welcome_member_bonus')}\n🎁 دعوت: {s('referral_reward')}\n👁 {s('view_channel')}\n👥 {s('member_channel')}\n\nتغییر: /set کلید مقدار")
@dp.message(F.text=='🪙 مدیریت سکه')
async def coins(m):
 if admin(m.from_user.id):await m.answer('/set view_reward 5\n/set member_reward 5\n/set welcome_view_bonus 40\n/set welcome_member_bonus 40\n/set referral_reward 1000')
@dp.message(F.text=='🔗 عضویت اجباری')
async def mand(m):
 if not admin(m.from_user.id):return
 x=q('select * from mandatory_channels');await m.answer('\n'.join(f"#{r['id']} {r['username']} {r['link']}" for r in x) or 'کانالی نیست.')
@dp.message(F.text=='👥 کاربران')
async def users(m):
 if admin(m.from_user.id):await m.answer('\n'.join(f"{u['id']} 🪙{u['view_coins']} 💎{u['member_diamonds']}" for u in q('select * from users order by id desc limit 30')) or 'کاربری نیست.')
@dp.message(F.text=='📢 مدیریت سفارش‌ها')
async def ao(m):
 if admin(m.from_user.id):await m.answer('\n'.join(f"#{x['id']} {x['kind']} {x['amount']}={x['price']} {'روشن' if x['enabled'] else 'خاموش'}" for x in q('select * from order_options')))
@dp.message(F.text=='💳 پرداخت‌ها')
async def ap(m):
 if admin(m.from_user.id):await m.answer('\n'.join(f"#{x['id']} user{x['user_id']} {x['amount']} {x['coins']}" for x in q("select * from payments where status='pending' order by id desc limit 30")) or 'پرداخت معلقی نیست.')
@dp.message(Command('set'))
async def setcmd(m):
 if not admin(m.from_user.id):return
 p=m.text.split(maxsplit=2)
 if len(p)<3:return
 allowed={'view_enabled','member_enabled','coin_purchase_enabled','lottery_enabled','view_reward','member_reward','welcome_view_bonus','welcome_member_bonus','referral_reward','view_channel','member_channel','card_number_1','card_number_2','payment_link','merchant_id','payment_api_enabled'}
 if p[1] not in allowed:return
 ss(p[1],p[2]);await m.answer('✅ ذخیره شد.')
@dp.message(Command('addchannel'))
async def addch(m):
 if admin(m.from_user.id):
  p=m.text.split();q('insert into mandatory_channels(username,link) values(?,?)',(p[1],p[2]),commit=True);await m.answer('✅ اضافه شد.')
@dp.message(Command('delchannel'))
async def delch(m):
 if admin(m.from_user.id):q('delete from mandatory_channels where id=?',(int(m.text.split()[1]),),commit=True);await m.answer('✅ حذف شد.')

@asynccontextmanager
async def life(app):
 init()
 if bot and WEBHOOK_URL:
  try:await bot.set_webhook(WEBHOOK_URL+'/webhook',drop_pending_updates=True)
  except Exception:logging.exception('webhook')
 yield
 if bot:await bot.session.close()
app=FastAPI(title='ViewCoin',lifespan=life)
@app.get('/')
async def root():return {'status':'ok','bot':'ViewCoin'}
@app.get('/health')
async def health():return {'status':'healthy'}
@app.post('/webhook')
async def webhook(request:Request):
 if not bot:return {'ok':False,'error':'BOT_TOKEN missing'}
 u=Update.model_validate(await request.json(),context={'bot':bot});await dp.feed_update(bot,u);return {'ok':True}
