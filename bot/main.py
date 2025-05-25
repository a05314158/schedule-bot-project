import asyncio
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.types import BotCommandScopeAllPrivateChats, BotCommandScopeChat

from bot.config import BOT_TOKEN, ADMIN_IDS
from bot.models.db import init_db
from bot.controllers import common_handlers, schedule_handlers, admin_handlers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

async def on_startup(dp: Dispatcher):
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("Установка команд бота...")
    common_commands = [
        types.BotCommand("start", "🚀 Запуск / Перезапуск бота"),
        types.BotCommand("help", "❓ Помощь по командам"),
        types.BotCommand("cancel", "❌ Отменить текущее действие"),
    ]
    await dp.bot.set_my_commands(common_commands, scope=BotCommandScopeAllPrivateChats())
    if ADMIN_IDS:
        admin_specific_commands = [
            types.BotCommand("admin", "👑 Админ-панель"),
            types.BotCommand("pending_users", "⏳ Ожидающие пользователи"),
            types.BotCommand("list_all_users", "👥 Все пользователи"),
            types.BotCommand("user_profile", "👤 Профиль пользователя (по ID)"),
            types.BotCommand("task_info", "ℹ️ Информация о задаче (по ID)"),
            types.BotCommand("list_tasks", "📋 Список всех задач"),
            types.BotCommand("force_cancel_task", "🚫 Принудительно отменить задачу"),
            # types.BotCommand("delete_task_data", "🗑️ Удалить данные задачи"), # Удалена, т.к. теперь через task_info
            types.BotCommand("broadcast", "📢 Рассылка сообщения"),
            types.BotCommand("view_feedback", "📬 Просмотреть отзывы"),
        ]
        all_admin_commands = common_commands + admin_specific_commands
        for admin_id in ADMIN_IDS:
            try: await dp.bot.set_my_commands(all_admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
            except Exception as e: logger.error(f"Не удалось установить команды для админа {admin_id}: {e}")
    logger.info("Бот запущен!")

async def on_shutdown(dp: Dispatcher):
    logger.warning('Бот остановлен.'); await dp.storage.close(); await dp.storage.wait_closed(); logger.info("Хранилище FSM закрыто.")

def main():
    if not BOT_TOKEN: logger.critical("Ошибка: BOT_TOKEN не найден."); exit("Критическая ошибка: BOT_TOKEN не найден.")
    bot = Bot(token=BOT_TOKEN); storage = MemoryStorage(); dp = Dispatcher(bot, storage=storage)
    logger.info("Регистрация обработчиков...")
    common_handlers.register_common_handlers(dp)
    schedule_handlers.register_schedule_handlers(dp)
    admin_handlers.register_admin_handlers(dp)
    logger.info("Обработчики зарегистрированы."); logger.info("Запуск поллинга...")
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True, allowed_updates=types.AllowedUpdates.all())

if __name__ == '__main__':
    main()