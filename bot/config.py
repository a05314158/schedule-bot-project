import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]
    except ValueError:
        print("Ошибка: ADMIN_IDS в .env файле должен быть списком чисел, разделенных запятой.")
        ADMIN_IDS = []


BASE_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_PROJECT_DIR, "data", "scheduler_bot.db")
UPLOADS_DIR = os.path.join(BASE_PROJECT_DIR, "data", "uploads")
GENERATED_SCHEDULES_DIR = os.path.join(BASE_PROJECT_DIR, "data", "generated_schedules")
CORE_CONFIGS_DIR = os.path.join(BASE_PROJECT_DIR, "configs") # Путь к конфигам для schedule_core

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(GENERATED_SCHEDULES_DIR, exist_ok=True)
os.makedirs(CORE_CONFIGS_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_PROJECT_DIR, "data"), exist_ok=True) # Для scheduler_bot.db