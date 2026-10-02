import sqlite3
from config import DB_NAME

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # جدول کاربران
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        coins INTEGER DEFAULT 0,
        diamonds INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT NULL,
        tickets INTEGER DEFAULT 0,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # جدول تنظیمات عمومی و داینامیک
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')

    # جدول بسته‌های سفارشات (ویو و ممبر)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS order_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        slot_index INTEGER,
        text_label TEXT
    )
    ''')

    # جدول بسته‌های فروشگاه (سکه و الماس)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shop_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        slot_index INTEGER,
        text_label TEXT
    )
    ''')

    # جدول بسته‌های بلیت قرعه‌کشی
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lottery_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot_index INTEGER,
        text_label TEXT
    )
    ''')

    # جدول لینک‌های جوین اجباری (اسپانسرها)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sponsors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link TEXT UNIQUE
    )
    ''')

    # مقداردهی اولیه تنظیمات پیش‌فرض
    default_settings = {
        "daily_coin": "100",
        "daily_diamond": "5",
        "referral_coin": "50",
        "referral_diamond": "2",
        "gateway_url": "https://example.com/pay",
        "card_number": "6037990000000000",
        "lottery_prize_1": "نامشخص",
        "lottery_prize_2": "نامشخص",
        "lottery_prize_3": "نامشخص",
        "lottery_period": "weekly",
        "lottery_status": "off",
        "lottery_end_date": "",
        "leave_penalty": "0",
        "retention_days": "0",
        "welcome_message": "به ربات ما خوش آمدید!"
    }

    for key, value in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    for i in range(1, 6):
        cursor.execute("INSERT OR IGNORE INTO order_packages (id, type, slot_index, text_label) VALUES (?, 'view', ?, ?)",
                       (i, i, f"بسته ویو {i}"))
        cursor.execute("INSERT OR IGNORE INTO order_packages (id, type, slot_index, text_label) VALUES (?, 'member', ?, ?)",
                       (i+5, i, f"بسته ممبر {i}"))

    for i in range(1, 6):
        cursor.execute("INSERT OR IGNORE INTO shop_packages (id, type, slot_index, text_label) VALUES (?, 'coin', ?, ?)",
                       (i, i, f"بسته سکه {i}"))
        cursor.execute("INSERT OR IGNORE INTO shop_packages (id, type, slot_index, text_label) VALUES (?, 'diamond', ?, ?)",
                       (i+5, i, f"بسته الماس {i}"))

    for i in range(1, 6):
        cursor.execute("INSERT OR IGNORE INTO lottery_packages (id, slot_index, text_label) VALUES (?, ?, ?)",
                       (i, i, f"بسته بلیت {i}"))

    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
