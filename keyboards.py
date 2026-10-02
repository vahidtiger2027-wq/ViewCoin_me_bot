from telebot import types

def main_menu_keyboard(is_admin=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎁 هدیه روزانه", "👥 زیرمجموعه‌گیری")
    markup.add("👤 حساب کاربری")
    markup.add("🛒 فروشگاه", "👁‍‍🗨 ثبت سفارش ویو و ممبر")
    markup.add("🏆 ورود به قرعه‌کشی", "🔄 انتقال سکه و الماس")
    if is_admin:
        markup.add("⚙️ پنل مدیریت")
    return markup

def order_type_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👁‍🗨 سفارش ویو (بازدید)", callback_data="order_type_view"),
        types.InlineKeyboardButton("👥 سفارش ممبر (عضو)", callback_data="order_type_member")
    )
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_action"))
    return markup

def order_packages_keyboard(service_type):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if service_type == "view":
        markup.add(
            types.InlineKeyboardButton("▫️ بسته ۱: ۱۰۰ بازدید ➔ ۱۰ سکه", callback_data="pkg_view_100_10"),
            types.InlineKeyboardButton("▫️ بسته ۲: ۵۰۰ بازدید ➔ ۴۵ سکه", callback_data="pkg_view_500_45"),
            types.InlineKeyboardButton("▫️ بسته ۳: ۱,۰۰۰ بازدید ➔ ۸۰ سکه", callback_data="pkg_view_1000_80"),
            types.InlineKeyboardButton("▫️ بسته ۴: ۵,۰۰۰ بازدید ➔ ۳۵۰ سکه", callback_data="pkg_view_5000_350"),
            types.InlineKeyboardButton("▫️ بسته ۵: ۱۰,۰۰۰ بازدید ➔ ۶۵۰ سکه", callback_data="pkg_view_10000_650")
        )
    elif service_type == "member":
        markup.add(
            types.InlineKeyboardButton("▫️ بسته ۱: ۵۰ ممبر ➔ ۱۰۰ سکه", callback_data="pkg_member_50_100"),
            types.InlineKeyboardButton("▫️ بسته ۲: ۱۰۰ ممبر ➔ ۱۸۰ سکه", callback_data="pkg_member_100_180"),
            types.InlineKeyboardButton("▫️ بسته ۳: ۲۵۰ ممبر ➔ ۴۰۰ سکه", callback_data="pkg_member_250_400"),
            types.InlineKeyboardButton("▫️ بسته ۴: ۵۰۰ ممبر ➔ ۷۵۰ سکه", callback_data="pkg_member_500_750"),
            types.InlineKeyboardButton("▫️ بسته ۵: ۱,۰۰۰ ممبر ➔ ۱,۴۰۰ سکه", callback_data="pkg_member_1000_1400")
        )
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_action"))
    return markup

def cancel_inline_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_action"))
    return markup

def admin_panel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 آمار ربات", "📢 همگانی / پیام عمومی")
    markup.add("⚙️ تنظیمات سکه و هدیه", "💳 تنظیم شماره کارت")
    markup.add("🔙 بازگشت به منوی اصلی")
    return markup
