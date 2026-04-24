from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
from bot.database.models import User, City, Order, Assignment, Worker, worker_city
from bot.utils.states import AdminStates, PostStates
from bot.utils.time_utils import format_datetime_moscow
from bot.config import settings
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.handlers.posts import format_post_text
from bot.handlers.post_creator import cancel_create_post
from datetime import timedelta
import pytz
import re

router = Router()

# Проверка прав администратора
async def is_admin(telegram_id: int, db: AsyncSession) -> bool:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user is not None and user.role == 'admin'

@router.message(F.text == "📋 Активные заявки")
async def show_active_orders(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    # Получаем текущее московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    today_moscow = now_moscow.date()
    tomorrow_moscow = today_moscow + timedelta(days=1)
    
    # Получаем ВСЕ активные заявки
    result = await db.execute(
        select(Order, City)
        .join(City, Order.city_id == City.id)
        .order_by(Order.start_datetime)
    )
    all_orders = result.all()
    
    # Фильтруем заявки по московской дате (только сегодня и завтра)
    filtered_orders = []
    for order, city in all_orders:
        # Конвертируем UTC в московское время
        order_moscow_time = order.start_datetime + timedelta(hours=3)
        order_date = order_moscow_time.date()
        
        if order_date == today_moscow or order_date == tomorrow_moscow:
            filtered_orders.append((order, city, order_moscow_time))
    
    if not filtered_orders:
        await message.answer("📭 Нет активных заявок на сегодня и завтра")
        return
    
    text = "📋 *Активные заявки на сегодня и завтра*\n"
    text += "*Для просмотра деталей отправьте:* `Заявка <ID>`\n\n"
    
    for order, city, moscow_time in filtered_orders:
        # Получаем количество откликнувшихся
        assignments_result = await db.execute(
            select(Assignment).where(Assignment.order_id == order.id)
        )
        assignments = assignments_result.scalars().all()
        assignments_count = len(assignments)

        # Статус публикации поста
        if order.channel_post_id:
            post_status = "✅ Опубликован"
        else:
            post_status = "❌ Не опубликован"

        # Определяем статус набора
        if assignments_count >= order.workers_count:
            status_icon = "✅"
            status_text = "Набор закрыт (все места заняты)"
        else:
            status_icon = "❌"
            status_text = "Требуются рабочие"
            remaining = order.workers_count - assignments_count
            status_text += f" (осталось {remaining} мест)"
        
        text += f"🏙️ Город: {city.name} ID: `{order.id}`\n"
        text += f"🕐 Время: {moscow_time.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"👥 Требуется: {order.workers_count} чел.\n"
        text += f"📌 Откликнулось: {assignments_count} чел.\n"
        text += f"📢 Пост: {post_status}\n"
        text += f"{status_icon} {status_text}\n"
        text += f"---\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text.regexp(r'^Заявка\s+(\d+)$', flags=re.IGNORECASE))
async def show_order_details(message: Message, db: AsyncSession):
    """Показать детали заявки по ID"""
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    import re
    match = re.match(r'^Заявка\s+(\d+)$', message.text, re.IGNORECASE)
    if not match:
        await message.answer("❌ Неверный формат. Используйте: Заявка 123")
        return
    
    order_id = int(match.group(1))
    
    # Получаем заявку с городом
    result = await db.execute(
        select(Order, City)
        .join(City, Order.city_id == City.id)
        .where(Order.id == order_id)
    )
    order_data = result.first()
    
    if not order_data:
        await message.answer(f"❌ Заявка с ID {order_id} не найдена")
        return
    
    order, city = order_data
    
    # Получаем всех откликнувшихся рабочих
    assignments_result = await db.execute(
        select(Assignment, Worker, User)
        .join(Worker, Assignment.worker_id == Worker.id)
        .join(User, Worker.user_id == User.id)
        .where(Assignment.order_id == order_id)
    )
    assignments = assignments_result.all()
    
    # Получаем количество откликнувшихся
    assignments_count = len(assignments)
    
    # Определяем статус набора по количеству откликнувшихся
    if assignments_count >= order.workers_count:
        status_icon = "✅"
        status_text = "Набор закрыт (все места заняты)"
    else:
        status_icon = "❌"
        status_text = "Набор открыт"
    
    # Формируем текст заявки с правильным временем
    from bot.utils.time_utils import format_datetime_moscow
    
    order_text = f"""
📋 *ДЕТАЛИ ЗАЯВКИ* 🆔 #{order.id}

🏢 *Заказчик:* {order.full_name}
📞 *Телефон:* {order.contact_phone}
👥 *Количество человек:* {order.workers_count}
📝 *Суть работы:* {order.work_description}
🕐 *Дата и время:* {format_datetime_moscow(order.start_datetime)}
⏱️ *Время занятости:* {order.estimated_hours} ч.
🏙️ *Город:* {city.name}
📍 *Адрес:* {order.address}
👤 *Username:* @{order.username_for_contact if order.username_for_contact else 'не указан'}
💰 *Оплата:* {order.price_per_person if order.price_per_person else 'не указана'} руб./чел.

📊 *Статус:* {status_icon} {status_text}
📢 *Пост:* {'✅ Опубликован' if order.channel_post_id else '❌ Не опубликован'}
📅 *Создана:* {format_datetime_moscow(order.created_at)}
"""

    # Добавляем информацию об откликнувшихся
    if assignments:
        order_text += f"\n👥 *Откликнувшиеся исполнители:* ({assignments_count} чел.)\n\n"
        for i, (assignment, worker, user) in enumerate(assignments, 1):
            order_text += f"{i}. *{worker.full_name}*\n"
            order_text += f"   📞 Телефон: {worker.phone}\n"
            order_text += f"   📅 Возраст: {worker.age}\n"
            order_text += f"   🌍 Гражданство: {worker.citizenship}\n"
            order_text += f"   📌 Отклик: {format_datetime_moscow(assignment.assigned_at)}\n\n"
    else:
        order_text += "\n📭 *Откликнувшиеся исполнители:* нет\n"
    
    # Кнопки для администратора
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        
    # Кнопка создания поста
    if not order.channel_post_id:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="📢 Создать пост", callback_data=f"admin_create_post_{order.id}")]
        )
    else:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="✅ Пост создан", callback_data="post_already_created")]
        )

    # Кнопка закрыть/открыть набор
    if order.status == 'active':
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="🔒 Закрыть набор", callback_data=f"close_order_{order.id}")]
        )
    else:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="🔓 Открыть набор", callback_data=f"open_order_{order.id}")]
        )
    
    # Кнопка повторной отправки (только если пост создан)
    if order.channel_post_id:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="🔄 Повторно отправить", callback_data=f"resend_post_{order.id}")]
        )
    
    await message.answer(order_text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("close_order_"))
async def close_order(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    """Закрыть набор на заявку"""
    order_id = int(callback.data.split("_")[2])
    
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    order.status = 'closed'
    await db.commit()
    
    await callback.answer(f"✅ Набор на заявку {order_id} закрыт")
    
    # Обновляем сообщение с деталями
    await show_order_details(callback.message, db)
    await callback.message.delete()
    await callback.message.answer(f"✅ Набор на заявку {order_id} закрыт!")

@router.callback_query(lambda c: c.data.startswith("open_order_"))
async def open_order(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    """Открыть набор на заявку"""
    order_id = int(callback.data.split("_")[2])
    
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    order.status = 'active'
    await db.commit()
    
    await callback.answer(f"✅ Набор на заявку {order_id} открыт")
    
    # Обновляем сообщение с деталями
    await show_order_details(callback.message, db)
    await callback.message.delete()
    await callback.message.answer(f"✅ Набор на заявку {order_id} открыт!")

@router.callback_query(lambda c: c.data == "post_already_created")
async def post_already_created(callback: CallbackQuery):
    await callback.answer("Пост для этой заявки уже создан", show_alert=True)

@router.message(F.text.regexp(r'^Отклики\s+(\d+)$', flags=re.IGNORECASE))
async def show_order_assignments(message: Message, db: AsyncSession):
    """Показать откликнувшихся на заявку"""
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    import re
    match = re.match(r'^Отклики\s+(\d+)$', message.text, re.IGNORECASE)
    if not match:
        await message.answer("❌ Неверный формат. Используйте: Отклики 123")
        return
    
    order_id = int(match.group(1))
    
    # Проверяем, существует ли заявка
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        await message.answer(f"❌ Заявка с ID {order_id} не найдена")
        return
    
    # Получаем откликнувшихся
    result = await db.execute(
        select(Assignment, Worker, User)
        .join(Worker, Assignment.worker_id == Worker.id)
        .join(User, Worker.user_id == User.id)
        .where(Assignment.order_id == order_id)
    )
    assignments = result.all()
    
    if not assignments:
        await message.answer(f"📭 На заявку {order_id} никто не откликнулся")
        return
    
    text = f"👥 <b>Откликнувшиеся на заявку {order_id}:<b>\n\n"
    for i, (assignment, worker, user) in enumerate(assignments, 1):
        text += f"{i}. <b>{worker.full_name}</b>\n"
        text += f"   📞 Телефон: {worker.phone}\n"
        text += f"   📅 Возраст: {worker.age}\n"
        text += f"   🌍 Гражданство: {worker.citizenship}\n"
        text += f"   👤 Telegram: @{user.username if user.username else 'нет username'}\n"
        text += f"   📌 Отклик: {assignment.assigned_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "🏙️ Управление городами")
async def manage_cities(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    result = await db.execute(select(City).order_by(City.name))
    cities = result.scalars().all()
    
    if not cities:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить город", callback_data="add_city")]
        ])
        await message.answer("📭 Список городов пуст\n\n➕ Чтобы добавить город, нажмите кнопку ниже", reply_markup=keyboard)
        return
    
    text = "🏙️ *Список городов*\n\n"
    keyboard = []
    
    for city in cities:
        status = "✅" if city.is_active else "❌"
        channel_info = f"{city.channel_id}" if city.channel_id else "Не привязан"
        text += f"{status} *{city.name}*\n"
        text += f"   📢 Канал: {channel_info}\n\n"
        
        # Кнопки для каждого города
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {city.name}",
                callback_data=f"city_{city.id}"
            )
        ])
    
    # Кнопка добавления города
    keyboard.append([InlineKeyboardButton(text="➕ Добавить город", callback_data="add_city")])
    
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("city_"))
async def city_detail(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    channel_text = f"📢 Канал: {city.channel_id}" if city.channel_id else "📢 Канал: не привязан"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="👁️ Скрыть" if city.is_active else "👁️ Показать",
            callback_data=f"toggle_{city_id}"
        )],
        [InlineKeyboardButton(text="🔗 Привязать канал", callback_data=f"edit_channel_{city_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{city_id}")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_cities")]
    ])
    
    await callback.message.edit_text(
        f"🏙️ *{city.name}*\n\n"
        f"Статус: {'Активен ✅' if city.is_active else 'Скрыт ❌'}\n"
        f"{channel_text}\n"
        f"📅 Создан: {city.created_at.strftime('%d.%m.%Y')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "back_to_cities")
async def back_to_cities(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    # Получаем список городов заново
    result = await db.execute(select(City).order_by(City.name))
    cities = result.scalars().all()
    
    if not cities:
        text = "📭 Список городов пуст"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить город", callback_data="add_city")]
        ])
    else:
        text = "🏙️ *Список городов*\n\n"
        keyboard = []
        
        for city in cities:
            status = "✅" if city.is_active else "❌"
            channel_info = f"@{city.channel_id}" if city.channel_id else "Не привязан"
            text += f"{status} *{city.name}*\n"
            text += f"   📢 Канал: {channel_info}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} {city.name}",
                    callback_data=f"city_{city.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="➕ Добавить город", callback_data="add_city")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

# Новая система добавления города через состояния (как при регистрации)
@router.callback_query(lambda c: c.data == "add_city")
async def add_city_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_city_name)
    await callback.message.answer(
        "🏙️ Введите название нового города:",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_city_name)
async def add_city_name(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_add_city(message, state)
        return
    
    await state.update_data(city_name=message.text)
    await state.set_state(AdminStates.waiting_for_channel_id)
    
    await message.answer(
        f"📢 Введите ID Telegram-канала для города {message.text}\n\n"
        "Как получить ID канала:\n"
        "1. Добавьте бота в канал как администратора\n"
        "2. Отправьте любое сообщение в канал\n"
        "3. Перешлите это сообщение боту\n"
        "4. Бот покажет ID\n\n"
        "Пример: @moscow_channel\n\n"
        "Или отправьте 'Пропустить' чтобы добавить без канала",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Пропустить")], [KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )
@router.message(AdminStates.waiting_for_channel_id)
async def add_city_channel(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await cancel_add_city(message, state)
        return
    
    data = await state.get_data()
    city_name = data['city_name']
    
    # Проверяем, не существует ли уже город
    result = await db.execute(select(City).where(City.name == city_name))
    existing = result.scalar_one_or_none()
    
    if existing:
        await message.answer(f"❌ Город {city_name} уже существует!")
        await state.clear()
        return
    
    # Определяем channel_id
    if message.text == "Пропустить":
        channel_id = None
        channel_text = "без привязки канала"
    else:
        channel_id = message.text
        channel_text = f"с каналом {channel_id}"
    
    # Создаём новый город
    new_city = City(
        name=city_name,
        channel_id=channel_id,
        is_active=True
    )
    db.add(new_city)
    await db.commit()
    
    await message.answer(
        f"✅ Город {city_name} успешно добавлен {channel_text}!",
        reply_markup=get_main_menu('admin')
    )
    await state.clear()

async def cancel_add_city(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Добавление города отменено",
        reply_markup=get_main_menu('admin')
    )

@router.callback_query(lambda c: c.data.startswith("edit_channel_"))
async def edit_city_channel_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    city_id = int(callback.data.split("_")[2])
    await state.update_data(edit_city_id=city_id)
    await state.set_state(AdminStates.waiting_for_channel_id_edit)
    
    await callback.message.answer(
        "📢 Введите новый ID Telegram-канала для города:\n\n"
        "Пример: @moscow_channel\n\n"
        "Или отправьте '0' чтобы удалить привязку канала\n"
        "Или отправьте 'Пропустить' чтобы оставить как есть",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Пропустить")], [KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_channel_id_edit)
async def edit_city_channel(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Редактирование отменено",
            reply_markup=get_main_menu('admin')
        )
        return
    
    data = await state.get_data()
    city_id = data['edit_city_id']
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    if message.text == "Пропустить":
        await message.answer(f"✅ Канал для города {city.name} оставлен без изменений")
    elif message.text == "0":
        city.channel_id = None
        await db.commit()
        await message.answer(f"✅ Привязка канала для города {city.name} удалена")
    else:
        city.channel_id = message.text
        await db.commit()
        await message.answer(f"✅ Канал для города {city.name} обновлён: {message.text}")
    
    await state.clear()
    await message.answer("👋 Главное меню:", reply_markup=get_main_menu('admin'))
    
@router.callback_query(lambda c: c.data.startswith("toggle_"))
async def toggle_city(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    city.is_active = not city.is_active
    await db.commit()
    
    status = "скрыт" if not city.is_active else "показан"
    await callback.answer(f"Город {city.name} {status}")
    
    # Обновляем сообщение
    await city_detail(callback, db)

@router.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_city(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    city_name = city.name
    
    await db.delete(city)
    await db.commit()
    
    await callback.answer(f"Город {city_name} удалён")
    await callback.message.edit_text(f"✅ Город *{city_name}* успешно удалён!", parse_mode="Markdown")
    
    # Показываем обновлённый список городов
    await back_to_cities(callback, db)

@router.message(F.text == "📢 Уведомления")
async def send_notification_menu(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Заказчикам", callback_data="notify_customers")],
        [InlineKeyboardButton(text="🔧 Исполнителям", callback_data="notify_workers")],
        [InlineKeyboardButton(text="🌍 По городам", callback_data="notify_by_city")]
    ])
    
    await message.answer(
        "📢 *Уведомления*\n\n"
        "Выберите кому отправить сообщение:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("notify_"))
async def notification_type(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await callback.answer()
    notification_type = callback.data.split("_")[1]
    
    if notification_type == "by":
        # Уведомление по городам - показываем список городов
        result = await db.execute(select(City).where(City.is_active == True))
        cities = result.scalars().all()
        
        if not cities:
            await callback.message.answer("❌ Нет активных городов")
            await callback.answer()
            return
        
        keyboard = []
        for city in cities:
            keyboard.append([InlineKeyboardButton(text=city.name, callback_data=f"notify_city_{city.id}")])
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")])
        
        await callback.message.answer(
            "🌍 *Выберите город* для рассылки уведомления:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        await callback.answer()
        return
    
    await state.update_data(notification_role=notification_type)
    await state.set_state(AdminStates.waiting_for_notification_text)
    
    await callback.message.answer(
        "✏️ Введите текст сообщения для рассылки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")]
        ])
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("notify_city_"))
async def notify_by_city(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await callback.answer()
    city_id = int(callback.data.split("_")[2])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    await state.update_data(notification_role="by_city")
    await state.update_data(notification_city_id=city_id)
    await state.update_data(notification_city_name=city.name)
    await state.set_state(AdminStates.waiting_for_notification_text)
    
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        f"✏️ Введите текст сообщения для рассылки пользователям из города *{city.name}*:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_notification_text)
async def send_notification(message: Message, state: FSMContext, db: AsyncSession, bot):
    data = await state.get_data()
    role = data.get('notification_role')
    city_id = data.get('notification_city_id')
    city_name = data.get('notification_city_name')
    text = message.text
    
    # Получаем пользователей в зависимости от выбора
    if role == 'customers':
        result = await db.execute(
            select(User).where(User.role == 'customer', User.is_registered == True)
        )
    elif role == 'workers':
        result = await db.execute(
            select(User).where(User.role == 'worker', User.is_registered == True)
        )
    elif role == 'by_city' and city_id:
        # Получаем исполнителей из выбранного города
        result = await db.execute(
            select(User)
            .join(Worker, User.id == Worker.user_id)
            .join(worker_city, Worker.id == worker_city.c.worker_id)
            .where(worker_city.c.city_id == city_id)
        )
    else:
        result = await db.execute(
            select(User).where(User.is_registered == True)
        )
    
    users = result.scalars().all()
    
    title = "📢 *Уведомление от администратора*"
    
    sent = 0
    for user in users:
        try:
            await bot.send_message(
                user.telegram_id, 
                f"{title}\n\n{text}", 
                parse_mode="Markdown"
            )
            sent += 1
        except Exception as e:
            print(f"Не удалось отправить сообщение пользователю {user.telegram_id}: {e}")
    
    if city_name:
        await message.answer(f"✅ Уведомление отправлено исполнителям из города {city_name}!")
    else:
        await message.answer(f"✅ Уведомление отправлено пользователям!")
    
    await state.clear()

@router.callback_query(lambda c: c.data == "cancel_notification")
async def cancel_notification(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ Рассылка отменена")
    
    # Возвращаемся в главное меню админа
    await callback.message.answer(
        "👋 Главное меню:",
        reply_markup=get_main_menu('admin')
    )
    await callback.answer()

@router.message(F.text == "📊 Аналитика")
async def show_analytics(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    # Ссылка на Google таблицу (потом замените на реальную)
    google_sheets_url = "https://docs.google.com/spreadsheets/d/157voo32aW7_DXac6R-R9mtAHDmO7SDJo9Tq9jOtp9JA/edit?gid=0#gid=0"
    
    await message.answer(
        "📊 <b>Аналитика</b>\n\n"
        "Все данные собираются в Google таблице.\n\n"
        "Ссылка на таблицу:\n"
        f"<a href='{google_sheets_url}'>Открыть таблицу</a>\n\n",
        parse_mode="HTML"
    )

@router.callback_query(lambda c: c.data.startswith("apply_order_"))
async def apply_for_order(callback: CallbackQuery, db: AsyncSession):
    """Обработчик нажатия кнопки 'Я поеду' - универсальный, кнопка не меняется"""
    order_id = int(callback.data.split("_")[2])
    
    # Проверяем, зарегистрирован ли пользователь
    result = await db.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    
    if not user:
        await callback.answer(
            "❌ Сначала зарегистрируйтесь!\n"
            "Нажмите /start и пройдите регистрацию как исполнитель",
            show_alert=True
        )
        return
    
    if user.role != 'worker':
        await callback.answer(
            "❌ Только исполнители могут откликаться на заявки!\n"
            "Зарегистрируйтесь как исполнитель через /start",
            show_alert=True
        )
        return
    
    # Получаем исполнителя
    result = await db.execute(select(Worker).where(Worker.user_id == user.id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        await callback.answer(
            "❌ Сначала завершите регистрацию исполнителя через /start",
            show_alert=True
        )
        return
    
    # Получаем заявку
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return
    
    # Проверяем, открыт ли набор
    if order.status != 'active':
        await callback.answer("❌ Набор на эту заявку уже закрыт!", show_alert=True)
        return
    
    # Проверяем, не откликался ли уже
    result = await db.execute(
        select(Assignment).where(
            Assignment.order_id == order_id,
            Assignment.worker_id == worker.id
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        await callback.answer(
            "❌ Вы уже откликнулись на эту заявку!\n"
            "Ожидайте звонка администратора",
            show_alert=True
        )
        return
    
    # Проверяем, есть ли свободные места
    result = await db.execute(
        select(Assignment).where(Assignment.order_id == order_id)
    )
    current_assignments = result.scalars().all()
    
    if len(current_assignments) >= order.workers_count:
        # Набор закрыт
        order.status = 'closed'
        await db.commit()
        await callback.answer(
            "❌ Набор на эту заявку уже закрыт!\n"
            "Все места заняты",
            show_alert=True
        )
        return
    
    # Создаём отклик
    new_assignment = Assignment(
        order_id=order_id,
        worker_id=worker.id
    )
    db.add(new_assignment)
    
    # Проверяем, не набралось ли полное количество
    result = await db.execute(
        select(Assignment).where(Assignment.order_id == order_id)
    )
    all_assignments = result.scalars().all()
    
    if len(all_assignments) >= order.workers_count:
        order.status = 'closed'
    
    await db.commit()
    
    # Уведомляем администраторов о новом отклике
    admin_ids = settings.ADMIN_IDS
    for admin_id in admin_ids:
        try:
            # Получаем город
            city_result = await db.execute(select(City).where(City.id == order.city_id))
            city = city_result.scalar_one()
            
            await callback.bot.send_message(
                admin_id,
                f"✅ *НОВЫЙ ОТКЛИК!*\n\n"
                f"👤 Исполнитель: {worker.full_name}\n"
                f"📞 Телефон: {worker.phone}\n"
                f"📅 Возраст: {worker.age}\n"
                f"🌍 Гражданство: {worker.citizenship}\n"
                f"🆔 Заявка #{order_id}\n"
                f"🏙️ Город: {city.name}\n"
                f"👥 Мест занято: {len(all_assignments)}/{order.workers_count}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")
    
    # Ответ пользователю
    remaining_spots = order.workers_count - len(all_assignments)
    if remaining_spots > 0:
        await callback.answer(
            f"✅ Вы успешно откликнулись на заявку #{order_id}!\n"
            f"Осталось мест: {remaining_spots}",
            show_alert=True
        )
    else:
        await callback.answer(
            f"✅ Вы успешно откликнулись на заявку #{order_id}!\n"
            f"⚠️ ВНИМАНИЕ: Вы последний! Набор закрыт.",
            show_alert=True
        )
    
    # Отправляем личное сообщение пользователю с подтверждением
    try:
        await callback.bot.send_message(
            callback.from_user.id,
            f"✅ *Вы откликнулись на заявку #{order_id}!*\n\n"
            f"Ожидайте звонка от администратора для подтверждения.\n"
            f"Осталось мест: {remaining_spots} из {order.workers_count}",
            parse_mode="Markdown"
        )
    except:
        pass
    
    await callback.answer()

    # Обновляем Google Sheets
    google_client = callback.bot.get('google_client')
    if google_client:
        google_client.add_response(order_id, worker.full_name, worker.phone)

@router.callback_query(lambda c: c.data.startswith("resend_post_"))
async def resend_post(callback: CallbackQuery, state: FSMContext, db: AsyncSession, bot):
    await callback.answer()
    """Повторная отправка поста исполнителям"""
    order_id = int(callback.data.split("_")[2])
    
    # Получаем заявку и город
    result = await db.execute(
        select(Order, City)
        .join(City, Order.city_id == City.id)
        .where(Order.id == order_id)
    )
    order_data = result.first()
    
    if not order_data:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    
    order, city = order_data
    
    if not order.price_per_person:
        await callback.answer("Сначала укажите стоимость в заявке", show_alert=True)
        return
    
    # Формируем текст поста
    post_text = format_post_text(order, city, order.price_per_person)
    
    # Клавиатура для отклика
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{order_id}")]
    ])
    
    # Отправляем исполнителям
    result = await db.execute(
        select(User, Worker)
        .join(Worker, User.id == Worker.user_id)
        .join(worker_city, Worker.id == worker_city.c.worker_id)
        .where(worker_city.c.city_id == city.id)
        .where(User.is_registered == True)
    )
    workers = result.all()
    
    sent = 0
    for user, worker in workers:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=f"🔔 *Новая заявка в вашем городе!*\n\n{post_text}",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            sent += 1
        except Exception as e:
            print(f"Не удалось отправить {user.telegram_id}: {e}")
    
    await callback.answer(f"✅ Отправлено {sent} исполнителям")

@router.callback_query(lambda c: c.data.startswith("admin_create_post_"))
async def admin_create_post_from_order(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    """Создание поста из заявки - сначала запрашиваем цену"""
    order_id = int(callback.data.split("_")[3])
    
    # Получаем заявку
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    
    if order.channel_post_id:
        await callback.answer("Пост для этой заявки уже создан!", show_alert=True)
        return
    
    # Получаем город
    result = await db.execute(select(City).where(City.id == order.city_id))
    city = result.scalar_one()
    
    if not city.channel_id:
        await callback.answer(f"К городу {city.name} не привязан канал!", show_alert=True)
        return
    
    # Сохраняем данные в состояние (без datetime)
    await state.update_data(
        order_id=order_id,
        city_id=city.id,
        city_name=city.name,
        channel_id=city.channel_id,
        workers_count=order.workers_count,
        start_datetime_str=order.start_datetime.isoformat(),
        start_datetime_text=order.start_datetime.strftime('%d.%m.%Y %H:%M'),
        estimated_hours=order.estimated_hours,
        address=order.address,
        work_description=order.work_description,
        current_price=order.price_per_person if order.price_per_person else 0
    )
    
    # Запрашиваем цену
    await callback.message.answer(
        f"💰 *Введите оплату для заявки #{order_id}* (руб./чел.)\n\n"
        f"Пример: 2500\n\n"
        f"Город: {city.name}\n"
        f"Адрес: {order.address}\n"
        f"Требуется: {order.workers_count} чел.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_post")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.entering_price)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("confirm_post_"))
async def confirm_post_publish(callback: CallbackQuery, state: FSMContext, db: AsyncSession, bot):
    """Подтверждение и публикация поста"""
    order_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    
    # Получаем заявку
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    
    # Получаем город
    result = await db.execute(select(City).where(City.id == data['city_id']))
    city = result.scalar_one()
    
    # Обновляем цену в заявке
    order.price_per_person = data.get('current_price', 0)
    
    # Обновляем другие поля, если они изменились
    order.workers_count = data['workers_count']
    order.address = data['address']
    order.work_description = data['work_description']
    order.estimated_hours = data['estimated_hours']
    order.start_datetime = datetime.fromisoformat(data['start_datetime_str'])
    await db.commit()
    
    # Формируем итоговый пост
    post_text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {format_datetime_moscow(order.start_datetime)}

📍 *Адрес:* {order.address}

👥 *Требуется человек:* {order.workers_count}

⏱️ *Продолжительность:* {order.estimated_hours} ч.

📝 *Суть работы:*
{order.work_description}

💰 *Оплата:* {order.price_per_person} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{order.id}")]
    ])
    
    try:
        sent_message = await bot.send_message(
            chat_id=city.channel_id,
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        order.channel_post_id = sent_message.message_id
        order.posted_at = datetime.now()
        await db.commit()
        
        await callback.message.answer(
            f"✅ *Пост успешно опубликован в канале {city.name}!*\n\n"
            f"ID сообщения: {sent_message.message_id}",
            parse_mode="Markdown"
        )
        
        # Обновляем детали заявки
        await show_order_details(callback.message, db)
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при публикации: {str(e)}")
    
    await state.clear()
    await callback.answer()

    # Получаем google_client из контекста
    google_client = callback.bot.get('google_client')
    
    # После успешной публикации:
    if google_client:
        order_data_for_sheet = {
            'order_id': order.id,
            'created_at': order.created_at.strftime('%d.%m.%Y %H:%M'),
            'city': city.name,
            'customer_name': order.full_name,
            'customer_phone': order.contact_phone,
            'workers_count': order.workers_count,
            'start_datetime': format_datetime_moscow(order.start_datetime),
            'estimated_hours': order.estimated_hours,
            'address': order.address,
            'work_description': order.work_description,
            'price_per_person': order.price_per_person if order.price_per_person else 0,
            'post_status': 'Опубликован',
            'recruitment_status': 'Набор открыт',
            'responses_count': 0
        }
        google_client.save_order(order_data_for_sheet)

@router.callback_query(lambda c: c.data.startswith("publish_post_"))
async def publish_post_direct(callback: CallbackQuery, db: AsyncSession, bot):
    """Непосредственная публикация поста"""
    order_id = int(callback.data.split("_")[2])
    
    # Получаем заявку и город
    result = await db.execute(select(Order, City).join(City, Order.city_id == City.id).where(Order.id == order_id))
    order_data = result.first()
    
    if not order_data:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    
    order, city = order_data
    
    if order.channel_post_id:
        await callback.answer("Пост уже создан!", show_alert=True)
        return
    
    post_text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {order.start_datetime.strftime('%d.%m.%Y %H:%M') if not hasattr(order, 'start_datetime_text') else order.start_datetime_text}

📍 *Адрес:* {order.address}

👥 *Требуется человек:* {order.workers_count}

⏱️ *Продолжительность:* {order.estimated_hours} ч.

📝 *Суть работы:*
{order.work_description}

💰 *Оплата:* {order.price_per_person if order.price_per_person else 'не указана'} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{order.id}")]
    ])
    
    try:
        sent_message = await bot.send_message(
            chat_id=city.channel_id,
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        order.channel_post_id = sent_message.message_id
        order.posted_at = datetime.now()
        await db.commit()
        
        await callback.message.answer(f"✅ *Пост успешно опубликован в канале {city.name}!*", parse_mode="Markdown")
        
        # Обновляем детали заявки
        await show_order_details(callback.message, db)
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при публикации: {str(e)}")
    
    await callback.answer()

@router.message(PostStates.entering_price)
async def process_post_price(message: Message, state: FSMContext):
    """Ввод цены для поста"""
    if message.text == "❌ Отмена":
        await cancel_create_post(message, state)
        return
    
    try:
        price = int(message.text)
        if price <= 0:
            await message.answer("❌ Стоимость должна быть больше 0!")
            return
        await state.update_data(current_price=price)
    except ValueError:
        await message.answer("❌ Введите число! Пример: 2500")
        return
    
    data = await state.get_data()
    
    # Восстанавливаем datetime из строки
    from datetime import datetime
    start_datetime = datetime.fromisoformat(data['start_datetime_str'])
    
    # Показываем предпросмотр поста с ценой
    post_text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {start_datetime.strftime('%d.%m.%Y %H:%M')}

📍 *Адрес:* {data['address']}

👥 *Требуется человек:* {data['workers_count']}

⏱️ *Продолжительность:* {data['estimated_hours']} ч.

📝 *Суть работы:*
{data['work_description']}

💰 *Оплата:* {price} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"confirm_post_{data['order_id']}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_data")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="edit_post_price")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_post")]
    ])
    
    await message.answer(
        f"📝 *Предпросмотр поста для канала {data['city_name']}:*\n\n{post_text}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.confirming_post)

@router.callback_query(lambda c: c.data == "edit_post_data")
async def edit_post_data(callback: CallbackQuery, state: FSMContext):
    """Выбор поля для редактирования"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Адрес", callback_data="edit_field_address")],
        [InlineKeyboardButton(text="👥 Количество человек", callback_data="edit_field_workers")],
        [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_description")],
        [InlineKeyboardButton(text="⏱️ Продолжительность", callback_data="edit_field_hours")],
        [InlineKeyboardButton(text="📅 Дата и время", callback_data="edit_field_date")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
    ])
    
    await callback.message.answer(
        "✏️ *Что вы хотите отредактировать?*",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("edit_field_"))
async def edit_field(callback: CallbackQuery, state: FSMContext):
    """Редактирование конкретного поля"""
    field = callback.data.split("_")[2]
    await state.update_data(edit_field=field)
    
    prompts = {
        "address": "📍 *Введите новый адрес:*\nПример: г. Мытищи, ул. Железнодорожная д.20",
        "workers": "👥 *Введите новое количество человек:*\nПример: 5",
        "description": "📝 *Введите новое описание работ:*",
        "hours": "⏱️ *Введите новую продолжительность (в часах):*\nПример: 4, 6.5, 8",
        "date": "📅 *Введите новую дату и время:*\nФормат: ДД.ММ.ГГГГ ЧЧ:ММ\nПример: 25.05.2026 10:15"
    }
    
    await callback.message.answer(
        prompts.get(field, "Введите новое значение:"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.editing_field)
    await callback.answer()

@router.message(PostStates.editing_field)
async def save_edited_field(message: Message, state: FSMContext, db: AsyncSession):
    """Сохранение отредактированного поля"""
    data = await state.get_data()
    field = data.get('edit_field')
    new_value = message.text
    
    if field == "address":
        await state.update_data(address=new_value)
    elif field == "workers":
        try:
            workers = int(new_value)
            if workers <= 0:
                await message.answer("❌ Количество должно быть больше 0!")
                return
            await state.update_data(workers_count=workers)
        except ValueError:
            await message.answer("❌ Введите число!")
            return
    elif field == "description":
        await state.update_data(work_description=new_value)
    elif field == "hours":
        try:
            hours = float(new_value.replace(',', '.'))
            if hours <= 0:
                await message.answer("❌ Продолжительность должна быть больше 0!")
                return
            await state.update_data(estimated_hours=hours)
        except ValueError:
            await message.answer("❌ Введите число!")
            return
    elif field == "date":
        from bot.utils.time_utils import parse_datetime_moscow
        start_datetime = parse_datetime_moscow(new_value)
        if not start_datetime:
            await message.answer("❌ Неверный формат! Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
            return
        if start_datetime < datetime.now():
            await message.answer("❌ Дата не может быть в прошлом!")
            return
        await state.update_data(start_datetime_str=start_datetime.isoformat())
        await state.update_data(start_datetime_text=new_value)
    
    await message.answer(f"✅ Поле обновлено!")
    
    # Показываем обновлённый предпросмотр
    data = await state.get_data()
    start_datetime = datetime.fromisoformat(data['start_datetime_str'])
    price = data.get('current_price', 0)
    
    post_text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {start_datetime.strftime('%d.%m.%Y %H:%M')}

📍 *Адрес:* {data['address']}

👥 *Требуется человек:* {data['workers_count']}

⏱️ *Продолжительность:* {data['estimated_hours']} ч.

📝 *Суть работы:*
{data['work_description']}

💰 *Оплата:* {price} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"confirm_post_{data['order_id']}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_data")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="edit_post_price")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_post")]
    ])
    
    await message.answer(
        f"📝 *Обновленный предпросмотр:*\n\n{post_text}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.confirming_post)
    await state.update_data(edit_field=None)

@router.callback_query(lambda c: c.data == "edit_post_price")
async def edit_post_price(callback: CallbackQuery, state: FSMContext):
    """Редактирование цены"""
    await callback.message.answer(
        "💰 *Введите новую оплату* (руб./чел.)\nПример: 3000",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.entering_price)
    await callback.answer()