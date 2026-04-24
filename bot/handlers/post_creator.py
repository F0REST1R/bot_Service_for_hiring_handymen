from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from bot.database.models import Order, City, Worker, Assignment, worker_city, User
from bot.utils.states import PostStates
from bot.utils.time_utils import parse_datetime_moscow, format_datetime_moscow
from bot.config import settings
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard

router = Router()

@router.message(F.text == "📝 Создать пост")
async def create_post_start(message: Message, state: FSMContext, db: AsyncSession):
    """Начало создания поста - выбор города"""
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    result = await db.execute(select(City).where(City.is_active == True, City.channel_id.isnot(None)))
    cities = result.scalars().all()
    
    if not cities:
        await message.answer("❌ Нет доступных городов с привязанными каналами!")
        return
    
    keyboard = []
    for city in cities:
        keyboard.append([InlineKeyboardButton(text=f"🏙️ {city.name}", callback_data=f"create_post_city_{city.id}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_post")])
    
    await message.answer(
        "📝 *Создание новой заявки*\n\nВыберите город:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.choosing_city)

@router.callback_query(PostStates.choosing_city, lambda c: c.data.startswith("create_post_city_"))
async def create_post_city_selected(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    city_id = int(callback.data.split("_")[3])
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    await state.update_data(city_id=city_id, city_name=city.name, channel_id=city.channel_id)
    
    await callback.message.answer(
        "💰 *Введите оплату* (руб./чел.)\nПример: 2500",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.entering_price)
    await callback.answer()

@router.message(PostStates.entering_price)
async def create_post_price(message: Message, state: FSMContext):
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
        "👥 *Введите количество требуемых человек*\nПример: 5",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_workers_count)

@router.message(PostStates.editing_workers_count)
async def create_post_workers_count(message: Message, state: FSMContext):
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
        "Важно: вводите МОСКОВСКОЕ время",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_date)

@router.message(PostStates.editing_date)
async def create_post_date(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    start_datetime = parse_datetime_moscow(message.text)
    
    if not start_datetime:
        await message.answer("❌ Неверный формат! Используйте: ДД.ММ.ГГГГ ЧЧ:ММ\nПример: 25.05.2026 10:15")
        return
    
    # Проверяем, что дата не в прошлом (сравниваем с текущим UTC)
    if start_datetime < datetime.now():
        await message.answer("❌ Дата и время не могут быть в прошлом! Укажите будущую дату.")
        return
    
    await state.update_data(start_datetime=start_datetime, start_datetime_text=message.text)
    
    await message.answer(
        "📍 *Введите адрес проведения работ*\nПример: г. Мытищи, ул. Железнодорожная д.20",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_address)

@router.message(PostStates.editing_address)
async def create_post_address(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    await state.update_data(address=message.text)
    
    await message.answer(
        "📝 *Введите описание работ*\nПодробно опишите, что нужно делать:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_description)

@router.message(PostStates.editing_description)
async def create_post_description(message: Message, state: FSMContext, db: AsyncSession, bot):
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    await state.update_data(work_description=message.text)
    data = await state.get_data()
    
    # Создаём заявку с корректным временем
    new_order = Order(
        customer_id=None,
        city_id=data['city_id'],
        full_name="Администратор",
        contact_phone="",
        workers_count=data['workers_count'],
        work_description=data['work_description'],
        start_datetime=data['start_datetime'],  # Уже в UTC
        estimated_hours=0,
        address=data['address'],
        username_for_contact=None,
        status='active',
        price_per_person=data['price_per_person']
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)
    
    # Формируем текст поста с московским временем
    moscow_time = format_datetime_moscow(data['start_datetime'])
    post_text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {data['start_datetime_text']}
🕐 *Время:* {moscow_time.split()[1]}

📍 *Адрес:* {data['address']}

👥 *Требуется человек:* {data['workers_count']}

📝 *Суть работы:*
{data['work_description']}

💰 *Оплата:* {data['price_per_person']} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{new_order.id}")]
    ])
    
    try:
        sent_message = await bot.send_message(
            chat_id=data['channel_id'],
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Рассылка исполнителям
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
        
        new_order.channel_post_id = sent_message.message_id
        new_order.posted_at = datetime.now()
        await db.commit()
        
        await message.answer(
            f"✅ *Пост опубликован!*\n\n"
            f"🏙️ Город: {data['city_name']}\n"
            f"📢 Канал: {data['channel_id']}\n"
            f"💰 {data['price_per_person']} руб./чел.\n"
            f"👥 {data['workers_count']} чел.\n"
            f"🕐 {format_datetime_moscow(data['start_datetime'])}\n"
            f"👥 Отправлено: {sent_to_workers} чел.",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await db.delete(new_order)
        await db.commit()
    
    await state.clear()

async def is_admin(telegram_id: int, db: AsyncSession) -> bool:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user is not None and user.role == 'admin'

async def cancel_create_post(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Создание поста отменено", reply_markup=get_main_menu('admin'))

@router.callback_query(lambda c: c.data == "cancel_create_post")
async def cancel_create_post_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Создание поста отменено")
    await callback.answer()