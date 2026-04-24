from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import re
from bot.database.models import Order, City, Worker, Assignment, worker_city, User
from bot.utils.states import PostStates
from bot.config import settings
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.handlers.admin import is_admin, parse_datetime

router = Router()

@router.message(F.text == "📝 Создать пост")
async def create_post_start(message: Message, state: FSMContext, db: AsyncSession):
    """Начало создания поста - выбор города"""
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    # Получаем список городов с каналами
    result = await db.execute(select(City).where(City.is_active == True, City.channel_id.isnot(None)))
    cities = result.scalars().all()
    
    if not cities:
        await message.answer(
            "❌ Нет доступных городов с привязанными каналами!\n\n"
            "Сначала добавьте город и привяжите к нему Telegram-канал в 'Управление городами'"
        )
        return
    
    keyboard = []
    for city in cities:
        keyboard.append([InlineKeyboardButton(
            text=f"🏙️ {city.name}",
            callback_data=f"create_post_city_{city.id}"
        )])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_post")])
    
    await message.answer(
        "📝 *Создание новой заявки/поста*\n\n"
        "Выберите город:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.choosing_city)

@router.callback_query(PostStates.choosing_city, lambda c: c.data.startswith("create_post_city_"))
async def create_post_city_selected(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    """Выбор города - запрашиваем стоимость"""
    city_id = int(callback.data.split("_")[3])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    await state.update_data(city_id=city_id)
    await state.update_data(city_name=city.name)
    await state.update_data(channel_id=city.channel_id)
    
    await callback.message.answer(
        f"💰 *Введите оплату* (руб./чел.)\n\n"
        f"Город: {city.name}\n"
        f"Пример: 2500",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_price)
    await callback.answer()

@router.message(PostStates.editing_price)
async def create_post_price(message: Message, state: FSMContext):
    """Ввод стоимости"""
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    try:
        price = int(message.text)
        if price <= 0:
            await message.answer("❌ Стоимость должна быть больше 0!")
            return
        await state.update_data(price_per_person=price)
    except ValueError:
        await message.answer("❌ Введите число! Пример: 2500")
        return
    
    await message.answer(
        "👥 *Введите количество требуемых человек*\n\n"
        "Пример: 5",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_workers_count)

@router.message(PostStates.editing_workers_count)
async def create_post_workers_count(message: Message, state: FSMContext):
    """Ввод количества человек"""
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    try:
        workers = int(message.text)
        if workers <= 0:
            await message.answer("❌ Количество человек должно быть больше 0!")
            return
        await state.update_data(workers_count=workers)
    except ValueError:
        await message.answer("❌ Введите число! Пример: 5")
        return
    
    await message.answer(
        "📅 *Введите дату и время начала работ*\n\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Пример: 25.05.2026 10:15\n\n"
        "Важно: используйте МОСКОВСКОЕ время",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_date)

@router.message(PostStates.editing_date)
async def create_post_date(message: Message, state: FSMContext):
    """Ввод даты и времени"""
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    start_datetime = parse_datetime(message.text)
    
    if not start_datetime:
        await message.answer(
            "❌ Неверный формат!\n\n"
            "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Пример: 25.05.2026 10:15"
        )
        return
    
    # Проверяем, что дата не в прошлом
    if start_datetime < datetime.now():
        await message.answer("❌ Дата и время не могут быть в прошлом! Укажите будущую дату.")
        return
    
    await state.update_data(start_datetime=start_datetime)
    await state.update_data(start_datetime_text=message.text)
    
    await message.answer(
        "📍 *Введите адрес проведения работ*\n\n"
        "Пример: г. Мытищи, ул. Железнодорожная д.20",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_address)

@router.message(PostStates.editing_address)
async def create_post_address(message: Message, state: FSMContext):
    """Ввод адреса"""
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    await state.update_data(address=message.text)
    
    await message.answer(
        "📝 *Введите описание работ*\n\n"
        "Подробно опишите, что нужно делать:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_description)

@router.message(PostStates.editing_description)
async def create_post_description(message: Message, state: FSMContext, db: AsyncSession, bot):
    """Ввод описания и публикация"""
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    await state.update_data(work_description=message.text)
    
    data = await state.get_data()
    
    # Создаём новую заявку
    new_order = Order(
        customer_id=None,
        city_id=data['city_id'],
        full_name="Администратор",
        contact_phone="",
        workers_count=data['workers_count'],
        work_description=data['work_description'],
        start_datetime=data['start_datetime'],
        estimated_hours=0,
        address=data['address'],
        username_for_contact=None,
        status='active',
        price_per_person=data['price_per_person']
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)
    
    # Формируем текст поста
    post_text = f"""
🏗️ *НОВАЯ ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {data['start_datetime'].strftime('%d.%m.%Y')}
🕐 *Время:* {data['start_datetime'].strftime('%H:%M')}

📍 *Адрес:* {data['address']}

👥 *Требуется человек:* {data['workers_count']}

📝 *Суть работы:*
{data['work_description']}

💰 *Оплата:* {data['price_per_person']} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться на заявку!
"""
    
    # Клавиатура для поста
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{new_order.id}")]
    ])
    
    try:
        # 1. Отправляем пост в канал
        sent_message = await bot.send_message(
            chat_id=data['channel_id'],
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # 2. Отправляем пост исполнителям
        result = await db.execute(
            select(User, Worker)
            .join(Worker, User.id == Worker.user_id)
            .join(worker_city, Worker.id == worker_city.c.worker_id)
            .where(worker_city.c.city_id == data['city_id'])
            .where(User.is_registered == True)
        )
        workers = result.all()
        
        sent_to_workers = 0
        for user, worker in workers:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"🔔 *Новая заявка в городе {data['city_name']}!*\n\n{post_text}",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                sent_to_workers += 1
            except Exception as e:
                print(f"Не удалось отправить {user.telegram_id}: {e}")
        
        # Обновляем заявку
        new_order.channel_post_id = sent_message.message_id
        new_order.posted_at = datetime.now()
        await db.commit()
        
        await message.answer(
            f"✅ *Пост успешно опубликован!*\n\n"
            f"🏙️ Город: {data['city_name']}\n"
            f"📢 Канал: {data['channel_id']}\n"
            f"💰 Оплата: {data['price_per_person']} руб./чел.\n"
            f"👥 Требуется: {data['workers_count']} чел.\n"
            f"🕐 Время: {data['start_datetime'].strftime('%d.%m.%Y %H:%M')}\n"
            f"🆔 ID сообщения: {sent_message.message_id}\n"
            f"👥 Отправлено исполнителям: {sent_to_workers} чел.\n"
            f"📅 Время публикации: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при публикации: {str(e)}")
        await db.delete(new_order)
        await db.commit()
    
    await state.clear()

async def cancel_create_post(message: Message, state: FSMContext):
    """Отмена создания поста"""
    await state.clear()
    await message.answer(
        "❌ Создание поста отменено",
        reply_markup=get_main_menu('admin')
    )

@router.callback_query(lambda c: c.data == "cancel_create_post")
async def cancel_create_post_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена создания поста (callback)"""
    await state.clear()
    await callback.message.answer("❌ Создание поста отменено")
    await callback.answer()