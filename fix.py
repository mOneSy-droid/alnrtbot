import sqlite3

def fix_database():
    db_name = 'choyxona.db'
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    try:
        print("Jarayon boshlandi...")

        # 1. Mavjud ma'lumotlarni o'qib olamiz
        cursor.execute("SELECT room_number, name, description, image, price, capacity, type FROM rooms")
        rows = cursor.fetchall()
        
        # 2. Xona raqami bo'yicha raqamli saralaymiz (2, 3, 5, 7, 8, 9, 10...)
        sorted_rows = sorted(rows, key=lambda x: int(x[0]))

        # 3. Jadvalni butunlay o'chirib tashlaymiz (ID hisoblagichini nol qilish uchun)
        cursor.execute("DROP TABLE IF EXISTS rooms")

        # 4. Jadvalni xuddi o'zidek qayta yaratamiz
        cursor.execute("""
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                room_number TEXT,
                name TEXT,
                description TEXT,
                image TEXT,
                price INTEGER,
                capacity INTEGER,
                type TEXT
            )
        """)

        # 5. Ma'lumotlarni yangitdan, to'g'ri ID bilan joylaymiz
        for row in sorted_rows:
            room_id = int(row[0]) # ID endi aynan room_number ga teng bo'ladi
            
            sql = """INSERT INTO rooms (id, room_number, name, description, image, price, capacity, type) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            cursor.execute(sql, (room_id, *row))

        conn.commit()
        print("Muvaffaqiyatli yakunlandi! Endi ID va Room_number bir xil.")

    except Exception as e:
        conn.rollback()
        print(f"Xatolik: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()