import os
import sqlite3
import datetime
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8864400306:AAHsgcfH1GdWzJARqMxnX8ABMWBYWFH4Rn4")
PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(level=logging.INFO)

# ----------------- HEALTH CHECK SERVER FOR RENDER -----------------
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
        last_daily TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def get_or_create_user(user_id, username=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, username, coin_view, coin_member, ref_count, last_daily FROM users WHERE user_id=?", (user_id,))
    u = c.fetchone()
    if not u:
        c.execute("INSERT INTO users (user_id, username, coin_view, coin_member, ref_count, last_daily) VALUES (?, ?, 0, 0, 0, '')", (user_id, username))
        conn.commit()
        c.execute("SELECT user_id, username, coin_view, coin_member, ref_count, last_daily FROM users WHERE user_id=?", (user_id,))
        u = c.fetchone()
    conn.close()
    return u

# ----------------- KEYBOARD -----------------
def main_keyboard():
    kb = [
        ["💎جم اوری سکه رایگان"],
        ["💻حصاب کار بری مشحصات", "👥جذب زیر مجموعه"],
        ["📥ثبت تبلیغ ویو گیر و ممبر گیر"],
        ["👨‍💻🛍︎فروشگاه", "دکمه قرعه کشی"],
        ["💰 انتقال سکه", "💎︎  انتقال الماس"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ----------------- HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username or "")
    await update.message.reply_text(f"سلام {user.first_name} عزیز، به ربات خوش آمدید!", reply_markup=main_keyboard())

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    u = get_or_create_user(user.id, user.username or "")

    # ۱. بخش جمع آوری سکه رایگان
    if text == "💎جم اوری سکه رایگان":
        today_str = str(datetime.date.today())
        last_daily = u[5] # ستون last_daily
        
        if last_daily == today_str:
            await update.message.reply_text("❌ شما امروز سکه و الماس رایگان خود را دریافت کرده‌اید!\nلطفاً فردا مجدداً مراجعه کنید.")
        else:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE users SET coin_view = coin_view + 20, coin_member = coin_member + 20, last_daily = ? WHERE user_id=?", (today_str, user.id))
            conn.commit()
            conn.close()
            await update.message.reply_text("🎉 ۲ **سکه ویو** و ۲۰ **الماس ممبر** رایگان به حساب شما اضافه شد!", parse_mode="Markdown")

    # ۲. بخش حساب کاربری
    elif text == "💻حصاب کار بری مشحصات":
        username_str = f"@{u[1]}" if u[1] else "ثبت نشده"
        msg = f"""💻 **مشخصات حساب کاربری شما:**

🆔 **آیدی عددی:** `{u[0]}`
👤 **نام کاربری:** {username_str}
👥 **تعداد زیرمجموعه‌ها:** {u[4]} نفر

💰 **موجودی سکه ویو:** {u[2]}
💎 **موجودی الماس ممبر:** {u[3]}"""
        await update.message.reply_text(msg, parse_mode="Markdown")

    else:
        await update.message.reply_text("این بخش در حال حاضر در حال ساخت و تنظیم است.", reply_markup=main_keyboard())

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    logging.info("Starting bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
