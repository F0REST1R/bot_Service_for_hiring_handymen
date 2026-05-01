import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from bot.config import settings
from bot.database.database import init_db
from bot.handlers import registration, customer, worker, admin, cancel, admin_workers
from bot.database.database import get_db
from bot.utils.scheduler import start_scheduler
from bot.utils.google_sheets import GoogleSheetsClient
from bot.handlers import cancel 
from bot.handlers.cancel import router as cancel_router 
from bot.middleware.block_check import BlockCheckMiddleware

logging.basicConfig(level=logging.INFO)


class DatabaseMiddleware:
    """Middleware для внедрения сессии БД"""
    async def __call__(self, handler, event, data):
        async for db in get_db():
            data['db'] = db
            return await handler(event, data)

async def main():
    logging.info("Starting bot...")
    
    # Инициализация БД
    logging.info("Initializing database...")
    await init_db()
    logging.info("Database initialized")
    
    # Выбор storage (если есть Redis)
    if settings.REDIS_URL:
        logging.info(f"Using Redis storage: {settings.REDIS_URL}")
        storage = RedisStorage.from_url(settings.REDIS_URL)
    else:
        logging.info("Using Memory storage")
        storage = MemoryStorage()
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    
    # Регистрация мидлвари
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    
    # Передаём bot в middleware для отправки уведомлений
    dp['bot'] = bot
    
    await start_scheduler(bot)

    # Инициализация Google Sheets
    google_client = None
    if settings.GOOGLE_SPREADSHEET_ID:
        try:
            google_client = GoogleSheetsClient(
                settings.GOOGLE_CREDENTIALS_FILE,
                settings.GOOGLE_SPREADSHEET_ID
            )
            google_client.init_sheets()
            logging.info("✅ Google Sheets интеграция активна")
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации Google Sheets: {e}")
    
    # Передаем google_client в workspace (на уровень диспетчера)
    dp['google_client'] = google_client  # Правильный способ

    # Регистрация роутеров
    dp.include_router(registration.router)
    dp.include_router(customer.router)
    dp.include_router(worker.router)
    dp.include_router(admin.router)
    dp.include_router(cancel.router)
    dp.include_router(admin_workers.router)

    dp.message.middleware(BlockCheckMiddleware())
    dp.callback_query.middleware(BlockCheckMiddleware())
    
    logging.info("Bot started successfully!")
    
    # Запуск
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())