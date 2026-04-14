import asyncio
import os
import logging
import re
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fix import fix_database

from config import (
    BOT_TOKEN, ADMIN_IDS, DB_NAME, CHAYXONA_NAME, CHAYXONA_ADDRESS,     
    LATITUDE, LONGITUDE, CONTACT_PHONE,
    AUTO_CANCEL_MINUTES, DEPOSIT_PERCENT, IMAGES_PATH, PAYME_LINK
)
from database import (
    init_db, get_user, add_user, get_filtered_rooms, get_room,
    get_room_advantages, check_room_availability, add_booking,
    get_booking, get_expired_bookings, update_booking_status,
    add_payment, get_payment, get_unverified_payments, verify_payment,
    get_statistics, get_all_users, get_all_bookings, get_meals, get_meal_by_id,
    add_room_blocked_column, add_selected_meals_to_bookings, toggle_room_block,
    get_room_block_status, get_all_rooms_with_status, get_room_by_id,
    get_today_bookings_for_admin, update_booking_meals , 
)
from states import Registration, Booking, CheckStates
from keyboards import (
    main_menu, admin_main_menu, room_categories_keyboard,
    filtered_rooms_keyboard, room_detail_keyboard, back_to_main_keyboard,
    date_pagination_keyboard,
    feedback_keyboard, admin_panel_keyboard, admin_back_keyboard,
    admin_deposits_keyboard, admin_deposit_detail_keyboard, phone_request, booking_payment_keyboard, payment_keyboard,
    booking_confirmed_keyboard, meals_with_payment_keyboard, cart_with_payment_keyboard
)

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

dp = Dispatcher(storage=MemoryStorage())

MAIN_MENU_TEXTS = {
    "🏠 Bron qilish",
    "🍽 Ovqatlarimiz",
    "🏢 Xonalarimiz",
    "📍 Manzilimiz",
    "📞 Aloqa",
    "ℹ️ Biz haqimizda",
    "⭐ Fikr bildirish",
    "👑 Admin panel",
}

def get_user_greeting(user):
    if user and user[1]:
        return user[1]
    elif user and user[4]:
        return f"@{user[4]}"
    return "mehmon"


async def notify_admin(message_text: str, photo=None, room_name=None):
    if not ADMIN_IDS:
        return
    for admin_id in ADMIN_IDS:
        try:
            if photo:
                await bot.send_photo(admin_id, photo=photo, caption=message_text)
            elif room_name:
                await bot.send_message(admin_id, f"🏢 <b>Xona: {room_name}</b>\n\n{message_text}")
            else:
                await bot.send_message(admin_id, message_text)
        except Exception as e:
            logger.error(f"Admin xabar yuborishda xatolik: {e}")


def validate_date(date_str):
    pattern_short = r'^(0[1-9]|[12][0-9]|3[01])\.(0[1-9]|1[012])\.(\d{2})$'
    pattern_long = r'^(0[1-9]|[12][0-9]|3[01])\.(0[1-9]|1[012])\.(20\d{2})$'

    if re.match(pattern_short, date_str):
        day, month, year_short = map(int, date_str.split('.'))
        if 24 <= year_short <= 27:
            year = 2000 + year_short
        else:
            return False
    elif re.match(pattern_long, date_str):
        day, month, year = map(int, date_str.split('.'))
        if year < 2024 or year > 2027:
            return False
    else:
        return False

    try:
        input_date = datetime(year, month, day)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return input_date >= today
    except ValueError:
        return False


def validate_time(time_str):
    return bool(re.match(r'^([01][0-9]|2[0-3]):([0-5][0-9])$', time_str))


def parse_price(price_value):
    try:
        if isinstance(price_value, str):
            price_value = price_value.replace(',', '').replace(' ', '')
        return int(price_value)
    except (ValueError, TypeError):
        logger.error(f"Narxni o'qishda xatolik: {price_value}")
        return 200000


def get_appropriate_menu(user_id: int):
    return admin_main_menu() if user_id in ADMIN_IDS else main_menu()


async def send_main_menu(message: Message, text: str = None):
    await message.answer(
        text or "🏠 <b>Bosh menyu</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=get_appropriate_menu(message.from_user.id)
    )


async def auto_cancel_expired_bookings():
    while True:
        try:
            expired_bookings = get_expired_bookings(AUTO_CANCEL_MINUTES)
            for booking in expired_bookings:
                booking_id = booking[0]
                user_id = booking[1]
                update_booking_status(booking_id, 'cancelled')
                try:
                    await bot.send_message(
                        user_id,
                        f"❌ <b>Bron bekor qilindi</b>\n\n"
                        f"Siz zaklad to'lovini {AUTO_CANCEL_MINUTES} daqiqa ichida qilmaganingiz "
                        f"uchun bron #{booking_id} bekor qilindi.\n\n"
                        f"Qaytadan bron qilish uchun /start buyrug'ini bosing."
                    )
                    await notify_admin(
                        f"⏰ <b>Avtomatik bekor qilish</b>\n\n"
                        f"Bron #{booking_id} {AUTO_CANCEL_MINUTES} daqiqa ichida "
                        f"to'lov qilinmagani uchun bekor qilindi."
                    )
                except Exception as e:
                    logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Auto-cancel xatolik: {e}")
            await asyncio.sleep(60)


# ==================== SCHEDULER FUNCTIONS ====================

scheduler = AsyncIOScheduler()

async def send_daily_booking_report():
    """Har kuni 09:00 da adminlarga bugungi band xonalar haqida xabar yuborish"""
    if not ADMIN_IDS:
        return
    
    booked_rooms, blocked_rooms = get_today_bookings_for_admin()
    
    message = "📅 <b>Bugungi kun uchun band xonalar</b>\n\n"
    message += f"📆 Sana: {datetime.now().strftime('%d.%m.%Y')}\n"
    message += "━" * 30 + "\n\n"
    
    if booked_rooms or blocked_rooms:
        if blocked_rooms:
            message += "🚫 <b>Admin tomonidan band qilingan xonalar:</b>\n"
            for room in blocked_rooms:
                message += f"  • 🏠 Xona #{room[0]} - {room[2]} ({room[3]})\n"
            message += "\n"
        
        if booked_rooms:
            message += "👥 <b>Mijozlar bron qilgan xonalar:</b>\n"
            for booking in booked_rooms:
                status_emoji = "✅" if booking[5] == "confirmed" else "⏳"
                message += f"  {status_emoji} {booking[2]} | {booking[3]} | {booking[1]} | {booking[4]} kishi\n"
            message += "\n"
    else:
        message += "✨ <b>Bugun hech qanday xona band emas!</b>\n\n"
        message += "<i>Barcha xonalar bo'sh, mijozlarni kutmoqda 😊</i>\n"
    
    message += "━" * 30 + "\n"
    message += f"📊 <b>Jami band xonalar:</b> {len(booked_rooms) + len(blocked_rooms)} ta"
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message)
        except Exception as e:
            logger.error(f"Admin {admin_id} ga xabar yuborishda xatolik: {e}")


def start_scheduler():
    """Schedulerni ishga tushirish"""
    scheduler.add_job(send_daily_booking_report, 'cron', hour=9, minute=0)
    scheduler.start()
    logger.info("✅ Scheduler ishga tushdi (09:00 da admin eslatma)")


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = get_user(user_id)
    

    if user:
        name = get_user_greeting(user)

        photo = "AgACAgIAAxkDAAIEomnIwVo1GYb2_SstYZdRNqfbXRoCAALEFGsbl99BStNH5b0AAWlu8gEAAwIAA3cAAzoE"

        await message.answer_photo(
        photo=photo,
        caption=(
            f"✨ <b>Assalomu alaykum, {name}!</b> ✨\n\n"
            f"<b>{CHAYXONA_NAME}</b> ga xush kelibsiz!\n\n"
            f"Quyidagi menyulardan birini tanlang:"
        ),
        reply_markup=get_appropriate_menu(user_id)
    )
    else:
        await state.set_state(Registration.name)
        if message.from_user.first_name:
            full_name = message.from_user.first_name
            if message.from_user.last_name:
                full_name += f" {message.from_user.last_name}"
            await state.update_data(name=full_name)

        await message.answer(
            f"🌟 <b>Assalomu alaykum! {CHAYXONA_NAME} ga xush kelibsiz!</b> 🌟\n\n"
            f"<i>{CHAYXONA_ADDRESS}</i>\n\n"
            f"Botdan to'liq foydalanish uchun ro'yxatdan o'tishingiz kerak.\n"
            f"Ismingizni kiriting (masalan: Alisher):",
            reply_markup=types.ReplyKeyboardRemove()
        )


@dp.message(StateFilter(None), F.text.in_(MAIN_MENU_TEXTS))
async def menu_guard_no_state(message: Message, state: FSMContext):
    await route_menu_message(message, state)


@dp.message(~StateFilter(None), F.text.in_(MAIN_MENU_TEXTS))
async def menu_interrupt_fsm(message: Message, state: FSMContext):
    await state.clear()
    await route_menu_message(message, state)


async def route_menu_message(message: Message, state: FSMContext):
    text = message.text

    if text == "🏠 Bron qilish":
        await message.answer(
            "🏢 <b>Xona kategoriyasini tanlang</b>\n\nQuyidagi kategoriyalardan birini tanlang:",
            reply_markup=room_categories_keyboard()
        )
    elif text == "🍽 Ovqatlarimiz":
        await handle_show_meals(message)
    elif text == "🏢 Xonalarimiz":
        await message.answer(
            "🏢 <b>Xonalarimiz</b>\n\nKategoriya bo'yicha tanlang:",
            reply_markup=room_categories_keyboard()
        )
    elif text == "📍 Manzilimiz":
        await handle_show_location(message)
    elif text == "📞 Aloqa":
        await handle_show_contact(message)
    elif text == "ℹ️ Biz haqimizda":
        await handle_show_info(message)
    elif text == "⭐ Fikr bildirish":
        await message.answer(
            "⭐ <b>Fikr bildirish</b>\n\nBiz uchun sizning fikringiz juda muhim!\n"
            "Iltimos, xizmatimizga baho bering:",
            reply_markup=feedback_keyboard()
        )
    elif text == "👑 Admin panel":
        await handle_admin_panel_message(message)


@dp.message(Registration.name)
async def reg_name(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    if len(message.text) > 50 or len(message.text) < 2:
        await message.answer("❌ Ism 2-50 belgidan iborat bo'lishi kerak.")
        return

    await state.update_data(name=message.text)
    await state.set_state(Registration.phone)
    await message.answer(
        "📞 <b>Telefon raqamingizni yuboring</b>\n\nQuyidagi tugmani bosib raqamingizni jo'nating:",
        reply_markup=phone_request()
    )


@dp.message(Registration.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    add_user(
        user_id=message.from_user.id,
        name=data.get('name', message.from_user.first_name),
        phone=message.contact.phone_number,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    await notify_admin(
        f"🆕 <b>Yangi foydalanuvchi!</b>\n\n"
        f"👤 <b>Ism:</b> {data.get('name')}\n"
        f"📞 <b>Telefon:</b> {message.contact.phone_number}\n"
        f"🆔 <b>User ID:</b> {message.from_user.id}\n"
        f"📱 <b>Username:</b> @{message.from_user.username if message.from_user.username else 'yo\'q'}"
    )
    await state.clear()
    await message.answer(
        f"✅ <b>Tabriklaymiz! Ro'yxatdan o'tdingiz!</b>\n\n"
        f"👤 <b>Ism:</b> {data.get('name')}\n"
        f"📞 <b>Telefon:</b> {message.contact.phone_number}\n\n"
        f"🏢 <b>Xonalar:</b> Banket, Tapchan, Sauna, Billiard, Tennis\n"
        f"🍽 <b>Taomlar:</b> 20+ xil milliy taomlar\n\n"
        f"Marhamat, menyulardan birini tanlang:",
        reply_markup=get_appropriate_menu(message.from_user.id)
    )


@dp.message(Registration.phone)
async def reg_phone_text(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    phone = message.text.strip()
    if not phone.startswith('+') or len(phone) < 9:
        await message.answer("❌ Noto'g'ri format. Iltimos, +998901234567 formatida yozing yoki tugmani bosing.")
        return

    data = await state.get_data()
    add_user(
        user_id=message.from_user.id,
        name=data.get('name', message.from_user.first_name),
        phone=phone,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    await notify_admin(
        f"🆕 <b>Yangi foydalanuvchi!</b>\n\n"
        f"👤 <b>Ism:</b> {data.get('name')}\n"
        f"📞 <b>Telefon:</b> {phone}\n"
        f"🆔 <b>User ID:</b> {message.from_user.id}"
    )
    await state.clear()
    await message.answer(
        f"✅ <b>Tabriklaymiz! Ro'yxatdan o'tdingiz!</b>\n\n"
        f"👤 <b>Ism:</b> {data.get('name')}\n"
        f"📞 <b>Telefon:</b> {phone}\n\n"
        f"Marhamat, menyulardan birini tanlang:",
        reply_markup=get_appropriate_menu(message.from_user.id)
    )


@dp.callback_query(lambda c: c.data.startswith("room_cat_"))
async def show_filtered_rooms(callback: CallbackQuery):
    category_type = callback.data.replace("room_cat_", "")
    category_names = {
        'banket': '🎉 Banket zallar',
        'tapchan': '🪑 Tapchan xonalar',
        'sauna_pool': '🏊‍♂️ Sauna/Basseyn',
        'tennis': '🏓 Tennis xonalar',
        'billiard': '🎱 Billiard xonalar',
        'all': '🏢 Barcha xonalar'
    }
    category_name = category_names.get(category_type, 'Xonalar')
    rooms = get_filtered_rooms(category_type)
    if not rooms:
        await callback.answer("Bu kategoriyada xonalar mavjud emas")
        return
    await callback.message.edit_text(
        f"🏢 <b>{category_name}</b>\n\n{len(rooms)} ta xona mavjud:\n\nQuyidagilardan birini tanlang:",
        reply_markup=filtered_rooms_keyboard(rooms, category_type)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("room_") and not c.data.startswith("room_cat_"))
async def show_room_detail(callback: CallbackQuery):
    try:
        room_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("Xatolik yuz berdi")
        return

    room = get_room(room_id)
    if not room:
        await callback.answer("Xona topilmadi")
        return

    # ========== YANGI: XONA BANDLIGINI TEKSHIRISH (BRON BOSHLASH OLDIDAN) ==========
    from database import get_room_block_status
    is_blocked = get_room_block_status(room_id)
    
    if is_blocked:
        # Xona admin tomonidan band qilingan
        await callback.message.delete()
        await callback.message.answer(
            f"🚫 <b>Xona #{room_id} - {room[2]}</b>\n\n"
            f"❌ <b>Kechirasiz, bu xona hozirda band qilingan!</b>\n\n"
            f"📌 <b>Holat:</b> 🔴 Admin tomonidan band qilingan\n\n"
            f"<i>Iltimos, boshqa xonalardan birini tanlang.</i>",
            reply_markup=back_to_main_keyboard()
        )
        await callback.answer("❌ Bu xona band qilingan!", show_alert=True)
        return
    # ========== TEKSHIRUV TUGADI ==========

    room_price_int = parse_price(room[5])
    deposit = int(room_price_int * DEPOSIT_PERCENT / 100)

    type_flags = [
        (11, "🏊‍♂️ Basseyn"),
        (12, "🧖‍♂️ Sauna"),
        (13, "🎱 Billiard"),
        (14, "🏓 Stol tennis"),
        (15, "🪑 Tapchan"),
        (16, "🎉 Banket zali"),
    ]
    room_types = []
    for idx, label in type_flags:
        if len(room) > idx and room[idx] and str(room[idx]).lower() in ['true', '1', 'yes']:
            room_types.append(label)

    room_type_text = " + ".join(room_types) if room_types else "Standart xona"
    advantages = get_room_advantages(room_id)
    advantages_text = "\n".join(advantages) if advantages else "✅ Asosiy qulayliklar mavjud"

    text = (
        f"🏢 <b>Xona #{room_id}</b>\n\n"
        f"📌 <b>Tur:</b> {room_type_text}\n\n"
        f"📝 <i>{room[2]}</i>\n\n"
        f"👥 <b>Sig'imi:</b> {room[6]} kishi\n"
        f"💰 <b>Narxi:</b> {room_price_int:,} so'm/soat\n"
        f"💳 <b>Zaklad ({DEPOSIT_PERCENT}%):</b> {deposit:,} so'm\n\n"
        f"<b>✨ Afzalliklar:</b>\n{advantages_text}\n\n"
        f"<i>Xonani bron qilish uchun pastdagi tugmani bosing</i>"
    )

    image_path = os.path.join(IMAGES_PATH, room[3])
    if os.path.exists(image_path):
        photo = FSInputFile(image_path)
        await callback.message.delete()
        await callback.message.answer_photo(photo=photo, caption=text, reply_markup=room_detail_keyboard(room_id))
    else:
        await callback.message.edit_text(text, reply_markup=room_detail_keyboard(room_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("book_room_"))
async def booking_room_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    room_id = int(callback.data.split("_")[2])
    room = get_room(room_id)

    room_desc = room[2][:50] + "..." if len(room[2]) > 50 else room[2]
    room_display = f"#{room_id} - {room_desc}"
    room_price_int = parse_price(room[5])

    await state.update_data(room_id=room_id, room_name=room_display, room_price=room_price_int)
    await state.set_state(Booking.name)

    await callback.message.edit_text(
        f"📅 <b>Xona bron qilish: {room_display}</b>\n\nIltimos, ismingizni kiriting:",
        reply_markup=back_to_main_keyboard()
    )
    await callback.answer()


@dp.message(Booking.name)
async def booking_name(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    if len(message.text) > 50:
        await message.answer("❌ Ism juda uzun, qisqaroq kiriting.")
        return

    await state.update_data(name=message.text)
    user = get_user(message.from_user.id)

    if user and user[2]:
        await state.update_data(phone=user[2])
        await state.set_state(Booking.date)
        await message.answer(
            "📅 <b>Bron qilish sanasini tanlang</b>\n\n"
            "Quyidagi kalendardan kunni tanlang yoki sanani kiriting:\nMasalan: 25.12.2024",
            reply_markup=types.ReplyKeyboardRemove()
        )
        today = datetime.now()
        keyboard, header = date_pagination_keyboard(today.year, today.month, 1)
        await message.answer(f"📅 {header}\n⬇️ Kunni tanlang:", reply_markup=keyboard)
    else:
        await state.set_state(Booking.phone)
        await message.answer(
            "📞 <b>Telefon raqamingizni kiriting</b>\n\nMasalan: +998901234567",
            reply_markup=types.ReplyKeyboardRemove()
        )


@dp.message(Booking.phone)
async def booking_phone(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    phone = message.text.strip()
    if not phone.startswith('+') or len(phone) < 9:
        await message.answer("❌ Noto'g'ri format. Iltimos, +998901234567 formatida yozing.")
        return

    await state.update_data(phone=phone)
    await state.set_state(Booking.date)
    await message.answer(
        "📅 <b>Bron qilish sanasini tanlang</b>\n\n"
        "Quyidagi kalendardan kunni tanlang yoki sanani kiriting:\nMasalan: 25.12.2024",
        reply_markup=types.ReplyKeyboardRemove()
    )
    today = datetime.now()
    keyboard, header = date_pagination_keyboard(today.year, today.month, 1)
    await message.answer(f"📅 {header}\n⬇️ Kunni tanlang:", reply_markup=keyboard)


@dp.message(Booking.date)
async def booking_date_text(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    if validate_date(message.text):
        await state.update_data(date=message.text)
        await state.set_state(Booking.time)
        await message.answer(
            "⏰ <b>Bron qilish vaqtini kiriting</b>\n\nMasalan: 19:00\n"
            "<i>Soat:daqiqa formatida (00:00 - 23:59)</i>",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.answer(
            "❌ <b>Noto'g'ri sana formati</b>\n\n"
            "Iltimos, sanani to'g'ri formatda kiriting:\n"
            "📅 Kun.Oy.Yil (masalan: 25.12.2024 yoki 25.12.24)\n\n"
            "<i>Faqat 2024-2027 yillar oralig'idagi kelajak sanalar qabul qilinadi</i>",
            reply_markup=types.ReplyKeyboardRemove()
        )


@dp.callback_query(lambda c: c.data.startswith("date_") and not c.data.startswith("date_page_"))
async def date_selected(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.replace("date_", "")
    if validate_date(date_str):
        await state.update_data(date=date_str)
        await state.set_state(Booking.time)
        await callback.message.edit_text(
            f"✅ Sana qabul qilindi: <b>{date_str}</b>\n\n"
            f"⏰ Endi bron qilish vaqtini kiriting:\nMasalan: 19:00",
            reply_markup=back_to_main_keyboard()
        )
    else:
        await callback.answer("❌ Noto'g'ri sana", show_alert=True)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("date_page_"))
async def date_pagination_handler(callback: CallbackQuery):
    try:
        parts = callback.data.split("_")
        page = int(parts[2])
        year = int(parts[3])
        month = int(parts[4])
        keyboard, header = date_pagination_keyboard(year, month, page)
        await callback.message.edit_text(f"📅 {header}\n⬇️ Kunni tanlang:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Pagination xatolik: {e}")
        await callback.answer("Xatolik yuz berdi")
    finally:
        await callback.answer()


@dp.message(Booking.time)
async def booking_time(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    if not validate_time(message.text):
        await message.answer(
            "❌ <b>Noto'g'ri vaqt formati</b>\n\nIltimos, vaqtni to'g'ri formatda kiriting:\n"
            "⏰ Soat:Daqiqa (masalan: 19:00)",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    await state.update_data(time=message.text)
    await state.set_state(Booking.guests)
    await message.answer(
        "👥 <b>Nechta kishi uchun bron qilasiz?</b>\n\nMasalan: 4",
        reply_markup=types.ReplyKeyboardRemove()
    )


@dp.message(Booking.guests)
async def booking_guests(message: Message, state: FSMContext):
    if message.text in MAIN_MENU_TEXTS:
        await state.clear()
        await route_menu_message(message, state)
        return

    if not message.text.isdigit():
        await message.answer("❌ Iltimos, son kiriting (masalan: 4)")
        return

    guests = int(message.text)
    if guests <= 0:
        await message.answer("❌ Iltimos, musbat son kiriting (masalan: 4)")
        return

    if guests > 100:
        await message.answer("❌ 100 kishidan ortiq bron qilish uchun admin bilan bog'lanishingiz kerak.")
        return

    await state.update_data(guests=guests)
    data = await state.get_data()
    
    # ========== BAND XONALARNI TEKSHIRUV ==========
    is_blocked = get_room_block_status(data['room_id'])
    if is_blocked:
        await message.answer(
            "❌ <b>Bu xona allaqachon band qilingan</b>\n\n"
            "Iltimos, boshqa xona tanlang.",
            reply_markup=get_appropriate_menu(message.from_user.id)
        )
        await state.clear()
        return
    
    is_available = check_room_availability(data['room_id'], data['date'], data['time'])
    if not is_available:
        await message.answer(
            "❌ <b>Bu xonani sizdan oldin bron qilishdi!</b>\n\n"
            "Iltimos boshqa xona tanlang.",
            reply_markup=get_appropriate_menu(message.from_user.id)
        )
        await state.clear()
        return
    # ========== TEKSHIRUV TUGADI ==========

    booking_id, deposit = add_booking(
        user_id=message.from_user.id,
        user_name=data['name'],
        user_phone=data['phone'],
        date=data['date'],
        time=data['time'],
        guests=data['guests'],
        room_id=data['room_id'],
        room_name=data['room_name']
    )

    await state.update_data(booking_id=booking_id, selected_meals=[])

    user_message = (
        f"✅ <b>BRON VAQTINCHA SAQLANDI!</b> ✅\n\n"
        f"🎫 <b>BRON #{booking_id}</b>\n\n"
        f"<b>🏢 XONA:</b> {data['room_name']}\n"
        f"<b>📅 SANA:</b> {data['date']}\n"
        f"<b>⏰ VAQT:</b> {data['time']}\n"
        f"<b>👥 KISHILAR:</b> {data['guests']}\n"
        f"<b>💰 ZAKLAD:</b> {deposit:,} so'm\n\n"
        f"<b>💳 TO'LOV USULINI TANLANG</b>\n"
        f"<i>To'lov qilmagan bronlar {AUTO_CANCEL_MINUTES} daqiqadan so'ng bekor qilinadi.</i>"
    )

    await message.answer(user_message, reply_markup=booking_payment_keyboard(booking_id))

    admin_message = (
        f"🆕 <b>YANGI BRON (KUTILMOQDA)!</b>\n\n"
        f"🎫 <b>BRON #{booking_id}</b>\n\n"
        f"<b>🏢 XONA:</b> {data['room_name']}\n"
        f"<b>👤 MIJOZ:</b> {data['name']}\n"
        f"<b>📞 TELEFON:</b> {data['phone']}\n"
        f"<b>📅 SANA:</b> {data['date']} {data['time']}\n"
        f"<b>👥 KISHILAR:</b> {data['guests']}\n"
        f"<b>💰 ZAKLAD:</b> {deposit:,} so'm\n\n"
        f"<i>⏳ Mijoz to'lovni kutilmoqda...</i>"
    )
    await notify_admin(admin_message)


@dp.callback_query(lambda c: c.data.startswith("pay_payme_"))
async def pay_with_payme(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[2])
    booking = get_booking(booking_id)
    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return

    payme_message = (
        f"💳 <b>Payme orqali to'lash</b>\n\n"
        f"🎫 <b>Bron #{booking_id}</b>\n\n"
        f"<i>To'lovni amalga oshirish uchun quyidagi tugmani bosing:</i>\n\n"
        f"<b>💰 To'lov summasi:</b> {booking[10]:,} so'm"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="💳 Payme orqali to'lash", url=PAYME_LINK))
    keyboard.row(InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"check_sent_{booking_id}"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_payment_{booking_id}"))

    await callback.message.delete()
    await callback.message.answer(payme_message, reply_markup=keyboard.as_markup())
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("pay_card_"))
async def pay_with_card(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[2])
    booking = get_booking(booking_id)
    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return

    card_message = (
        f"💳 <b>Karta orqali to'lash</b>\n\n"
        f"🎫 <b>Bron #{booking_id}</b>\n\n"
        f"<b>💳 Karta raqami:</b> <code>5614 6812 0593 8586</code>\n"
        f"<b>👤 Qabul qiluvchi:</b> Tashmuxamedov Dilshod\n"
        f"<b>💰 To'lov summasi:</b> {booking[10]:,} so'm\n\n"
        f"<i>To'lovni amalga oshirgandan so'ng, quyidagi tugma orqali chekni yuboring:</i>"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"check_sent_{booking_id}"))
    keyboard.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_payment_{booking_id}"))

    await callback.message.delete()
    await callback.message.answer(card_message, reply_markup=keyboard.as_markup())
    await callback.answer()


# ==================== O'ZGARTIRILGAN OVQAT HANDLERLARI ====================

@dp.callback_query(lambda c: c.data.startswith("add_meals_"))
async def add_meals(callback: CallbackQuery, state: FSMContext):
    """Ovqat qo'shish - DUPLIKATLARDAN HIMAYALANGAN"""
    booking_id = int(callback.data.split("_")[2])
    payment = get_payment(booking_id)
    booking = get_booking(booking_id)

    if payment and payment[6]:
        await callback.answer("❌ To'lov qilingan, ovqat qo'shib bo'lmaydi", show_alert=True)
        return

    meals = get_meals()
    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    
    total_meals_price = 0
    for meal_id in selected_meals:
        meal = get_meal_by_id(meal_id)
        if meal:
            total_meals_price += meal[3]
    
    total_payment = (booking[10] if booking else 0) + total_meals_price

    await callback.message.delete()
    await callback.message.answer(
        f"🍽 <b>OVQATLAR MENYUSI</b>\n\n"
        f"Quyidagi taomlardan tanlang:\n"
        f"<i>Tanlangan taomlar ✅ belgisi bilan ko'rsatiladi</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Xona zakladi:</b> {booking[10] if booking else 0:,} so'm\n"
        f"🍽 <b>Ovqatlar summasi:</b> {total_meals_price:,} so'm\n"
        f"💳 <b>Jami to'lov:</b> {total_payment:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━",
        reply_markup=meals_with_payment_keyboard(meals, booking_id, selected_meals, total_payment)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("select_meal_"))
async def select_meal(callback: CallbackQuery, state: FSMContext):
    """Ovqat tanlash - DUPLIKATLARDAN HIMAYALANGAN"""
    parts = callback.data.split("_")
    meal_id = int(parts[2])
    booking_id = int(parts[3])

    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    meal = get_meal_by_id(meal_id)
    booking = get_booking(booking_id)

    if meal_id in selected_meals:
        selected_meals.remove(meal_id)
        action_text = "o'chirildi"
    else:
        selected_meals.append(meal_id)
        action_text = "qo'shildi"

    await state.update_data(selected_meals=selected_meals)
    
    total_meals_price = 0
    for mid in selected_meals:
        m = get_meal_by_id(mid)
        if m:
            total_meals_price += m[3]
    
    total_payment = (booking[10] if booking else 0) + total_meals_price
    
    await callback.answer(f"✅ {meal[1]} {action_text}!")
    
    meals = get_meals()
    await callback.message.edit_text(
        f"🍽 <b>OVQATLAR MENYUSI</b>\n\n"
        f"Quyidagi taomlardan tanlang:\n"
        f"<i>Tanlangan taomlar ✅ belgisi bilan ko'rsatiladi</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Xona zakladi:</b> {booking[10] if booking else 0:,} so'm\n"
        f"🍽 <b>Ovqatlar summasi:</b> {total_meals_price:,} so'm\n"
        f"💳 <b>Jami to'lov:</b> {total_payment:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━",
        reply_markup=meals_with_payment_keyboard(meals, booking_id, selected_meals, total_payment)
    )


@dp.callback_query(lambda c: c.data.startswith("view_cart_"))
async def view_cart(callback: CallbackQuery, state: FSMContext):
    """Savatni ko'rish - DUPLIKATLARDAN HIMAYALANGAN"""
    booking_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    booking = get_booking(booking_id)

    if not selected_meals:
        await callback.answer("Savat bo'sh", show_alert=True)
        return

    meals_text = ""
    total_meals_price = 0
    for meal_id in selected_meals:
        meal = get_meal_by_id(meal_id)
        if meal:
            meals_text += f"• {meal[5]} {meal[1]} - {meal[3]:,} so'm\n"
            total_meals_price += meal[3]

    total_payment = (booking[10] if booking else 0) + total_meals_price
    
    cart_message = (
        f"🛒 <b>SAVAT</b>\n\n"
        f"<b>Tanlangan ovqatlar:</b>\n{meals_text}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Xona zakladi:</b> {booking[10] if booking else 0:,} so'm\n"
        f"🍽 <b>Ovqatlar summasi:</b> {total_meals_price:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>💳 Jami to'lov:</b> {total_payment:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Quyidagi tugmalar orqali to'lovni amalga oshiring:</i>"
    )
    await callback.message.edit_text(cart_message, reply_markup=cart_with_payment_keyboard(booking_id, total_payment))
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("pay_from_meals_"))
async def pay_from_meals(callback: CallbackQuery, state: FSMContext):
    """Ovqatlar bilan birga to'lov - DUPLIKATLARDAN HIMAYALANGAN"""
    parts = callback.data.split("_")
    payment_type = parts[3]
    booking_id = int(parts[4])
    
    booking = get_booking(booking_id)
    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    
    total_meals_price = 0
    for meal_id in selected_meals:
        meal = get_meal_by_id(meal_id)
        if meal:
            total_meals_price += meal[3]
    
    total_payment = booking[10] + total_meals_price
    
    if payment_type == "payme":
        payme_message = (
            f"💳 <b>Payme orqali to'lash</b>\n\n"
            f"🎫 <b>Bron #{booking_id}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Xona zakladi:</b> {booking[10]:,} so'm\n"
            f"🍽 <b>Ovqatlar:</b> {total_meals_price:,} so'm\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<b>💳 Jami to'lov:</b> {total_payment:,} so'm\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>To'lovni amalga oshirish uchun quyidagi tugmani bosing:</i>"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="💳 Payme orqali to'lash", url=PAYME_LINK))
        keyboard.row(InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"check_sent_{booking_id}"))
        keyboard.row(InlineKeyboardButton(text="⬅️ Ovqatlar menyusiga qaytish", callback_data=f"add_meals_{booking_id}"))
        
        await callback.message.delete()
        await callback.message.answer(payme_message, reply_markup=keyboard.as_markup())
        
    else:
        card_message = (
            f"💳 <b>Karta orqali to'lash</b>\n\n"
            f"🎫 <b>Bron #{booking_id}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Xona zakladi:</b> {booking[10]:,} so'm\n"
            f"🍽 <b>Ovqatlar:</b> {total_meals_price:,} so'm\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<b>💳 Jami to'lov:</b> {total_payment:,} so'm\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>💳 Karta raqami:</b> <code>5614 6812 0593 8586</code>\n"
            f"<b>👤 Qabul qiluvchi:</b> Tashmuxamedov Dilshod\n\n"
            f"<i>To'lovni amalga oshirgandan so'ng, quyidagi tugma orqali chekni yuboring:</i>"
        )
        
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"check_sent_{booking_id}"))
        keyboard.row(InlineKeyboardButton(text="⬅️ Ovqatlar menyusiga qaytish", callback_data=f"add_meals_{booking_id}"))
        
        await callback.message.delete()
        await callback.message.answer(card_message, reply_markup=keyboard.as_markup())
    
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("back_to_meals_"))
async def back_to_meals(callback: CallbackQuery, state: FSMContext):
    """Ovqatlar menyusiga qaytish - DUPLIKATLARDAN HIMAYALANGAN"""
    booking_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    meals = get_meals()
    
    booking = get_booking(booking_id)
    total_meals_price = 0
    for meal_id in selected_meals:
        meal = get_meal_by_id(meal_id)
        if meal:
            total_meals_price += meal[3]
    
    total_payment = (booking[10] if booking else 0) + total_meals_price
    
    await callback.message.delete()
    await callback.message.answer(
        f"🍽 <b>OVQATLAR MENYUSI</b>\n\n"
        f"Quyidagi taomlardan tanlang:\n"
        f"<i>Tanlangan taomlar ✅ belgisi bilan ko'rsatiladi</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Xona zakladi:</b> {booking[10] if booking else 0:,} so'm\n"
        f"🍽 <b>Ovqatlar summasi:</b> {total_meals_price:,} so'm\n"
        f"💳 <b>Jami to'lov:</b> {total_payment:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━",
        reply_markup=meals_with_payment_keyboard(meals, booking_id, selected_meals, total_payment)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("back_to_booking_"))
async def back_to_booking(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[3])
    booking = get_booking(booking_id)
    
    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return
    
    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    
    total_meals_price = 0
    for meal_id in selected_meals:
        meal = get_meal_by_id(meal_id)
        if meal:
            total_meals_price += meal[3]
    
    total_payment = booking[10] + total_meals_price
    
    back_message = (
        f"✅ <b>BRON VAQTINCHA SAQLANDI!</b> ✅\n\n"
        f"🎫 <b>BRON #{booking_id}</b>\n\n"
        f"<b>🏢 XONA:</b> {booking[8]}\n"
        f"<b>📅 SANA:</b> {booking[4]}\n"
        f"<b>⏰ VAQT:</b> {booking[5]}\n"
        f"<b>👥 KISHILAR:</b> {booking[6]}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>💰 ZAKLAD:</b> {booking[10]:,} so'm\n"
        f"<b>🍽 OVQATLAR:</b> {total_meals_price:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>💳 UMUMIY SUMMA:</b> {total_payment:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💳 TO'LOV USULINI TANLANG</b>\n"
        f"<i>To'lov qilmagan bronlar {AUTO_CANCEL_MINUTES} daqiqadan so'ng bekor qilinadi.</i>"
    )
    
    await callback.message.delete()
    await callback.message.answer(back_message, reply_markup=booking_payment_keyboard(booking_id))
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("back_to_payment_"))
async def back_to_payment(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[3])
    booking = get_booking(booking_id)
    if not booking:
        await callback.answer("Bron topilmadi", show_alert=True)
        return

    back_message = (
        f"✅ <b>BRON VAQTINCHA SAQLANDI!</b> ✅\n\n"
        f"🎫 <b>BRON #{booking_id}</b>\n\n"
        f"<b>🏢 XONA:</b> {booking[8]}\n"
        f"<b>📅 SANA:</b> {booking[4]}\n"
        f"<b>⏰ VAQT:</b> {booking[5]}\n"
        f"<b>👥 KISHILAR:</b> {booking[6]}\n"
        f"<b>💰 ZAKLAD:</b> {booking[10]:,} so'm\n\n"
        f"<b>💳 TO'LOV USULINI TANLANG</b>\n"
        f"<i>To'lov qilmagan bronlar {AUTO_CANCEL_MINUTES} daqiqadan so'ng bekor qilinadi.</i>"
    )
    await callback.message.delete()
    await callback.message.answer(back_message, reply_markup=booking_payment_keyboard(booking_id))
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("final_confirm_"))
async def final_confirm_booking(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[2])
    payment = get_payment(booking_id)
    booking = get_booking(booking_id)
    
    data = await state.get_data()
    selected_meals = data.get('selected_meals', [])
    
    if selected_meals:
        update_booking_meals(booking_id, json.dumps(selected_meals))

    if not payment or not payment[6]:
        await callback.answer("❌ Avval zaklad to'lovini qiling va admin tasdiqlashini kuting!", show_alert=True)
        return

    update_booking_status(booking_id, 'confirmed')
    await callback.message.delete()
    await callback.message.answer(
        f"✅ <b>BRON TASDIQLANDI!</b> ✅\n\n"
        f"🎫 <b>Bron #{booking_id}</b>\n"
        f"🏢 <b>Xona:</b> {booking[8]}\n"
        f"📅 <b>Sana:</b> {booking[4]}\n"
        f"⏰ <b>Vaqt:</b> {booking[5]}\n\n"
        f"<i>Sizni kutyapmiz! 😊</i>",
        reply_markup=get_appropriate_menu(callback.from_user.id)
    )
    await state.clear()
    await callback.answer("✅ Bron tasdiqlandi!")


@dp.callback_query(lambda c: c.data.startswith("check_sent_"))
async def check_sent(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[2])
    await state.update_data(booking_id=booking_id)
    await state.set_state(CheckStates.waiting_for_check)

    await callback.message.delete()
    await callback.message.answer(
        "📸 <b>Chek yuborish</b>\n\n"
        "Iltimos, zaklad to'lovini qilganingizdan keyin "
        "chek (screenshot) ni shu yerga yuboring.\n\n"
        "<i>Faqat rasm qabul qilinadi.</i>\n\n"
        "To'lov qilish uchun pastdagi tugmani bosing:",
        reply_markup=payment_keyboard(booking_id)
    )
    await callback.answer()


@dp.message(CheckStates.waiting_for_check, F.photo)
async def receive_check(message: Message, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get('booking_id')

    if not booking_id:
        await state.clear()
        await message.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    booking = get_booking(booking_id)

    if not booking:
        await message.answer("❌ Bron topilmadi.")
        await state.clear()
        return

    deposit_amount = booking[10]
    add_payment(booking_id, deposit_amount, file_id)

    admin_message = (
        f"🆕 <b>YANGI ZAKLAD TO'LOVI!</b>\n\n"
        f"🎫 <b>BRON #{booking_id}</b>\n\n"
        f"<b>🏢 XONA:</b> {booking[8]}\n"
        f"<b>👤 MIJOZ:</b> {booking[2]}\n"
        f"<b>📞 TELEFON:</b> {booking[3]}\n"
        f"<b>📅 SANA:</b> {booking[4]} {booking[5]}\n"
        f"<b>👥 KISHILAR:</b> {booking[6]}\n"
        f"<b>💰 ZAKLAD:</b> {deposit_amount:,} so'm\n\n"
        f"<i>Chekni tekshirib, tasdiqlang! Admin panel orqali.</i>"
    )
    await notify_admin(admin_message, photo=file_id)

    await message.answer(
        "✅ <b>Chek qabul qilindi!</b>\n\n"
        "Tez orada administratorlarimiz to'lovni tekshirib, sizga xabar beradi.\n\n"
        "<i>Bu jarayon bir necha daqiqa olishi mumkin.</i>",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.clear()


@dp.message(CheckStates.waiting_for_check, F.text.in_(MAIN_MENU_TEXTS))
async def check_state_menu_interrupt(message: Message, state: FSMContext):
    await state.clear()
    await route_menu_message(message, state)


@dp.message(CheckStates.waiting_for_check)
async def invalid_check(message: Message):
    await message.answer(
        "❌ <b>Xatolik</b>\n\nFaqat rasm yuboring! Iltimos, to'lov chekining screenshot'ini yuboring."
    )


# ==================== O'ZGARTIRILGAN HANDLE_SHOW_MEALS ====================

async def handle_show_meals(message: Message):
    """Ovqatlarni ko'rsatish - UNIQUE ovqatlar"""
    meals = get_meals()
    if not meals:
        await message.answer("🍽 Hozircha ma'lumotlar mavjud emas.")
        return

    text = "🍽 <b>OVQATLARIMIZ</b>\n\n"
    categories = {
        'main': '🍚 ASOSIY TAOMLAR',
        'meat': '🍖 GO\'SHTLI TAOMLAR'
    }
    for category, title in categories.items():
        category_meals = [m for m in meals if m[4] == category]
        if category_meals:
            text += f"<b>{title}</b>\n"
            for meal in category_meals:
                text += f"  {meal[5]} {meal[1]} - {meal[3]:,} so'm\n"
            text += "\n"

    text += "<i>Buyurtma berish uchun admin bilan bog'lanishingiz mumkin:</i>\n"
    text += f"📞 {CONTACT_PHONE}"
    await message.answer(text)

async def handle_show_location(message: Message):
    await message.answer_location(latitude=LATITUDE, longitude=LONGITUDE)
    await message.answer(f"📍 <b>Manzil:</b> {CHAYXONA_ADDRESS}\n\n🧭 <b>Mo'ljal:</b> {CHAYXONA_NAME}")


async def handle_show_contact(message: Message):
    text = (
        f"📞 <b>Aloqa ma'lumotlari</b>\n\n"
        f"☎️ <b>Telefon:</b> {CONTACT_PHONE}\n"
        f"📍 <b>Manzil:</b> {CHAYXONA_ADDRESS}\n\n"
        f"⏰ <b>Ish vaqti:</b>\nDushanba - Yakshanba: 09:00 - 23:00\n\n"
        f"<i>Savollar bo'lsa, bemalol bog'lanishingiz mumkin!</i>"
    )
    await message.answer(text)


async def handle_show_info(message: Message):
    text = (
        f"✨ <b>{CHAYXONA_NAME} haqida</b> ✨\n\n"
        f"<b>📅 Tashkil etilgan:</b> 2016-yil\n\n"
        f"<b>📍 Manzil:</b> {CHAYXONA_ADDRESS}\n\n"
        f"<b>🌟 Biz haqimizda:</b>\n"
        f"5 xil xona, 20+ xil taomlar, Basseyn, Sauna, Billiard va Tennis.\n\n"
        f"<b>🏊‍♂️ Xonalar:</b>\n"
        f"• 2 ta Basseyn/Sauna xona\n"
        f"• 3 ta Billiard xona\n"
        f"• 3 ta Stol tennis xona\n"
        f"• 9 ta Tapchan xona\n"
        f"• 7 ta Banket zal\n\n"
        f"<b>🍽 Taomlar:</b>\n• 20+ xil milliy taomlar\n\n"
        f"<b>✨ Imtiyozlar:</b>\n• Bepul Wi-Fi\n• Avtoturargoh\n• Konditsioner\n\n"
        f"<i>Sizni kutyapmiz! 🤗</i>"
    )
    image_path = os.path.join(IMAGES_PATH, "chayxona.jpg")
    if os.path.exists(image_path):
        photo = FSInputFile(image_path)
        await message.answer_photo(photo=photo, caption=text)
    else:
        await message.answer(text)


async def handle_admin_panel_message(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Siz admin emassiz!")
        return

    stats = get_statistics()
    text = (
        f"👑 <b>Admin panel</b>\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Foydalanuvchilar: {stats['total_users']} (bugun: +{stats['today_users']})\n"
        f"📅 Jami bronlar: {stats['total_bookings']} (bugun: {stats['today_bookings']})\n"
        f"⏳ Kutilayotgan bronlar: {stats['pending_bookings']}\n"
        f"✅ Tasdiqlangan bronlar: {stats['confirmed_bookings']}\n"
        f"💳 To'lovlar: {stats['total_payments']} (tekshirilmagan: {stats['unverified_payments']})\n"
        f"💰 Jami zakladlar: {stats['total_deposits']:,} so'm\n"
        f"━━━━━━━━━━━━━━━━━━━\n\nQuyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(text, reply_markup=admin_panel_keyboard())


# ==================== ADMIN ROOM BLOCKING HANDLERS ====================

@dp.callback_query(lambda c: c.data == "admin_block_rooms")
async def admin_block_rooms(callback: CallbackQuery):
    """Admin: Xonalarni band qilish paneli"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return
    
    # To'g'ridan-to'g'ri import qilish
    from database import get_all_rooms_with_status, toggle_room_block
    
    rooms = get_all_rooms_with_status()
    
    print(f"🔍 admin_block_rooms: {len(rooms)} ta xona olindi")
    
    if not rooms:
        await callback.message.edit_text(
            "🏠 Xonalar topilmadi.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    
    for room in rooms:
        room_id = room[0]
        room_number = room[1] if room[1] else "?"
        room_name = room[2][:20] if room[2] else "Xona"
        is_blocked = room[8] if len(room) > 8 else 0
        
        status = "🔴" if is_blocked else "🟢"
        
        builder.row(InlineKeyboardButton(
            text=f"{status} Xona #{room_number} - {room_name}",
            callback_data=f"admin_toggle_room_{room_id}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back"))
    
    await callback.message.edit_text(
        f"🏠 <b>Xonalarni band qilish</b>\n\nJami: {len(rooms)} ta xona",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_toggle_room_"))
async def admin_toggle_room(callback: CallbackQuery):
    """Admin: Xonani band/bo'sh qilish (toggle)"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return
    
    room_id = int(callback.data.split("_")[3])
    
    new_status = toggle_room_block(room_id)
    room = get_room(room_id)  # get_room_by_id o'rniga get_room
    
    if room:
        status_text = "🔴 BAND QILINDI" if new_status else "🟢 BO'SH QILINDI"
        status_emoji = "🔴" if new_status else "🟢"
        
        await callback.answer(f"{status_emoji} Xona #{room[1]} {status_text}!", show_alert=True)
        
        await admin_block_rooms(callback)
    else:
        await callback.answer("❌ Xona topilmadi!", show_alert=True)


@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    stats = get_statistics()
    text = (
        f"📊 <b>Batafsil statistika</b>\n\n"
        f"👥 <b>Foydalanuvchilar:</b>\n• Jami: {stats['total_users']}\n• Bugun: {stats['today_users']}\n\n"
        f"📅 <b>Bronlar:</b>\n• Jami: {stats['total_bookings']}\n• Bugun: {stats['today_bookings']}\n"
        f" •  Kutilmoqda: {stats['pending_bookings']}\n• Tasdiqlangan: {stats['confirmed_bookings']}\n\n"
        f"💳 <b>To'lovlar:</b>\n• Jami: {stats['total_payments']}\n• Tekshirilmagan: {stats['unverified_payments']}\n\n"
        f"💰 <b>Zakladlar:</b>\n• Jami summa: {stats['total_deposits']:,} so'm"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(lambda c: c.data in ("admin_deposits", "admin_deposits_refresh"))
async def admin_deposits(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    unverified = get_unverified_payments()
    if not unverified:
        await callback.message.edit_text(
            "📋 <b>Zakladlar</b>\n\n📭 Tekshirilmagan zakladlar mavjud emas.\nBarcha to'lovlar tekshirilgan.",
            reply_markup=admin_back_keyboard()
        )
        await callback.answer()
        return

    text = (
        f"📋 <b>Zakladlar</b>\n\n"
        f"🔄 <b>Tekshirilmagan:</b> {len(unverified)} ta\n"
        f"━━━━━━━━━━━━━━━━━━━\n\nQuyidagi zakladlardan birini tanlang:"
    )
    await callback.message.edit_text(text, reply_markup=admin_deposits_keyboard(unverified))
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("admin_deposit_") and not c.data.startswith("admin_deposit_detail_"))
async def admin_deposit_detail(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    try:
        booking_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Xatolik yuz berdi")
        return

    payment = get_payment(booking_id)
    booking = get_booking(booking_id)

    if not payment or not booking:
        await callback.answer("Ma'lumot topilmadi")
        return

    status_text = "✅ Tasdiqlangan" if payment[6] else "⏳ Kutilmoqda"
    status_color = "✅" if payment[6] else "⏳"

    text = (
        f"📋 <b>ZAKLAD #{booking_id}</b> {status_color}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 MIJOZ MA'LUMOTLARI:</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Ism:</b> {booking[2]}\n"
        f"📞 <b>Telefon:</b> {booking[3]}\n"
        f"🆔 <b>User ID:</b> <code>{booking[1]}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🏢 BRON MA'LUMOTLARI:</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 <b>Xona:</b> {booking[8]}\n"
        f"📅 <b>Sana:</b> {booking[4]}\n"
        f"⏰ <b>Vaqt:</b> {booking[5]}\n"
        f"👥 <b>Kishilar:</b> {booking[6]}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>💰 TO'LOV MA'LUMOTLARI:</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Zaklad:</b> {booking[10]:,} so'm\n"
        f"📅 <b>Yuborilgan:</b> {payment[9] if len(payment) > 9 else 'Noma\'lum'}\n"
        f"📊 <b>Holati:</b> {status_text}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Chekni tekshirib, quyidagi tugmalardan birini bosing:</i>"
    )

    if payment[5]:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=payment[5],
            caption=text,
            reply_markup=admin_deposit_detail_keyboard(booking_id)
        )
    else:
        await callback.message.edit_text(text, reply_markup=admin_deposit_detail_keyboard(booking_id))
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("admin_verify_deposit_"))
async def admin_verify_deposit(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    booking_id = int(callback.data.split("_")[3])
    verify_payment(booking_id, callback.from_user.id)
    booking = get_booking(booking_id)

    if booking:
        user_message = (
            f"✅ <b>ZAKLAD TO'LOVI TASDIQLANDI!</b> ✅\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"   🎫 <b>BRON #{booking_id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Assalomu alaykum, {booking[2]}!</b>\n\n"
            f"Sizning zaklad to'lovingiz muvaffaqiyatli tasdiqlandi! 🎉\n\n"
            f"<b>🏢 Bron ma'lumotlari:</b>\n"
            f"• 🏠 <b>Xona:</b> {booking[8]}\n"
            f"• 📅 <b>Sana:</b> {booking[4]}\n"
            f"• ⏰ <b>Vaqt:</b> {booking[5]}\n"
            f"• 👥 <b>Kishilar:</b> {booking[6]}\n"
            f"• 💰 <b>To'lov:</b> {booking[10]:,} so'm\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>🌟 Sizni {CHAYXONA_NAME} da kutib qolamiz!</b>\n\n"
            f"📍 <b>Manzil:</b> {CHAYXONA_ADDRESS}\n"
            f"📞 <b>Telefon:</b> {CONTACT_PHONE}\n"
            f"<i>Yana bir bor tanlaganingiz uchun rahmat! 😊</i>"
        )
        try:
            await bot.send_message(booking[1], user_message, reply_markup=booking_confirmed_keyboard(booking_id))
        except Exception as e:
            logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")

    await callback.message.delete()
    await callback.message.answer(
        f"✅ <b>Zaklad #{booking_id} tasdiqlandi!</b>\n\nMijozga xabar yuborildi.",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer("✅ Tasdiqlandi")


@dp.callback_query(lambda c: c.data.startswith("admin_reject_deposit_"))
async def admin_reject_deposit(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    booking_id = int(callback.data.split("_")[3])
    update_booking_status(booking_id, 'rejected')
    booking = get_booking(booking_id)

    if booking:
        user_message = (
            f"❌ <b>ZAKLAD TO'LOVI RAD ETILDI</b> ❌\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"   🎫 <b>BRON #{booking_id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Hurmatli {booking[2]}!</b>\n\n"
            f"Kechirasiz, sizning zaklad to'lovingiz rad etildi.\n\n"
            f"<b>❌ Rad etish mumkin bo'lgan sabablar:</b>\n"
            f"• To'lov cheki aniqlanmadi yoki noto'g'ri\n"
            f"• To'lov summasi xato\n"
            f"• Chekda Payme logotipi yoki to'lov tafsilotlari yo'q\n"
            f"• Chek boshqa bron uchun\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📞 Qayta urinib ko'ring yoki admin bilan bog'laning:</b>\n"
            f"📞 {CONTACT_PHONE}\n\n\n"
            f"<i>Iltimos, aniq va to'g'ri chek yuboring! To'lov chekida quyidagilar bo'lishi kerak:</i>\n"
            f"• To'lov summasi\n• To'lov vaqti\n• Payme logotipi\n\n"
            f"<b>Agar muammo takrorlansa, admin bilan bog'lanishingizni so'raymiz.</b>"
        )
        try:
            await bot.send_message(booking[1], user_message, reply_markup=types.ReplyKeyboardRemove())
        except Exception as e:
            logger.error(f"Foydalanuvchiga xabar yuborishda xatolik: {e}")

    await callback.message.delete()
    await callback.message.answer(
        f"❌ <b>Zaklad #{booking_id} rad etildi!</b>\n\nMijozga xabar yuborildi.",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer("❌ Rad etildi")


@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    stats = get_statistics()
    text = (
        f"👑 <b>Admin panel</b>\n\n"
        f"📊 <b>Statistika:</b>\n━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Foydalanuvchilar: {stats['total_users']} (bugun: +{stats['today_users']})\n"
        f"📅 Jami bronlar: {stats['total_bookings']} (bugun: {stats['today_bookings']})\n"
        f"⏳ Kutilayotgan bronlar: {stats['pending_bookings']}\n"
        f"✅ Tasdiqlangan bronlar: {stats['confirmed_bookings']}\n"
        f"❌ Bekor qilingan: {stats.get('cancelled_bookings', 0) + stats.get('rejected_bookings', 0)}\n"
        f"💳 Tekshirilmagan to'lovlar: {stats['unverified_payments']}\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, reply_markup=admin_panel_keyboard())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_logout")
async def admin_logout(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return
    await callback.message.delete()
    await callback.message.answer("🏠 <b>Bosh menyu</b>", reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    users = get_all_users()
    if not users:
        await callback.message.edit_text("👥 Foydalanuvchilar topilmadi.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    text = f"👥 <b>Foydalanuvchilar ({len(users)} ta)</b>\n\n"
    for i, user in enumerate(users[:10], 1):
        text += f"{i}. {user[1]} - {user[2]}\n"
    if len(users) > 10:
        text += f"\n... va yana {len(users) - 10} ta"
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_bookings")
async def admin_bookings(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Ruxsat yo'q")
        return

    bookings = get_all_bookings()
    if not bookings:
        await callback.message.edit_text("📅 Bronlar topilmadi.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    text = f"📅 <b>Bronlar ({len(bookings)} ta)</b>\n\n"
    for i, book in enumerate(bookings[:10], 1):
        status_emoji = "✅" if book[11] == "confirmed" else "⏳" if book[11] == "pending" else "❌"
        text += f"{i}. {status_emoji} #{book[0]} - {book[2]} | {book[8][:20]}\n"
    if len(bookings) > 10:
        text += f"\n... va yana {len(bookings) - 10} ta"
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "back_to_room_cats")
async def back_to_room_categories(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🏢 <b>Xonalarimiz</b>\n\nKategoriya bo'yicha tanlang:",
        reply_markup=room_categories_keyboard()
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(lambda c: c.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "🏠 <b>Bosh menyu</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=get_appropriate_menu(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "cancel_booking")
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data and 'booking_id' in data:
        update_booking_status(data['booking_id'], 'cancelled')
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "❌ <b>Bron bekor qilindi</b>\n\nYangi bron qilish uchun 🏠 Bron qilish tugmasini bosing.",
        reply_markup=get_appropriate_menu(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("feedback_"))
async def feedback_received(callback: CallbackQuery):
    rating = callback.data.split("_")[1]
    stars = "⭐" * int(rating)
    user = get_user(callback.from_user.id)
    user_name = user[1] if user else callback.from_user.first_name

    await notify_admin(
        f"⭐ <b>Yangi fikr!</b>\n\n"
        f"👤 <b>Foydalanuvchi:</b> {user_name}\n"
        f"📞 <b>Telefon:</b> {user[2] if user else 'noma\'lum'}\n"
        f"⭐ <b>Baho:</b> {stars}\n"
        f"🆔 <b>User ID:</b> {callback.from_user.id}"
    )
    await callback.message.edit_text(
        f"<b>Rahmat!</b> 🌸\n\nSiz {stars} baho berdingiz.\n\n"
        f"Fikringiz uchun katta rahmat! Sizning fikringiz bizni yanada yaxshilanishimizga yordam beradi.\n\n"
        f"<i>Yana kutib qolamiz!</i>",
        reply_markup=back_to_main_keyboard()
    )
    await callback.answer("Fikringiz uchun rahmat! 🌸")

    


@dp.message(~StateFilter(None))
async def fsm_unknown_input(message: Message, state: FSMContext):
    current_state = await state.get_state()
    await message.answer(
        "❓ Iltimos, so'ralgan ma'lumotni kiriting yoki bosh menyuga qaytish uchun tugmani bosing.",
        reply_markup=back_to_main_keyboard()
    )



@dp.message(StateFilter(None))
async def handle_unknown(message: Message):
    await message.answer(
        "❌ <b>Noto'g'ri buyruq</b>\n\nIltimos, quyidagi menyulardan birini tanlang:",
        reply_markup=get_appropriate_menu(message.from_user.id)
    )

async def main():
    init_db()
    # Yangi ustunlarni qo'shish
    try:
        add_room_blocked_column()
        add_selected_meals_to_bookings()
    except Exception as e:
        print(f"Ustunlarni qo'shishda xatolik: {e}")
    
    os.makedirs(IMAGES_PATH, exist_ok=True)
    asyncio.create_task(auto_cancel_expired_bookings())
    
    # Scheduler ishga tushirish
    start_scheduler()

    print(f"🤖 {CHAYXONA_NAME} bot ishga tushdi!")
    print(f"📊 Ma'lumotlar bazasi: {DB_NAME}")
    print(f"👑 Adminlar: {ADMIN_IDS}")
    print(f"⏰ Auto-cancel: {AUTO_CANCEL_MINUTES} daqiqa")
    print(f"💰 Zaklad foizi: {DEPOSIT_PERCENT}%")
    print("-" * 30)

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
