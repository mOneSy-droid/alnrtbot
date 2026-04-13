# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Bot token
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Ma'lumotlar bazasi
DB_NAME = os.getenv('DB_NAME')

# Adminlar ro'yxati (user id lar)
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]

# Bot username
BOT_USERNAME = os.getenv('BOT_USERNAME')

# Manzil (Toshkent)
LATITUDE = float(os.getenv('LATITUDE'))
LONGITUDE = float(os.getenv('LONGITUDE'))

# Aloqa ma'lumotlari
CONTACT_PHONE = os.getenv('CONTACT_PHONE')

# Rasmlar uchun papka
IMAGES_PATH = os.getenv('IMAGES_PATH',)

# Chayxona ma'lumotlari
CHAYXONA_NAME = os.getenv('CHAYXONA_NAME', 'Choyxona')
CHAYXONA_ADDRESS = os.getenv('CHAYXONA_ADDRESS')

# Payme to'lov linki
PAYME_LINK = os.getenv('PAYME_LINK',)

# Auto-cancel vaqti (minut)
AUTO_CANCEL_MINUTES = int(os.getenv('AUTO_CANCEL_MINUTES'))

# Xona narxlari (zaklad hisoblash uchun)
DEPOSIT_PERCENT = int(os.getenv('DEPOSIT_PERCENT',))  # 50% zaklad