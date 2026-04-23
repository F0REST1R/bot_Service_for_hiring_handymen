import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from bot.database.database import AsyncSessionLocal
from bot.database.models import Order, City, Assignment, Worker, User
from bot.config import settings
import logging

logging.basicConfig(level=logging.INFO)

async def check_and_send_reminders(bot):
    """Проверка заявок и отправка напоминаний за 2 часа"""
    while True:
        try:
            # Проверяем каждую минуту
            await asyncio.sleep(60)
            
            now = datetime.now()
            # Заявки, которые начнутся через 2 часа (± 1 минута)
            reminder_time_start = now + timedelta(hours=2) - timedelta(minutes=1)
            reminder_time_end = now + timedelta(hours=2) + timedelta(minutes=1)
            
            async with AsyncSessionLocal() as db:
                # Находим заявки, которые нужно напомнить
                result = await db.execute(
                    select(Order, City)
                    .join(City, Order.city_id == City.id)
                    .where(
                        Order.status == 'active',
                        Order.start_datetime >= reminder_time_start,
                        Order.start_datetime <= reminder_time_end,
                        Order.reminder_sent == False  # Добавим поле в модель
                    )
                )
                orders = result.all()
                
                for order, city in orders:
                    # Получаем всех исполнителей, откликнувшихся на эту заявку
                    result = await db.execute(
                        select(Assignment, Worker, User)
                        .join(Worker, Assignment.worker_id == Worker.id)
                        .join(User, Worker.user_id == User.id)
                        .where(Assignment.order_id == order.id)
                    )
                    assignments = result.all()
                    
                    for assignment, worker, user in assignments:
                        try:
                            # Формируем текст напоминания
                            reminder_text = f"""
⏰ *НАПОМИНАНИЕ О ЗАЯВКЕ!*

У вас запланирована заявка через 2 часа!

📋 *Детали заявки:* #{order.id}
🏙️ *Город:* {city.name}
📍 *Адрес:* {order.address}
🕐 *Время начала:* {order.start_datetime.strftime('%d.%m.%Y %H:%M')}
👥 *Требуется человек:* {order.workers_count}
💰 *Оплата:* {order.price_per_person} руб./чел.

Пожалуйста, будьте вовремя!
"""
                            await bot.send_message(
                                chat_id=user.telegram_id,
                                text=reminder_text,
                                parse_mode="Markdown"
                            )
                            logging.info(f"Напоминание отправлено исполнителю {user.telegram_id} для заявки #{order.id}")
                        except Exception as e:
                            logging.error(f"Не удалось отправить напоминание {user.telegram_id}: {e}")
                    
                    # Отмечаем, что напоминание отправлено
                    order.reminder_sent = True
                    await db.commit()
                    
        except Exception as e:
            logging.error(f"Ошибка в планировщике напоминаний: {e}")

async def start_scheduler(bot):
    """Запуск планировщика напоминаний"""
    asyncio.create_task(check_and_send_reminders(bot))
    logging.info("Планировщик напоминаний запущен")