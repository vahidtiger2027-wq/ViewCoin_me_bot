import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # جدول کاربران
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            coins INT DEFAULT 0,
            diamonds INT DEFAULT 0,
            daily_claimed TIMESTAMP,
            referrer_id BIGINT,
            referrals_count INT DEFAULT 0,
            gifts_received INT DEFAULT 0,
            total_views INT DEFAULT 0,
            today_views INT DEFAULT 0,
            lottery_tickets INT DEFAULT 0,
            lottery_wins INT DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE
        );
    ''')
    
    # جدول تنظیمات سیستم
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    
    # جدول قفل‌های جوین اجباری برای جریمه لفت
    cur.execute('''
        CREATE TABLE IF NOT EXISTS member_locks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            channel_id TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lock_days INT DEFAULT 3,
            penalty_diamonds INT DEFAULT 2
        );
    ''')
    
    # مقداردهی اولیه تنظیمات پیش‌فرض
    default_settings = {
        'card_number': 'تنظیم نشده',
        'gateway_url': 'تنظیم نشده',
        'daily_coins': '20',
        'daily_diamonds': '20',
        'ref_coins': '200',
        'ref_diamonds': '50',
        'gift_amount': '0',
        'sponsor_channels': '',
        'welcome_msg': 'به ربات خوش آمدید!',
        'ticket_price_step': '50000',
        'penalty_days': '3',
        'penalty_diamonds': '2',
        'lottery_active': '0',
        'lottery_prizes': '20,50' # نفر اول: 20 الماس 50 سکه
    }
    
    for key, val in default_settings.items():
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING;", (key, val))
        
    conn.commit()
    cur.close()
    conn.close()

if __name__ == '__main__':
    init_db()
