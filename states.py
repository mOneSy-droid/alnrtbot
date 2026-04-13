# states.py
from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    """Ro'yxatdan o'tish holatlari"""
    name = State()
    phone = State()

class Booking(StatesGroup):
    """Bron qilish holatlari"""
    name = State()
    phone = State()
    date = State()
    time = State()
    guests = State()
    confirm = State()

class AdminStates(StatesGroup):
    """Admin panel holatlari"""
    menu = State()
    
    # Xona qo'shish
    add_room_name = State()
    add_room_description = State()
    add_room_price = State()
    add_room_capacity = State()
    add_room_image = State()
    add_room_features = State()
    add_room_confirm = State()
    
    # Xabar yuborish
    mailing_text = State()
    mailing_confirm = State()
    mailing_with_image = State()
    mailing_image = State()
    
    # Bronni boshqarish
    booking_action = State()

class CheckStates(StatesGroup):
    """Chek tekshirish holatlari"""
    waiting_for_check = State()
    verify_check = State()