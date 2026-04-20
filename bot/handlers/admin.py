from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
from bot.database.models import User, City, Order, Assignment, Worker
from bot.utils.states import AdminStates
from bot.config import settings

router = Router()

# Проверка прав администратора
async def is_admin(telegram_id: int, db: AsyncSession) -> bool:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user is not None and user.role == 'admin'

# Главное меню админа
@router.message(F.text == "📋 Активные заявки")
async def show_active_orders(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    # Заявки на сегодня и завтра
    result = await db.execute(
        select(Order).where(
            Order.status == 'active',
            Order.start_datetime >= today,
            Order.start_datetime <= tomorrow + timedelta(days=1)
        )
    )
    orders = result.scalars().all()
    
    if not orders:
        await message.answer("📭 Нет активных заявок на сегодня и завтра")
        return
    
    text = "📋 *Активные заявки*\n\n"
    for order in orders:
        # Получаем город
        city_result = await db.execute(select(City).where(City.id == order.city_id))
        city = city_result.scalar_one()
        
        text += f"🏙️ *{city.name}*\n"
        text += f"🕐 Время: {order.start_datetime.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"👥 Количество человек: {order.workers_count}\n"
        
        # Количество откликнувшихся
        assignments_result = await db.execute(
            select(Assignment).where(Assignment.order_id == order.id)
        )
        assignments = assignments_result.scalars().all()
        text += f"📌 Откликнулось: {len(assignments)} чел.\n"
        text += f"🆔 ID заявки: `{order.id}`\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🏙️ Управление городами")
async def manage_cities(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    result = await db.execute(select(City))
    cities = result.scalars().all()
    
    if not cities:
        await message.answer("📭 Список городов пуст")
        return
    
    keyboard = []
    for city in cities:
        status = "✅" if city.is_active else "❌"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {city.name}",
                callback_data=f"city_{city.id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="➕ Добавить город", callback_data="add_city")])
    
    await message.answer(
        "🏙️ *Управление городами*\n\n"
        "Выберите город для управления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("city_"))
async def city_detail(callback: CallbackQuery, db: AsyncSession):
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Скрыть" if city.is_active else "✅ Показать",
            callback_data=f"toggle_{city_id}"
        )],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{city_id}")],
        [InlineKeyboardButton(text="📢 Настроить канал", callback_data=f"channel_{city_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_cities")]
    ])
    
    await callback.message.edit_text(
        f"🏙️ *{city.name}*\n\n"
        f"Статус: {'Активен' if city.is_active else 'Скрыт'}\n"
        f"ID канала: {city.channel_id or 'Не указан'}\n"
        f"Создан: {city.created_at.strftime('%d.%m.%Y')}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "add_city")
async def add_city_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_city_name)
    await callback.message.answer(
        "🏙️ Введите название нового города:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_city")]
        ])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_city_name)
async def add_city_name(message: Message, state: FSMContext, db: AsyncSession):
    await state.update_data(city_name=message.text)
    await state.set_state(AdminStates.waiting_for_channel_id)
    
    await message.answer(
        f"📢 Введите ID Telegram-канала для города *{message.text}*\n\n"
        "Как получить ID канала:\n"
        "1. Добавьте бота в канал как администратора\n"
        "2. Отправьте любое сообщение в канал\n"
        "3. Перешлите это сообщение боту\n"
        "4. Бот покажет ID",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_channel")]
        ])
    )

@router.message(AdminStates.waiting_for_channel_id)
async def add_city_channel(message: Message, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    city_name = data['city_name']
    
    # Проверяем, не существует ли уже город
    result = await db.execute(select(City).where(City.name == city_name))
    existing = result.scalar_one_or_none()
    
    if existing:
        await message.answer(f"❌ Город {city_name} уже существует!")
        await state.clear()
        return
    
    new_city = City(
        name=city_name,
        channel_id=message.text if message.text != "⏭️ Пропустить" else None,
        is_active=True
    )
    db.add(new_city)
    await db.commit()
    
    await message.answer(f"✅ Город *{city_name}* успешно добавлен!", parse_mode="Markdown")
    await state.clear()

@router.callback_query(lambda c: c.data == "skip_channel")
async def skip_channel(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    city_name = data['city_name']
    
    new_city = City(name=city_name, channel_id=None, is_active=True)
    db.add(new_city)
    await db.commit()
    
    await callback.message.answer(f"✅ Город *{city_name}* успешно добавлен без привязки канала!", parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("toggle_"))
async def toggle_city(callback: CallbackQuery, db: AsyncSession):
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    city.is_active = not city.is_active
    await db.commit()
    
    await callback.answer(f"Город {city.name} {'скрыт' if not city.is_active else 'показан'}")
    
    # Обновляем сообщение
    await city_detail(callback, db)

@router.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_city(callback: CallbackQuery, db: AsyncSession):
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    await db.delete(city)
    await db.commit()
    
    await callback.answer(f"Город {city.name} удалён")
    await callback.message.edit_text(f"✅ Город *{city.name}* успешно удалён!", parse_mode="Markdown")

@router.message(F.text == "📢 Уведомления")
async def send_notification_menu(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Заказчикам", callback_data="notify_customers")],
        [InlineKeyboardButton(text="🔧 Исполнителям", callback_data="notify_workers")],
        [InlineKeyboardButton(text="👑 Администраторам", callback_data="notify_admins")],
        [InlineKeyboardButton(text="🌍 По городам", callback_data="notify_by_city")]
    ])
    
    await message.answer(
        "📢 *Уведомления*\n\n"
        "Выберите кому отправить сообщение:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("notify_"))
async def notification_type(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    await state.update_data(notification_role=role)
    await state.set_state(AdminStates.waiting_for_notification_text)
    
    await callback.message.answer(
        "✏️ Введите текст сообщения для рассылки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")]
        ])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_notification_text)
async def send_notification(message: Message, state: FSMContext, db: AsyncSession, bot):
    data = await state.get_data()
    role = data.get('notification_role')
    text = message.text
    
    # Получаем пользователей по роли
    if role == 'customers':
        result = await db.execute(
            select(User).where(User.role == 'customer', User.is_registered == True)
        )
    elif role == 'workers':
        result = await db.execute(
            select(User).where(User.role == 'worker', User.is_registered == True)
        )
    elif role == 'admins':
        result = await db.execute(
            select(User).where(User.role == 'admin', User.is_registered == True)
        )
    else:
        result = await db.execute(
            select(User).where(User.is_registered == True)
        )
    
    users = result.scalars().all()
    
    sent = 0
    for user in users:
        try:
            await bot.send_message(user.telegram_id, f"📢 *Уведомление от администратора*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            pass
    
    await message.answer(f"✅ Уведомление отправлено {sent} пользователям!")
    await state.clear()