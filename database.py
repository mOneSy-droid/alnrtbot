import sqlite3
from config import DB_NAME
from datetime import datetime, timedelta
import time
import os
import json

def get_connection():
    """Ma'lumotlar bazasiga ulanish - timeout bilan"""
    conn = sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-2000")
    return conn

def fix_value(value, default=0):
    """Qiymatni integer ga o'tkazish"""
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(',', '').replace(' ', '')
            return int(float(value)) if value else default
        return int(value)
    except:
        return default

def fix_room_data(room):
    """Xona ma'lumotlarini tuzatish"""
    if not room:
        return room
    
    room_list = list(room)
    
    if len(room_list) > 5:
        room_list[5] = fix_value(room_list[5])
    
    if len(room_list) > 6:
        room_list[6] = fix_value(room_list[6])
    
    for i in range(7, len(room_list)):
        room_list[i] = fix_value(room_list[i], 0)
    
    return tuple(room_list)

# ==================== FIX ALL DUPLICATES FUNCTIONS ====================

def fix_all_duplicates():
    """Barcha jadvallardagi duplikatlarni tozalash va UNIQUE constraint qo'shish"""
    conn = get_connection()
    c = conn.cursor()
    
    print("=" * 60)
    print("🔍 BARCHA JADVALLARDAGI DUPLIKATLARNI TEKSHIRISH...")
    print("=" * 60)
    
    fix_meals_duplicates(conn, c)
    fix_rooms_duplicates(conn, c)
    fix_salads_duplicates(conn, c)
    fix_soups_duplicates(conn, c)
    
    conn.close()
    
    print("=" * 60)
    print("✅ BARCHA JADVALLARDAGI DUPLIKATLAR TOZALANDI!")
    print("=" * 60)


def fix_meals_duplicates(conn, c):
    """Meals jadvalidagi duplikatlarni tozalash"""
    print("\n📋 MEALS JADVALI...")
    print("-" * 40)
    
    try:
        c.execute("""
            SELECT name_uz, COUNT(*) as cnt, MIN(id) as first_id
            FROM meals 
            GROUP BY name_uz 
            HAVING cnt > 1
        """)
        
        duplicates = c.fetchall()
        
        if duplicates:
            print(f"⚠️ {len(duplicates)} ta ovqatda duplikat topildi:")
            total_deleted = 0
            for dup in duplicates:
                name_uz = dup['name_uz']
                first_id = dup['first_id']
                cnt = dup['cnt']
                print(f"   • {name_uz}: {cnt} ta nusxa")
                
                c.execute("DELETE FROM meals WHERE name_uz = ? AND id != ?", (name_uz, first_id))
                total_deleted += c.rowcount
            
            conn.commit()
            print(f"✅ {total_deleted} ta duplikat o'chirildi!")
        else:
            print("✅ Duplikatlar topilmadi!")
        
        c.execute("PRAGMA table_info(meals)")
        columns = c.fetchall()
        has_unique = False
        for col in columns:
            if col[1] == 'name_uz' and col[4] == 1:
                has_unique = True
                break
        
        if not has_unique:
            print("🔄 UNIQUE constraint qo'shilmoqda...")
            c.execute("ALTER TABLE meals RENAME TO meals_old")
            
            c.execute("""CREATE TABLE meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_uz TEXT UNIQUE,
                name_ru TEXT UNIQUE,
                price INTEGER,
                category TEXT,
                emoji TEXT,
                description_uz TEXT,
                description_ru TEXT,
                is_available INTEGER DEFAULT 1
            )""")
            
            c.execute("""
                INSERT INTO meals (name_uz, name_ru, price, category, emoji, description_uz, description_ru, is_available)
                SELECT DISTINCT name_uz, name_ru, price, category, emoji, description_uz, description_ru, is_available
                FROM meals_old
                WHERE name_uz IS NOT NULL
            """)
            
            c.execute("DROP TABLE meals_old")
            conn.commit()
            print("✅ UNIQUE constraint qo'shildi!")
        else:
            print("✅ UNIQUE constraint allaqachon mavjud!")
            
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        conn.rollback()


def fix_rooms_duplicates(conn, c):
    """Rooms jadvalidagi duplikatlarni tozalash (room_number UNIQUE)"""
    print("\n📋 ROOMS JADVALI...")
    print("-" * 40)
    
    try:
        c.execute("""
            SELECT room_number, COUNT(*) as cnt, MIN(id) as first_id
            FROM rooms 
            GROUP BY room_number 
            HAVING cnt > 1
        """)
        
        duplicates = c.fetchall()
        
        if duplicates:
            print(f"⚠️ {len(duplicates)} ta xona raqamida duplikat topildi:")
            total_deleted = 0
            for dup in duplicates:
                room_number = dup['room_number']
                first_id = dup['first_id']
                cnt = dup['cnt']
                print(f"   • Xona #{room_number}: {cnt} ta nusxa")
                
                c.execute("DELETE FROM rooms WHERE room_number = ? AND id != ?", (room_number, first_id))
                total_deleted += c.rowcount
            
            conn.commit()
            print(f"✅ {total_deleted} ta duplikat o'chirildi!")
        else:
            print("✅ Duplikatlar topilmadi!")
        
        c.execute("PRAGMA table_info(rooms)")
        columns = c.fetchall()
        has_unique = False
        for col in columns:
            if col[1] == 'room_number' and col[4] == 1:
                has_unique = True
                break
        
        if not has_unique:
            print("🔄 UNIQUE constraint qo'shilmoqda...")
            
            # Eski jadvalni saqlash
            c.execute("SELECT * FROM rooms")
            old_rooms = c.fetchall()
            
            c.execute("DROP TABLE IF EXISTS rooms")
            
            # Yangi jadvalni yaratish - TO'G'RI USTUNLAR BILAN
            c.execute("""CREATE TABLE rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                room_number TEXT UNIQUE,
                name TEXT, 
                description TEXT, 
                image TEXT, 
                price INTEGER, 
                capacity INTEGER, 
                type TEXT,
                has_tv INTEGER DEFAULT 1, 
                has_ac INTEGER DEFAULT 1, 
                has_wifi INTEGER DEFAULT 1, 
                has_pool INTEGER DEFAULT 0,
                has_sauna INTEGER DEFAULT 0, 
                has_billiard INTEGER DEFAULT 0,
                has_tennis INTEGER DEFAULT 0, 
                has_tapchan INTEGER DEFAULT 0,
                has_banket INTEGER DEFAULT 0,
                is_available INTEGER DEFAULT 1,
                is_blocked INTEGER DEFAULT 0
            )""")
            
            # Eski ma'lumotlarni yangi jadvalga o'tkazish
            for room in old_rooms:
                try:
                    # room_number, name, description, image, price, capacity, type,
                    # has_tv, has_ac, has_wifi, has_pool, has_sauna, has_billiard,
                    # has_tennis, has_tapchan, has_banket, is_available, is_blocked
                    c.execute("""
                        INSERT OR IGNORE INTO rooms (
                            room_number, name, description, image, price, capacity, type,
                            has_tv, has_ac, has_wifi, has_pool, has_sauna, has_billiard,
                            has_tennis, has_tapchan, has_banket, is_available, is_blocked
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        room[1] if len(room) > 1 else None,  # room_number
                        room[2] if len(room) > 2 else None,  # name
                        room[3] if len(room) > 3 else None,  # description
                        room[4] if len(room) > 4 else None,  # image
                        fix_value(room[5]) if len(room) > 5 else 0,  # price
                        fix_value(room[6]) if len(room) > 6 else 0,  # capacity
                        room[7] if len(room) > 7 else 'standart',  # type
                        fix_value(room[8]) if len(room) > 8 else 1,  # has_tv
                        fix_value(room[9]) if len(room) > 9 else 1,  # has_ac
                        fix_value(room[10]) if len(room) > 10 else 1,  # has_wifi
                        fix_value(room[11]) if len(room) > 11 else 0,  # has_pool
                        fix_value(room[12]) if len(room) > 12 else 0,  # has_sauna
                        fix_value(room[13]) if len(room) > 13 else 0,  # has_billiard
                        fix_value(room[14]) if len(room) > 14 else 0,  # has_tennis
                        fix_value(room[15]) if len(room) > 15 else 0,  # has_tapchan
                        fix_value(room[16]) if len(room) > 16 else 0,  # has_banket
                        fix_value(room[17]) if len(room) > 17 else 1,  # is_available
                        fix_value(room[18]) if len(room) > 18 else 0   # is_blocked
                    ))
                except Exception as e:
                    print(f"Ma'lumot o'tkazishda xatolik: {e}")
            
            conn.commit()
            print("✅ UNIQUE constraint qo'shildi!")
        else:
            print("✅ UNIQUE constraint allaqachon mavjud!")
            
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        conn.rollback()


def fix_salads_duplicates(conn, c):
    """Salads jadvalidagi duplikatlarni tozalash"""
    print("\n📋 SALADS JADVALI...")
    print("-" * 40)
    
    try:
        c.execute("""
            SELECT name, COUNT(*) as cnt, MIN(id) as first_id
            FROM salads 
            GROUP BY name 
            HAVING cnt > 1
        """)
        
        duplicates = c.fetchall()
        
        if duplicates:
            print(f"⚠️ {len(duplicates)} ta salatda duplikat topildi:")
            total_deleted = 0
            for dup in duplicates:
                name = dup['name']
                first_id = dup['first_id']
                cnt = dup['cnt']
                print(f"   • {name}: {cnt} ta nusxa")
                
                c.execute("DELETE FROM salads WHERE name = ? AND id != ?", (name, first_id))
                total_deleted += c.rowcount
            
            conn.commit()
            print(f"✅ {total_deleted} ta duplikat o'chirildi!")
        else:
            print("✅ Duplikatlar topilmadi!")
        
        c.execute("PRAGMA table_info(salads)")
        columns = c.fetchall()
        has_unique = False
        for col in columns:
            if col[1] == 'name' and col[4] == 1:
                has_unique = True
                break
        
        if not has_unique:
            print("🔄 UNIQUE constraint qo'shilmoqda...")
            c.execute("ALTER TABLE salads RENAME TO salads_old")
            
            c.execute("""CREATE TABLE salads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                price INTEGER,
                weight TEXT,
                note TEXT,
                category TEXT DEFAULT 'oddiy'
            )""")
            
            c.execute("""
                INSERT INTO salads (name, price, weight, note, category)
                SELECT DISTINCT name, price, weight, note, category
                FROM salads_old
                WHERE name IS NOT NULL
            """)
            
            c.execute("DROP TABLE salads_old")
            conn.commit()
            print("✅ UNIQUE constraint qo'shildi!")
        else:
            print("✅ UNIQUE constraint allaqachon mavjud!")
            
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        conn.rollback()


def fix_soups_duplicates(conn, c):
    """Soups jadvalidagi duplikatlarni tozalash"""
    print("\n📋 SOUPS JADVALI...")
    print("-" * 40)
    
    try:
        c.execute("""
            SELECT name, COUNT(*) as cnt, MIN(id) as first_id
            FROM soups 
            GROUP BY name 
            HAVING cnt > 1
        """)
        
        duplicates = c.fetchall()
        
        if duplicates:
            print(f"⚠️ {len(duplicates)} ta suyuq ovqatda duplikat topildi:")
            total_deleted = 0
            for dup in duplicates:
                name = dup['name']
                first_id = dup['first_id']
                cnt = dup['cnt']
                print(f"   • {name}: {cnt} ta nusxa")
                
                c.execute("DELETE FROM soups WHERE name = ? AND id != ?", (name, first_id))
                total_deleted += c.rowcount
            
            conn.commit()
            print(f"✅ {total_deleted} ta duplikat o'chirildi!")
        else:
            print("✅ Duplikatlar topilmadi!")
        
        c.execute("PRAGMA table_info(soups)")
        columns = c.fetchall()
        has_unique = False
        for col in columns:
            if col[1] == 'name' and col[4] == 1:
                has_unique = True
                break
        
        if not has_unique:
            print("🔄 UNIQUE constraint qo'shilmoqda...")
            c.execute("ALTER TABLE soups RENAME TO soups_old")
            
            c.execute("""CREATE TABLE soups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                price INTEGER,
                measure TEXT,
                description TEXT
            )""")
            
            c.execute("""
                INSERT INTO soups (name, price, measure, description)
                SELECT DISTINCT name, price, measure, description
                FROM soups_old
                WHERE name IS NOT NULL
            """)
            
            c.execute("DROP TABLE soups_old")
            conn.commit()
            print("✅ UNIQUE constraint qo'shildi!")
        else:
            print("✅ UNIQUE constraint allaqachon mavjud!")
            
    except Exception as e:
        print(f"❌ Xatolik: {e}")
        conn.rollback()


def init_db():
    """
    Ma'lumotlar bazasini yaratish va kerakli jadvallarni yaratish
    """
    time.sleep(1)
    
    fix_all_duplicates()
    
    conn = get_connection()
    c = conn.cursor()
    
    print("📊 Ma'lumotlar bazasi tekshirilmoqda...")
    
    # Foydalanuvchilar jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        name TEXT, 
        phone TEXT, 
        registered_date TEXT, 
        username TEXT, 
        first_name TEXT, 
        last_name TEXT
    )""")
    print("✅ users jadvali yaratildi (yoki mavjud)")
    
    # Xonalar jadvali - TO'G'RI USTUNLAR BILAN
    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        room_number TEXT UNIQUE,
        name TEXT, 
        description TEXT, 
        image TEXT, 
        price INTEGER, 
        capacity INTEGER, 
        type TEXT,
        has_tv INTEGER DEFAULT 1, 
        has_ac INTEGER DEFAULT 1, 
        has_wifi INTEGER DEFAULT 1, 
        has_pool INTEGER DEFAULT 0,
        has_sauna INTEGER DEFAULT 0, 
        has_billiard INTEGER DEFAULT 0,
        has_tennis INTEGER DEFAULT 0, 
        has_tapchan INTEGER DEFAULT 0,
        has_banket INTEGER DEFAULT 0,
        is_available INTEGER DEFAULT 1,
        is_blocked INTEGER DEFAULT 0
    )""")
    print("✅ rooms jadvali yaratildi (yoki mavjud)")
    
    # Xonalarni faqat mavjud bo'lmasa qo'shish
    rooms_data = [
        # Sauna xonalar
        ('2', 'Finskiy sauna', 'Finskiy sauna - 2-xona', 'sauna1.jpg', 1200000, 6, 'sauna', 1, 1, 1, 1, 1, 0, 0, 0, 0),
        ('3', 'Oddiy sauna', 'Oddiy sauna - 3-xona', 'sauna2.jpg', 1200000, 6, 'sauna', 1, 1, 1, 0, 1, 0, 0, 0, 0),
        ('14', 'Tennis xona', 'Stol tennis o\'ynash uchun xona', 'tennis1.jpg', 350000, 4, 'tennis', 1, 1, 1, 0, 0, 0, 1, 0, 0),
        ('15', 'Billiard xona', 'Billiard o\'ynash uchun xona', 'billiard1.jpg', 450000, 8, 'billiard', 1, 1, 1, 0, 0, 1, 0, 0, 0),
        ('16', 'Billiard xona', 'Billiard o\'ynash uchun xona', 'billiard2.jpg', 450000, 8, 'billiard', 1, 1, 1, 0, 0, 1, 0, 0, 0),
        ('18', 'Billiard xona', 'Billiard o\'ynash uchun xona', 'billiard3.jpg', 450000, 8, 'billiard', 1, 1, 1, 0, 0, 1, 0, 0, 0),
        ('9', 'Banket xona', 'Banket zali - 9-xona', 'banket1.jpg', 500000, 20, 'banket', 1, 1, 1, 0, 0, 0, 0, 0, 1),
        ('10', 'Banket xona', 'Banket zali - 10-xona', 'banket2.jpg', 500000, 20, 'banket', 1, 1, 1, 0, 0, 0, 0, 0, 1),
        ('12', 'Banket xona', 'Banket zali - 12-xona', 'banket3.jpg', 500000, 20, 'banket', 1, 1, 1, 0, 0, 0, 0, 0, 1),
        ('13', 'Banket xona', 'Banket zali - 13-xona', 'banket4.jpg', 500000, 20, 'banket', 1, 1, 1, 0, 0, 0, 0, 0, 1),
        ('22', 'Banket xona', 'Banket zali - 22-xona', 'banket5.jpg', 500000, 30, 'banket', 1, 1, 1, 0, 0, 0, 0, 1, 1),
        ('27', 'Banket xona', 'Banket zali - 27-xona', 'banket6.jpg', 500000, 30, 'banket', 1, 1, 1, 0, 0, 0, 0, 1, 1),
        ('28', 'Banket xona', 'Banket zali - 28-xona', 'banket7.jpg', 500000, 30, 'banket', 1, 1, 1, 0, 0, 0, 0, 1, 1),
        ('5', 'Tapchan xona', 'Tapchan xona - 5-xona', 'tapchan1.jpg', 250000, 4, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('7', 'Tapchan xona', 'Tapchan xona - 7-xona', 'tapchan2.jpg', 250000, 4, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('8', 'Tapchan xona', 'Tapchan xona - 8-xona', 'tapchan3.jpg', 250000, 4, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('20', 'Tapchan xona', 'Tapchan xona - 20-xona', 'tapchan4.jpg', 250000, 6, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('21', 'Tapchan xona', 'Tapchan xona - 21-xona', 'tapchan5.jpg', 250000, 6, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('23', 'Tapchan xona', 'Tapchan xona - 23-xona', 'tapchan6.jpg', 250000, 6, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('24', 'Tapchan xona', 'Tapchan xona - 24-xona', 'tapchan7.jpg', 250000, 6, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('25', 'Tapchan xona', 'Tapchan xona - 25-xona', 'tapchan8.jpg', 250000, 6, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
        ('26', 'Tapchan xona', 'Tapchan xona - 26-xona', 'tapchan9.jpg', 250000, 6, 'tapchan', 1, 1, 1, 0, 0, 0, 0, 1, 0),
    ]
    
    for room in rooms_data:
        try:
            c.execute("""INSERT OR IGNORE INTO rooms 
                (room_number, name, description, image, price, capacity, type, 
                 has_tv, has_ac, has_wifi, has_pool, has_sauna, has_billiard, 
                 has_tennis, has_tapchan, has_banket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", room)
        except Exception as e:
            print(f"Xona qo'shishda xatolik: {e}")
    conn.commit()
    print("✅ Xonalar tekshirildi (faqat yangilari qo'shildi)")
    
    # Bronlar jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        user_name TEXT, 
        user_phone TEXT,
        date TEXT, 
        time TEXT, 
        guests INTEGER, 
        room_id INTEGER, 
        room_name TEXT,
        room_price INTEGER, 
        deposit_amount INTEGER, 
        status TEXT, 
        created_date TEXT,
        notification_sent INTEGER DEFAULT 0,
        selected_meals TEXT
    )""")
    print("✅ bookings jadvali yaratildi (yoki mavjud)")
    
    # To'lovlar jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        booking_id INTEGER UNIQUE, 
        deposit_amount INTEGER,
        payment_status TEXT, 
        check_image TEXT, 
        check_file_id TEXT,
        verified INTEGER DEFAULT 0, 
        verified_by_admin INTEGER,
        verified_date TEXT, 
        created_date TEXT
    )""")
    print("✅ payments jadvali yaratildi (yoki mavjud)")
    
    # Suyuq ovqatlar jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS soups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        price INTEGER,
        measure TEXT,
        description TEXT
    )""")
    print("✅ soups jadvali yaratildi (yoki mavjud)")
    
    # Suyuq ovqatlarni faqat mavjud bo'lmasa qo'shish
    soups_data = [
        ('Shorva', 30000, 'kosa', "An'anaviy shorva"),
        ('Mastava', 30000, 'kosa', 'Guruchli shorva'),
        ('Manpar', 30000, 'kosa', 'Uy usulida manpar'),
        ('Moxora', 30000, 'kosa', 'Moxora sho\'rva'),
        ('Kareyka shorva', 40000, 'kosa', 'Maxsus koreyscha shorva')
    ]
    
    for soup in soups_data:
        try:
            c.execute("""INSERT OR IGNORE INTO soups (name, price, measure, description)
                        VALUES (?, ?, ?, ?)""", soup)
        except Exception as e:
            print(f"Suyuq ovqat qo'shishda xatolik: {e}")
    conn.commit()
    print("✅ Suyuq ovqatlar tekshirildi (faqat yangilari qo'shildi)")
    
    # Salatlar jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS salads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        price INTEGER,
        weight TEXT,
        note TEXT,
        category TEXT DEFAULT 'oddiy'
    )""")
    print("✅ salads jadvali yaratildi (yoki mavjud)")
    
    # Salatlarni faqat mavjud bo'lmasa qo'shish
    salads_data = [
        ('Svejiy salat', 30000, None, None, 'oddiy'),
        ('Suzma', 12000, None, None, 'oddiy'),
        ('Achichuk salat', 12000, None, None, 'oddiy'),
        ('Qatiq salat', 12000, None, None, 'oddiy'),
        ('Chiroqchi', 14000, None, None, 'oddiy'),
        ('Mujskoy salat', 90000, '600 gr', '600 gr / 1 portsiya', 'maxsus'),
        ('Yaponskiy', 80000, '600 gr', '600 gr / 1 portsiya', 'maxsus'),
        ('Olivie', 80000, '600 gr', '600 gr / 1 portsiya', 'maxsus'),
        ('Grechiskiy salat', 70000, '600 gr', '600 gr / 1 portsiya', 'maxsus'),
        ('Meysnoy salat', 140000, '600 gr', '600 gr / 1 portsiya', 'maxsus')
    ]
    
    for salad in salads_data:
        try:
            c.execute("""INSERT OR IGNORE INTO salads (name, price, weight, note, category)
                        VALUES (?, ?, ?, ?, ?)""", salad)
        except Exception as e:
            print(f"Salat qo'shishda xatolik: {e}")
    conn.commit()
    print("✅ Salatlar tekshirildi (faqat yangilari qo'shildi)")
    
    # Ovqatlar jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS meals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name_uz TEXT UNIQUE,
        name_ru TEXT UNIQUE,
        price INTEGER,
        category TEXT,
        emoji TEXT,
        description_uz TEXT,
        description_ru TEXT,
        is_available INTEGER DEFAULT 1
    )""")
    print("✅ meals jadvali yaratildi (yoki mavjud)")
    
    add_meals_safe(conn, c)
    
    conn.commit()
    conn.close()
    print("✅ Ma'lumotlar bazasi muvaffaqiyatli tekshirildi!")
    print("=" * 50)


# ==================== ANTI-CLONE MEAL FUNCTIONS ====================

def add_meals_safe(conn, c):
    """Ovqatlarni faqat mavjud bo'lmasa qo'shish"""
    meals = [
        ('Osh', 'Плов', 320000, 'main', '🍚', "An'anaviy o'zbek oshi", 'Традиционный узбекский плов'),
        ('Boyin', 'Шея', 210000, 'meat', '🍖', "Qo'y bo'ynidan tayyorlangan", 'Блюдо из бараньей шеи'),
        ("Qo'l", 'Рулька', 220000, 'meat', '🍗', "Qo'y qo'lidan tayyorlangan", 'Из бараньей рульки'),
        ('Qozon Kabob', 'Казан кебаб', 230000, 'main', '🥘', 'Qozonda pishirilgan kabob', 'Кебаб в казане'),
        ('Choponcha', 'Чапонча', 220000, 'meat', '🥩', "Maxsus usulda tayyorlangan go'sht", 'Мясо особого приготовления'),
        ("Dumg'aza", 'Думгаза', 230000, 'meat', '🍖', "Dumg'aza go'shti", 'Мясо думгазы'),
        ('Dimlama', 'Димлама', 240000, 'main', '🥕', 'Sabzavotlar bilan dimlangan go\'sht', 'Тушеное мясо с овощами'),
        ('Assorti', 'Ассорти', 320000, 'main', '🥩', "Assorti go'shtli (turli xil go'shtlar)", 'Мясное ассорти (разные виды мяса)')
    ]
    
    print("🔄 Ovqatlar tekshirilmoqda...")
    
    for meal in meals:
        try:
            c.execute("""INSERT OR IGNORE INTO meals 
                (name_uz, name_ru, price, category, emoji, description_uz, description_ru, is_available)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)""", meal)
        except Exception as e:
            print(f"Ovqat qo'shishda xatolik: {e}")
    
    print("✅ Ovqatlar tekshirildi (faqat yangilari qo'shildi)")


def add_meal_safe(conn, c, name_uz, name_ru, price, category, emoji, description_uz, description_ru, force=False):
    try:
        c.execute("""
            INSERT OR IGNORE INTO meals 
            (name_uz, name_ru, price, category, emoji, description_uz, description_ru, is_available)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (name_uz, name_ru, price, category, emoji, description_uz, description_ru))
        
        if c.rowcount > 0:
            new_id = c.lastrowid
            print(f"✅ {name_uz} muvaffaqiyatli qo'shildi! (ID: {new_id})")
            return True, new_id
        else:
            c.execute("SELECT id FROM meals WHERE name_uz = ? OR name_ru = ?", (name_uz, name_ru))
            existing = c.fetchone()
            if existing:
                print(f"⚠️  DIQQAT: {name_uz} allaqachon mavjud! (ID: {existing[0]})")
                return False, existing[0]
            return False, None
    except Exception as e:
        print(f"Ovqat qo'shishda xatolik: {e}")
        return False, None


def update_meal_safe(meal_id, **kwargs):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM meals WHERE id = ?", (meal_id,))
    existing = c.fetchone()
    
    if not existing:
        print(f"❌ Xatolik: ID {meal_id} bo'lgan ovqat topilmadi!")
        conn.close()
        return False
    
    allowed_fields = ['name_uz', 'name_ru', 'price', 'category', 'emoji', 
                      'description_uz', 'description_ru', 'is_available']
    
    update_fields = []
    values = []
    
    for field, value in kwargs.items():
        if field in allowed_fields:
            update_fields.append(f"{field} = ?")
            values.append(value)
    
    if not update_fields:
        print("⚠️  Hech qanday maydon yangilanmadi!")
        conn.close()
        return False
    
    query = f"UPDATE meals SET {', '.join(update_fields)} WHERE id = ?"
    values.append(meal_id)
    
    c.execute(query, values)
    conn.commit()
    
    print(f"✅ Ovqat (ID: {meal_id}) muvaffaqiyatli yangilandi!")
    conn.close()
    return True


def get_meal_by_name(name):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM meals 
        WHERE name_uz LIKE ? OR name_ru LIKE ?
        ORDER BY id
    """, (f"%{name}%", f"%{name}%"))
    
    results = c.fetchall()
    conn.close()
    
    fixed_results = []
    for meal in results:
        meal_list = list(meal)
        if len(meal_list) > 3:
            meal_list[3] = fix_value(meal_list[3])
        fixed_results.append(tuple(meal_list))
    
    return fixed_results


def show_all_meals_with_count():
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT name_uz, name_ru, category, price, COUNT(*) as clone_count
        FROM meals
        GROUP BY name_uz
        ORDER BY clone_count DESC, name_uz
    """)
    
    results = c.fetchall()
    conn.close()
    
    print("\n📊 OVQATLAR STATISTIKASI:")
    print("-" * 70)
    print(f"{'Nomi (UZ)':<20} {'Nomi (RU)':<20} {'Kategoriya':<12} {'Narxi':<10} {'Clone soni':<10}")
    print("-" * 70)
    
    for row in results:
        name_uz = row['name_uz']
        name_ru = row['name_ru']
        category = row['category']
        price = fix_value(row['price'])
        count = row['clone_count']
        print(f"{name_uz:<20} {name_ru:<20} {category:<12} {price:<10} {count:<10}")
    
    total = sum([row['clone_count'] for row in results])
    print("-" * 70)
    print(f"Jami ovqatlar: {total} ta")
    print(f"Unikal ovqatlar: {len(results)} ta")


# ==================== USER FUNCTIONS ====================

def add_user(user_id, name, phone, username=None, first_name=None, last_name=None):
    conn = get_connection()
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    existing = c.fetchone()
    
    if existing:
        c.execute("""UPDATE users SET 
                     name = ?, phone = ?, username = ?, first_name = ?, last_name = ?
                     WHERE user_id = ?""",
                  (name, phone, username, first_name, last_name, user_id))
    else:
        c.execute("""INSERT INTO users 
                     (user_id, name, phone, registered_date, username, first_name, last_name) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                  (user_id, name, phone, date, username, first_name, last_name))
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY registered_date DESC")
    result = c.fetchall()
    conn.close()
    return result


# ==================== ROOM FUNCTIONS ====================

def get_rooms():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM rooms ORDER BY price DESC")
    result = c.fetchall()
    conn.close()
    
    fixed_result = [fix_room_data(room) for room in result]
    return fixed_result

def get_room(room_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
    result = c.fetchone()
    conn.close()
    return fix_room_data(result)

def get_room_by_number(room_number):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM rooms WHERE room_number = ?", (room_number,))
    result = c.fetchone()
    conn.close()
    return fix_room_data(result)

def get_filtered_rooms(category_type):
    """Kategoriya bo'yicha xonalarni filterlash - type ustuni bo'yicha"""
    conn = get_connection()
    c = conn.cursor()
    
    # Kategoriya nomlarini type ustuniga moslashtirish
    if category_type == 'banket':
        c.execute("SELECT * FROM rooms WHERE type = 'banket' ORDER BY price DESC")
    elif category_type == 'tapchan':
        c.execute("SELECT * FROM rooms WHERE type = 'tapchan' ORDER BY price DESC")
    elif category_type == 'sauna_pool':
        c.execute("SELECT * FROM rooms WHERE type = 'sauna' ORDER BY price DESC")
    elif category_type == 'tennis':
        c.execute("SELECT * FROM rooms WHERE type = 'tennis' ORDER BY price DESC")
    elif category_type == 'billiard':
        c.execute("SELECT * FROM rooms WHERE type = 'billiard' ORDER BY price DESC")
    else:
        c.execute("SELECT * FROM rooms ORDER BY price DESC")
    
    result = c.fetchall()
    conn.close()
    
    fixed_result = [fix_room_data(room) for room in result]
    return fixed_result

def get_room_advantages(room_id):
    """Xonaning afzalliklarini qaytarish"""
    room = get_room(room_id)
    if not room:
        return ["Afzalliklar mavjud emas"]
    
    advantages = []
    
    if len(room) > 8 and room[8]: advantages.append("✅ Televizor")
    if len(room) > 9 and room[9]: advantages.append("✅ Konditsioner")
    if len(room) > 10 and room[10]: advantages.append("✅ Wi-Fi")
    if len(room) > 11 and room[11]: advantages.append("🏊‍♂️ Basseyn")
    if len(room) > 12 and room[12]: advantages.append("🧖‍♂️ Sauna")
    if len(room) > 13 and room[13]: advantages.append("🎱 Billiard")
    if len(room) > 14 and room[14]: advantages.append("🏓 Stol tennis")
    if len(room) > 15 and room[15]: advantages.append("🪑 Tapchan")
    if len(room) > 16 and room[16]: advantages.append("🎉 Banket zali")
    
    if not advantages:
        advantages.append("✅ Asosiy qulayliklar mavjud")
    
    return advantages

def toggle_room_block(room_id):
    """Xonani band/bo'sh qilish (toggle)"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("SELECT is_blocked FROM rooms WHERE id = ?", (room_id,))
        result = c.fetchone()
        
        if result:
            current_status = result[0] if result[0] is not None else 0
            new_status = 1 if current_status == 0 else 0
            c.execute("UPDATE rooms SET is_blocked = ? WHERE id = ?", (new_status, room_id))
            conn.commit()
            return new_status
        return 0
    except Exception as e:
        print(f"Xona band qilishda xatolik: {e}")
        return 0
    finally:
        conn.close()

def get_room_block_status(room_id):
    """Xonaning band holatini tekshirish"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("SELECT is_blocked FROM rooms WHERE id = ?", (room_id,))
        result = c.fetchone()
        return result[0] if result and result[0] is not None else 0
    except Exception as e:
        print(f"Xona holatini olishda xatolik: {e}")
        return 0
    finally:
        conn.close()

def get_room_by_id(room_id):
    """Xonani ID bo'yicha olish"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        result = c.fetchone()
        if result:
            # Row obyektini tuple ga o'tkazish
            return tuple(result)
        return None
    except Exception as e:
        print(f"Xonani olishda xatolik: {e}")
        return None
    finally:
        conn.close()

def get_all_rooms_with_status():
    """Barcha xonalarni holati bilan olish - TO'G'RILANGAN VERSIYA"""
    import sqlite3
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        # To'g'ridan-to'g'ri SELECT - barcha kerakli ustunlar bilan
        c.execute("""
            SELECT id, room_number, name, description, image, price, capacity, 
                   type, COALESCE(is_blocked, 0) as is_blocked
            FROM rooms 
            ORDER BY CAST(room_number AS INTEGER) ASC
        """)
        result = c.fetchall()
        
        rooms = []
        for row in result:
            rooms.append((
                row[0],  # id
                row[1],  # room_number
                row[2],  # name
                row[3],  # description
                row[4],  # image
                row[5],  # price
                row[6],  # capacity
                row[7],  # type
                row[8]   # is_blocked
            ))
        
        print(f"✅ get_all_rooms_with_status: {len(rooms)} ta xona topildi")
        return rooms
        
    except Exception as e:
        print(f"❌ Xonalarni olishda xatolik: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        conn.close()
# ==================== BOOKING FUNCTIONS ====================

def add_booking(user_id, user_name, user_phone, date, time, guests, room_id, room_name):
    conn = get_connection()
    c = conn.cursor()
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    room = get_room(room_id)
    room_price = 0
    if room and len(room) > 5:
        room_price = fix_value(room[5])
    
    from config import DEPOSIT_PERCENT
    deposit_amount = int(room_price * DEPOSIT_PERCENT / 100)
    
    c.execute("""INSERT INTO bookings 
                 (user_id, user_name, user_phone, date, time, guests, 
                  room_id, room_name, room_price, deposit_amount, status, created_date) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, user_name, user_phone, date, time, guests, 
               room_id, room_name, room_price, deposit_amount, 'pending', created))
    
    conn.commit()
    booking_id = c.lastrowid
    conn.close()
    
    return booking_id, deposit_amount

def get_booking(booking_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        result_list = list(result)
        if len(result_list) > 9:
            result_list[9] = fix_value(result_list[9])
        if len(result_list) > 10:
            result_list[10] = fix_value(result_list[10])
        result = tuple(result_list)
    
    return result

def get_user_bookings(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT * FROM bookings 
                 WHERE user_id = ? 
                 ORDER BY created_date DESC""", (user_id,))
    result = c.fetchall()
    conn.close()
    return result

def get_all_bookings():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT * FROM bookings 
                 ORDER BY created_date DESC""")
    result = c.fetchall()
    conn.close()
    return result

def update_booking_status(booking_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
    conn.commit()
    conn.close()

def check_room_availability(room_id, date, time):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT * FROM bookings 
                 WHERE room_id = ? AND date = ? AND time = ? 
                 AND status IN ('pending', 'confirmed')""",
              (room_id, date, time))
    result = c.fetchone()
    conn.close()
    return result is None

def get_expired_bookings(minutes):
    conn = get_connection()
    c = conn.cursor()
    
    expiry_time = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("""SELECT * FROM bookings 
                 WHERE status = 'pending' 
                 AND created_date < ?
                 AND id NOT IN (SELECT booking_id FROM payments WHERE booking_id IS NOT NULL)""",
              (expiry_time,))
    result = c.fetchall()
    conn.close()
    return result

def update_booking_meals(booking_id, selected_meals_json):
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("UPDATE bookings SET selected_meals = ? WHERE id = ?", 
                  (selected_meals_json, booking_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ovqatlarni saqlashda xatolik: {e}")
        return False
    finally:
        conn.close()

def get_booking_meals(booking_id):
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("SELECT selected_meals FROM bookings WHERE id = ?", (booking_id,))
        result = c.fetchone()
        if result and result[0]:
            return json.loads(result[0])
        return []
    except Exception as e:
        print(f"Ovqatlarni olishda xatolik: {e}")
        return []
    finally:
        conn.close()

def get_today_bookings_for_admin():
    """Bugungi bronlarni admin uchun olish (band xonalar bilan)"""
    conn = get_connection()
    c = conn.cursor()
    
    today = datetime.now().strftime("%d.%m.%Y")
    
    try:
        c.execute("""
            SELECT b.id, b.user_name, b.room_name, b.time, b.guests, b.status,
                   r.is_blocked
            FROM bookings b
            LEFT JOIN rooms r ON b.room_id = r.id
            WHERE b.date = ? AND b.status IN ('pending', 'confirmed')
            ORDER BY b.time
        """, (today,))
        booked_rooms = c.fetchall()
        
        c.execute("""
            SELECT id, room_number, name, type, is_blocked
            FROM rooms
            WHERE is_blocked = 1
        """)
        blocked_rooms = c.fetchall()
        
        return booked_rooms, blocked_rooms
    except Exception as e:
        print(f"Bugungi bronlarni olishda xatolik: {e}")
        return [], []
    finally:
        conn.close()


# ==================== PAYMENT FUNCTIONS ====================

def add_payment(booking_id, deposit_amount, check_file_id):
    conn = get_connection()
    c = conn.cursor()
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("SELECT id FROM payments WHERE booking_id = ?", (booking_id,))
    existing = c.fetchone()
    
    deposit_amount = fix_value(deposit_amount)
    
    if existing:
        c.execute("""UPDATE payments 
                     SET deposit_amount = ?, check_file_id = ?, 
                         payment_status = ?, created_date = ?
                     WHERE booking_id = ?""",
                  (deposit_amount, check_file_id, 'pending', created, booking_id))
    else:
        c.execute("""INSERT INTO payments 
                     (booking_id, deposit_amount, payment_status, check_file_id, created_date) 
                     VALUES (?, ?, ?, ?, ?)""",
                  (booking_id, deposit_amount, 'pending', check_file_id, created))
    
    conn.commit()
    payment_id = c.lastrowid if not existing else existing[0]
    conn.close()
    return payment_id

def get_payment(booking_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE booking_id = ?", (booking_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        result_list = list(result)
        if len(result_list) > 2:
            result_list[2] = fix_value(result_list[2])
        if len(result_list) > 6:
            result_list[6] = fix_value(result_list[6])
        result = tuple(result_list)
    
    return result

def verify_payment(booking_id, verified_by_admin):
    conn = get_connection()
    c = conn.cursor()
    verified_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("""UPDATE payments 
                 SET verified = 1, verified_by_admin = ?, verified_date = ?,
                     payment_status = 'confirmed'
                 WHERE booking_id = ?""",
              (verified_by_admin, verified_date, booking_id))
    
    c.execute("UPDATE bookings SET status = 'confirmed' WHERE id = ?", (booking_id,))
    
    conn.commit()
    conn.close()

def get_unverified_payments():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT p.*, b.user_id, b.user_name, b.room_name, b.date, b.time, b.deposit_amount
                 FROM payments p
                 JOIN bookings b ON p.booking_id = b.id
                 WHERE p.verified = 0
                 ORDER BY p.created_date ASC""")
    result = c.fetchall()
    conn.close()
    return result


# ==================== SOUP FUNCTIONS ====================

def get_soups():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM soups ORDER BY price")
    result = c.fetchall()
    conn.close()
    
    fixed_result = []
    for soup in result:
        soup_list = list(soup)
        if len(soup_list) > 2:
            soup_list[2] = fix_value(soup_list[2])
        fixed_result.append(tuple(soup_list))
    
    return fixed_result


# ==================== SALAD FUNCTIONS ====================

def get_salads():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM salads ORDER BY category, price")
    result = c.fetchall()
    conn.close()
    
    fixed_result = []
    for salad in result:
        salad_list = list(salad)
        if len(salad_list) > 2:
            salad_list[2] = fix_value(salad_list[2])
        fixed_result.append(tuple(salad_list))
    
    return fixed_result

def get_salads_by_category(category):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM salads WHERE category = ? ORDER BY price", (category,))
    result = c.fetchall()
    conn.close()
    
    fixed_result = []
    for salad in result:
        salad_list = list(salad)
        if len(salad_list) > 2:
            salad_list[2] = fix_value(salad_list[2])
        fixed_result.append(tuple(salad_list))
    
    return fixed_result


# ==================== MEAL FUNCTIONS ====================

def get_meals():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM meals WHERE is_available = 1 ORDER BY category, price")
    result = c.fetchall()
    conn.close()
    
    fixed_result = []
    for meal in result:
        meal_list = list(meal)
        if len(meal_list) > 3:
            meal_list[3] = fix_value(meal_list[3])
        fixed_result.append(tuple(meal_list))
    
    return fixed_result

def get_meal_by_id(meal_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM meals WHERE id = ?", (meal_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        result_list = list(result)
        if len(result_list) > 3:
            result_list[3] = fix_value(result_list[3])
        result = tuple(result_list)
    
    return result

def get_meals_by_category(category):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM meals WHERE category = ? AND is_available = 1 ORDER BY price", (category,))
    result = c.fetchall()
    conn.close()
    
    fixed_result = []
    for meal in result:
        meal_list = list(meal)
        if len(meal_list) > 3:
            meal_list[3] = fix_value(meal_list[3])
        fixed_result.append(tuple(meal_list))
    
    return fixed_result


# ==================== STATISTICS FUNCTIONS ====================

def get_statistics():
    conn = get_connection()
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    stats = {
        'total_users': 0,
        'today_users': 0,
        'total_bookings': 0,
        'today_bookings': 0,
        'pending_bookings': 0,
        'confirmed_bookings': 0,
        'cancelled_bookings': 0,
        'rejected_bookings': 0,
        'total_payments': 0,
        'unverified_payments': 0,
        'total_deposits': 0
    }
    
    try:
        c.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM users WHERE registered_date LIKE ?", (f"{today}%",))
        stats['today_users'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM bookings")
        stats['total_bookings'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM bookings WHERE date = ?", (today,))
        stats['today_bookings'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM bookings WHERE status = 'pending'")
        stats['pending_bookings'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM bookings WHERE status = 'confirmed'")
        stats['confirmed_bookings'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM bookings WHERE status = 'cancelled'")
        stats['cancelled_bookings'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM bookings WHERE status = 'rejected'")
        stats['rejected_bookings'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM payments")
        stats['total_payments'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT COUNT(*) FROM payments WHERE verified = 0")
        stats['unverified_payments'] = c.fetchone()[0] or 0
    except: pass
    
    try:
        c.execute("SELECT SUM(deposit_amount) FROM bookings WHERE status = 'confirmed'")
        total = c.fetchone()[0]
        stats['total_deposits'] = total if total else 0
    except: pass
    
    conn.close()
    return stats


# ==================== ROOM BLOCKING FUNCTIONS ====================

def add_room_blocked_column():
    """rooms jadvaliga is_blocked ustunini qo'shish"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("PRAGMA table_info(rooms)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'is_blocked' not in columns:
            c.execute("ALTER TABLE rooms ADD COLUMN is_blocked INTEGER DEFAULT 0")
            print("✅ rooms jadvaliga is_blocked ustuni qo'shildi")
        
        conn.commit()
    except Exception as e:
        print(f"❌ is_blocked ustunini qo'shishda xatolik: {e}")
    finally:
        conn.close()


def add_selected_meals_to_bookings():
    """bookings jadvaliga selected_meals ustunini qo'shish"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute("PRAGMA table_info(bookings)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'selected_meals' not in columns:
            c.execute("ALTER TABLE bookings ADD COLUMN selected_meals TEXT")
            print("✅ bookings jadvaliga selected_meals ustuni qo'shildi")
        
        conn.commit()
    except Exception as e:
        print(f"❌ selected_meals ustunini qo'shishda xatolik: {e}")
    finally:
        conn.close()


# ==================== BAZANI ISHGA TUSHIRISH ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🗄️  MA'LUMOTLAR BAZASI YARATILMOQDA...")
    print("=" * 50)
    init_db()
    print("\n✅ Baza muvaffaqiyatli yaratildi!")
    print("📁 Fayl nomi: choyxona.db")
    
    print("\n" + "=" * 50)
    print("🔍 OVQATLAR HOLATI TEKSHIRILMOQDA...")
    print("=" * 50)
    show_all_meals_with_count()