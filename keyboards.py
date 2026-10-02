from telebot import types

# کیبورد منوی اصلی کاربران
def main_menu_keyboard(is_admin=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn1 = types.KeyboardButton("🎁 هدیه روزانه")
    btn2 = types.KeyboardButton("👥 زیرمجموعه‌گیری")
    btn3 = types.KeyboardButton("👤 حساب کاربری")
    btn4 = types.KeyboardButton("👁‍🗨 ثبت سفارش ویو و ممبر")
    btn5 = types.KeyboardButton("🛒 فروشگاه")
    btn6 = types.KeyboardButton("🔄 انتقال سکه و الماس")
    btn7 = types.KeyboardButton("🏆 ورود به قرعه‌کشی")
    
    markup.add(btn1, btn2)
    markup.add(btn3)
    markup.add(btn4, btn5)
    markup.add(btn6, btn7)
    
    # اگر کاربر مدیر باشد، دکمه پنل مدیریت هم اضافه می‌شود
    if is_admin:
        btn_admin = types.KeyboardButton("⚙️ پنل مدیریت")
        markup.add(btn_admin)
        
    return markup

# کیبورد پنل مدیریت اصلی
def admin_panel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn1 = types.KeyboardButton("⚙️ تغییر مقدار سکه و الماس هدیه روزانه")
    btn2 = types.KeyboardButton("⚙️ تغییر مقدار هدیه زیرمجموعه‌گیری")
    btn3 = types.KeyboardButton("⚙️ تغییر لینک درگاه پرداخت")
    btn4 = types.KeyboardButton("⚙️ تغییر شماره کارت")
    btn5 = types.KeyboardButton("⚙️ تغییر سفارشات ویو و ممبر")
    btn6 = types.KeyboardButton("⚙️️ تغییر قیمت سکه و الماس فروشگاه")
    btn7 = types.KeyboardButton("⚙️ تغییر تنظیمات قرعه کشی")
    btn8 = types.KeyboardButton("⚙️ اسپانسر جوین اجباری")
    btn9 = types.KeyboardButton("⚙️ تنظیم جریمه لفت و روزهای ماندگاری")
    btn10 = types.KeyboardButton("📢 پیام همگانی")
    btn11 = types.KeyboardButton("👋 پیام خوشامد گویی")
    btn_back = types.KeyboardButton("🔙 بازگشت به منوی اصلی")
    
    markup.add(btn1)
    markup.add(btn2)
    markup.add(btn3, btn4)
    markup.add(btn5)
    markup.add(btn6)
    markup.add(btn7)
    markup.add(btn8)
    markup.add(btn9)
    markup.add(btn10, btn11)
    markup.add(btn_back)
    
    return markup

# کیبورد شیشه‌ای بازگشت/انصراف
def cancel_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_action"))
    return markup
