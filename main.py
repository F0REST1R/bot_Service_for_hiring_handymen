import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from bot.config import settings
from bot.database.database import init_db
from bot.handlers import registration, customer, worker, admin
from bot.database.database import get_db

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
    
    # Регистрация роутеров
    dp.include_router(registration.router)
    dp.include_router(customer.router)
    dp.include_router(worker.router)
    dp.include_router(admin.router)
    
    logging.info("Bot started successfully!")
    
    # Запуск
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())