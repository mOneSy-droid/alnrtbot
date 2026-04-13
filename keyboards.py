# keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

# ==================== ASOSIY MENYU ====================

def main_menu():
    """Foydalanuvchi uchun asosiy menyu"""
    buttons = [
        [KeyboardButton(text="🏠 Bron qilish"), KeyboardButton(text="🏢 Xonalarimiz")],
        [KeyboardButton(text="🍽 Ovqatlarimiz"), KeyboardButton(text="📍 Manzilimiz")],
        [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="ℹ️ Biz haqimizda")],
        [KeyboardButton(text="⭐ Fikr bildirish")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_main_menu():
    """Admin uchun asosiy menyu"""
    buttons = [
        [KeyboardButton(text="🏠 Bron qilish"), KeyboardButton(text="🏢 Xonalarimiz")],
        [KeyboardButton(text="🍽 Ovqatlarimiz"), KeyboardButton(text="📍 Manzilimiz")],
        [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="ℹ️ Biz haqimizda")],
        [KeyboardButton(text="👑 Admin panel"), KeyboardButton(text="⭐ Fikr bildirish")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ==================== ADMIN PANEL ====================

def admin_panel_keyboard():
    """Admin panel uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="💳 Zakladlar", callback_data="admin_deposits"))
    builder.row(InlineKeyboardButton(text="🏠 Xonalarni band qilish", callback_data="admin_block_rooms"))
    builder.row(InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="📅 Bronlar", callback_data="admin_bookings"))
    builder.row(InlineKeyboardButton(text="🚪 Chiqish", callback_data="admin_logout"))
    return builder.as_markup()

def admin_back_keyboard():
    """Admin panelda orqaga qaytish"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back"))
    return builder.as_markup()

def admin_deposits_keyboard(unverified_payments):
    """Tekshirilmagan zakladlar ro'yxati"""
    builder = InlineKeyboardBuilder()
    
    for payment in unverified_payments[:10]:  # 10 tadan ko'p bo'lmasin
        booking_id = payment[1]  # booking_id
        user_name = payment[11] if len(payment) > 11 else "Noma'lum"  # user_name
        amount = payment[2]  # deposit_amount
        
        # Narxni formatlash (vergulsiz)
        amount_str = f"{amount:,}".replace(",", " ")
        button_text = f"#{booking_id} - {user_name[:15]} | {amount_str} so'm"
        builder.row(InlineKeyboardButton(
            text=button_text,
            callback_data=f"admin_deposit_{booking_id}"
        ))
    
    builder.row(
        InlineKeyboardButton(text="🔄 Yangilash", callback_data="admin_deposits_refresh"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")
    )
    return builder.as_markup()

def admin_deposit_detail_keyboard(booking_id):
    """Zaklad detali uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_verify_deposit_{booking_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_reject_deposit_{booking_id}")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_deposits"))
    return builder.as_markup()

# ==================== XONALAR ====================

def room_categories_keyboard():
    """Xona kategoriyalari uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎉 Banket", callback_data="room_cat_banket"),
        InlineKeyboardButton(text="🪑 Tapchan", callback_data="room_cat_tapchan")
    )
    builder.row(
        InlineKeyboardButton(text="🏊‍♂️ Sauna/Basseyn", callback_data="room_cat_sauna_pool"),
        InlineKeyboardButton(text="🏓 Tennis", callback_data="room_cat_tennis")
    )
    builder.row(
        InlineKeyboardButton(text="🎱 Billiard", callback_data="room_cat_billiard"),
        InlineKeyboardButton(text="🏢 Hammasi", callback_data="room_cat_all")
    )
    return builder.as_markup()

def filtered_rooms_keyboard(rooms, category_type):
    """Filterlangan xonalar ro'yxati"""
    builder = InlineKeyboardBuilder()
    
    for room in rooms:
        room_id = room[0]
        room_number = room[1] if len(room) > 1 else "Noma'lum"
        room_name = room[2][:20] + "..." if len(room[2]) > 20 else room[2]
        price = room[5] if len(room) > 5 else 0
        
        # Narxni formatlash (vergul o'rniga bo'sh joy)
        price_str = f"{price:,}".replace(",", " ")
        button_text = f"Xona {room_number} - {room_name} | {price_str} so'm"
        
        builder.row(InlineKeyboardButton(
            text=button_text,
            callback_data=f"room_{room_id}"
        ))
    
    builder.row(InlineKeyboardButton(
        text="⬅️ Orqaga",
        callback_data="back_to_room_cats"
    ))
    return builder.as_markup()

def room_detail_keyboard(room_id):
    """Xona detali uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📝 Bron qilish",
        callback_data=f"book_room_{room_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="⬅️ Orqaga",
        callback_data="back_to_room_cats"
    ))
    return builder.as_markup()

# ==================== BRON QILISH ====================

def date_pagination_keyboard(year, month, page=1):
    """Sana tanlash uchun kalendar"""
    builder = InlineKeyboardBuilder()
    
    months_uz = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
                 "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
    
    header = f"{months_uz[month-1]} {year}"
    
    # Hafta kunlari
    week_days = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
    week_buttons = []
    for day in week_days:
        week_buttons.append(InlineKeyboardButton(text=day, callback_data="ignore"))
    builder.row(*week_buttons)
    
    # Kunlar
    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()  # 0-Dushanba
    
    # Bo'sh kataklar
    buttons = []
    for _ in range(start_weekday):
        buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    # Oy kunlari
    if month == 12:
        next_month = datetime(year+1, 1, 1)
    else:
        next_month = datetime(year, month+1, 1)
    
    last_day = (next_month - timedelta(days=1)).day
    
    for day in range(1, last_day + 1):
        date_str = f"{day:02d}.{month:02d}.{year}"
        buttons.append(InlineKeyboardButton(
            text=str(day),
            callback_data=f"date_{date_str}"
        ))
    
    # Qatorlarga ajratish
    for i in range(0, len(buttons), 7):
        builder.row(*buttons[i:i+7])
    
    # Navigatsiya
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"date_page_{page-1}_{year}_{month}"
        ))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"{month}/{year}", callback_data="ignore"))
    
    # Keyingi oy
    if month == 12:
        next_year = year + 1
        next_month = 1
    else:
        next_year = year
        next_month = month + 1
    
    nav_buttons.append(InlineKeyboardButton(
        text="➡️",
        callback_data=f"date_page_{page+1}_{next_year}_{next_month}"
    ))
    
    builder.row(*nav_buttons)
    
    return builder.as_markup(), header

def booking_confirm_keyboard(room_price, deposit):
    """Bronni tasdiqlash uchun keyboard"""
    builder = InlineKeyboardBuilder()
    
    # Narxlarni formatlash
    price_str = f"{room_price:,}".replace(",", " ")
    deposit_str = f"{deposit:,}".replace(",", " ")
    
    builder.row(InlineKeyboardButton(
        text=f"✅ Tasdiqlash ({deposit_str} so'm)",
        callback_data="confirm_booking"
    ))
    builder.row(InlineKeyboardButton(
        text="❌ Bekor qilish",
        callback_data="cancel_booking"
    ))
    return builder.as_markup()

def cart_with_payment_keyboard(booking_id, total_payment):
    """Savat + to'lov tugmalari"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    # callback_data format: pay_from_meals_TYPE_ID
    builder.row(InlineKeyboardButton(text="💳 Payme orqali to'lash", callback_data=f"pay_from_meals_payme_{booking_id}"))
    builder.row(InlineKeyboardButton(text="💳 Karta orqali to'lash", callback_data=f"pay_from_meals_card_{booking_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Ovqatlar menyusiga qaytish", callback_data=f"add_meals_{booking_id}"))
    builder.row(InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="main_menu"))
    
    return builder.as_markup()

def meals_with_payment_keyboard(meals, booking_id, selected_meals, total_payment):
    """Ovqat menyusi + to'lov tugmalari"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    
    # Ovqatlar ro'yxati
    for meal in meals:
        emoji = meal[5] if meal[5] else "🍽"
        if meal[0] in selected_meals:
            text = f"✅ {emoji} {meal[1]} - {meal[3]:,} so'm"
        else:
            text = f"{emoji} {meal[1]} - {meal[3]:,} so'm"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"select_meal_{meal[0]}_{booking_id}"))
    
    # To'lov tugmalari (callback_data format: pay_from_meals_TYPE_ID)
    builder.row(InlineKeyboardButton(text="🛒 Savatni ko'rish", callback_data=f"view_cart_{booking_id}"))
    builder.row(InlineKeyboardButton(text="💳 Payme orqali to'lash", callback_data=f"pay_from_meals_payme_{booking_id}"))
    builder.row(InlineKeyboardButton(text="💳 Karta orqali to'lash", callback_data=f"pay_from_meals_card_{booking_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_payment_{booking_id}"))
    
    return builder.as_markup()

def booking_payment_keyboard(booking_id):
    """Bron qilingandan keyin to'lov keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Payme orqali to'lash", callback_data=f"pay_payme_{booking_id}"))
    builder.row(InlineKeyboardButton(text="💳 Karta orqali to'lash", callback_data=f"pay_card_{booking_id}"))
    builder.row(InlineKeyboardButton(text="🍽 Ovqat qo'shish", callback_data=f"add_meals_{booking_id}"))
    builder.row(InlineKeyboardButton(text="❌ Bronni bekor qilish", callback_data="cancel_booking"))
    return builder.as_markup()

def payment_keyboard(booking_id):
    """Chek yuborish uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Payme orqali to'lash", callback_data=f"pay_payme_{booking_id}"))
    builder.row(InlineKeyboardButton(text="💳 Karta orqali to'lash", callback_data=f"pay_card_{booking_id}"))
    builder.row(InlineKeyboardButton(text="🍽 Ovqat qo'shish", callback_data=f"add_meals_{booking_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_payment_{booking_id}"))
    return builder.as_markup()

def booking_confirmed_keyboard(booking_id):
    """Bron tasdiqlangandan keyin"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🏠 Bosh menyu",
        callback_data="main_menu"
    ))
    return builder.as_markup()

# ==================== OVQATLAR ====================

def meals_menu_keyboard(meals, booking_id, selected_meals=None):
    """Ovqatlar menyusi uchun keyboard"""
    if selected_meals is None:
        selected_meals = []
    
    builder = InlineKeyboardBuilder()
    
    categories = {
        'main': '🍚 ASOSIY',
        'meat': '🍖 GO\'SHT',
        'salad': '🥗 SALAT'
    }
    
    for category, title in categories.items():
        category_meals = [m for m in meals if m[4] == category]
        if category_meals:
            # Kategoriya sarlavhasi
            builder.row(InlineKeyboardButton(
                text=f"📌 {title}",
                callback_data="ignore"
            ))
            
            # Kategoriyadagi ovqatlar
            for meal in category_meals:
                meal_id = meal[0]
                meal_name = meal[1]
                meal_price = meal[3]
                emoji = meal[5] if len(meal) > 5 else "🍽"
                
                # Narxni formatlash
                price_str = f"{meal_price:,}".replace(",", " ")
                
                if meal_id in selected_meals:
                    button_text = f"✅ {emoji} {meal_name} - {price_str} so'm"
                else:
                    button_text = f"{emoji} {meal_name} - {price_str} so'm"
                
                builder.row(InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"select_meal_{meal_id}_{booking_id}"
                ))
    
    # Savat va orqaga
    builder.row(
        InlineKeyboardButton(text="🛒 Savatni ko'rish", callback_data=f"view_cart_{booking_id}"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_payment_{booking_id}")
    )
    
    return builder.as_markup()

def cart_keyboard(booking_id):
    """Savat uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_meals_{booking_id}"),
        InlineKeyboardButton(text="✅ Yakunlash", callback_data=f"final_confirm_{booking_id}")
    )
    return builder.as_markup()

# ==================== FIKR BILDIRISH ====================

def feedback_keyboard():
    """Fikr bildirish uchun keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⭐", callback_data="feedback_1"),
        InlineKeyboardButton(text="⭐⭐", callback_data="feedback_2"),
        InlineKeyboardButton(text="⭐⭐⭐", callback_data="feedback_3"),
        InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="feedback_4"),
        InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="feedback_5")
    )
    builder.row(InlineKeyboardButton(
        text="⬅️ Orqaga",
        callback_data="main_menu"
    ))
    return builder.as_markup()

# ==================== UMUMIY ====================

def back_to_main_keyboard():
    """Bosh menyuga qaytish"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🏠 Bosh menyu",
        callback_data="main_menu"
    ))
    return builder.as_markup()

def remove_keyboard():
    """Keyboardni olib tashlash"""
    from aiogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()

def phone_request():
    """Telefon raqam so'rash uchun keyboard"""
    buttons = [
        [KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)],
        [KeyboardButton(text="⬅️ Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)