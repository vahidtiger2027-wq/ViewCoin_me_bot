import telebot
from telebot import types
import config
import database
import keyboards

bot = telebot.TeleBot(config.BOT_TOKEN)

# بررسی عضویت کاربر در کانال‌های اسپانسر
def check_sponsorship(user_id):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT link FROM sponsors")
    sponsors = cursor.fetchall()
    conn.close()

    not_joined = []
    for sp in sponsors:
        link = sp['link']
        # استخراج آیدی یا یوزرنیم کانال از لینک
        chat_id = link.split('/')[-1]
        if not chat_id.startswith('@'):
            chat_id = '@' + chat_id
            
        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append((link, chat_id))
        except Exception:
            # در صورت عمومی نبودن یا عدم دسترسی ربات به کانال
            pass

    return not_joined

# هندلر دستور /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = None
    
    # استخراج آیدی دعوت‌کننده از لینک رفرال
    if len(args) > 1 and args[1].isdigit():
        possible_ref = int(args[1])
        if possible_ref != user_id:
            referrer_id = possible_ref

    # ثبت کاربر در دیتابیس
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user_exists = cursor.fetchone()

    if not user_exists:
        cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()
        
        # پاداش زیرمجموعه‌گیری به دعوت‌کننده
        if referrer_id:
            ref_coin = int(database.get_setting("referral_coin") or 0)
            ref_diamond = int(database.get_setting("referral_diamond") or 0)
            
            cursor.execute("""
                UPDATE users 
                SET coins = coins + ?, diamonds = diamonds + ? 
                WHERE user_id = ?
            """, (ref_coin, ref_diamond, referrer_id))
            conn.commit()
            
            try:
                bot.send_message(
                    referrer_id, 
                    f"🎉 کاربر جدیدی با لینک شما وارد ربات شد!\n"
                    f"🎁 پاداش شما: {ref_coin} سکه و {ref_diamond} الماس"
                )
            except Exception:
                pass

    conn.close()

    # بررسی قفل جوین اجباری
    not_joined = check_sponsorship(user_id)
    if not_joined:
        markup = types.InlineKeyboardMarkup()
        for idx, (link, _) in enumerate(not_joined, 1):
            markup.add(types.InlineKeyboardButton(f"📢 عضویت در کانال {idx}", url=link))
        
        markup.add(types.InlineKeyboardButton("✅ عضو شدم / تایید", callback_data="check_join"))
        
        bot.send_message(
            user_id, 
            "⚠️ جهت استفاده از امکانات ربات، ابتدا باید در کانال‌های زیر عضو شوید:", 
            reply_markup=markup
        )
        return

    # ارسال پیام خوش‌آمدگویی و منوی اصلی
    send_welcome_menu(user_id)

# بررسی مجدد جوین اجباری با دکمه شیشه‌ای
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = call.from_user.id
    not_joined = check_sponsorship(user_id)
    
    if not_joined:
        bot.answer_callback_query(call.id, "❌ شما هنوز در تمام کانال‌ها عضو نشده‌اید!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome_menu(user_id)

# تابع ارسال منو و پیام خوش‌آمدگویی
def send_welcome_menu(user_id):
    is_admin = user_id in config.ADMIN_IDS
    welcome_text = database.get_setting("welcome_message") or "به ربات خوش آمدید!"
    
    markup = keyboards.main_menu_keyboard(is_admin=is_admin)
    bot.send_message(user_id, welcome_text, reply_markup=markup)

if __name__ == "__main__":
    database.init_db()
    print("ربات روشن و فعال شد...")
    bot.infinity_polling()
