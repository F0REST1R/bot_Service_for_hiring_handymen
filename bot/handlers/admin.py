from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
from bot.database.models import User, City, Order, Assignment, Worker, worker_city
from bot.utils.states import AdminStates
from bot.config import settings
from bot.keyboards.reply import get_main_menu

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
    
    result = await db.execute(select(City).order_by(City.name))
    cities = result.scalars().all()
    
    if not cities:
        await message.answer("📭 Список городов пуст\n\n➕ Чтобы добавить город, нажмите кнопку ниже")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить город", callback_data="add_city")]
        ])
        await message.answer("Выберите действие:", reply_markup=keyboard)
        return
    
    text = "🏙️ *Список городов*\n\n"
    keyboard = []
    
    for city in cities:
        status = "✅" if city.is_active else "❌"
        channel_info = f"@{city.channel_id}" if city.channel_id else "Не привязан"
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
    city_id = int(callback.data.split("_")[1])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    channel_text = f"📢 Канал: @{city.channel_id}" if city.channel_id else "📢 Канал: не привязан"
    
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

@router.callback_query(lambda c: c.data == "add_city")
async def add_city_start(callback: CallbackQuery, state: FSMContext):
    # Удаляем предыдущее сообщение с кнопками
    await callback.message.delete()
    
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
    # Удаляем предыдущее сообщение пользователя
    await message.delete()
    
    await state.update_data(city_name=message.text)
    await state.set_state(AdminStates.waiting_for_channel_id)
    
    sent_msg = await message.answer(
        f"📢 Введите ID Telegram-канала для города *{message.text}*\n\n"
        "Как получить ID канала:\n"
        "1. Добавьте бота в канал как администратора\n"
        "2. Отправьте любое сообщение в канал\n"
        "3. Перешлите это сообщение боту\n"
        "4. Бот покажет ID\n\n"
        "Пример: @moscow_channel\n\n"
        "Или нажмите 'Пропустить' чтобы добавить без канала",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip_channel")]
        ])
    )
    await state.update_data(last_bot_message=sent_msg.message_id)

@router.message(AdminStates.waiting_for_channel_id)
async def add_city_channel(message: Message, state: FSMContext, db: AsyncSession):
    # Удаляем предыдущее сообщение пользователя
    await message.delete()
    
    data = await state.get_data()
    city_name = data['city_name']
    
    # Удаляем предыдущее сообщение бота
    try:
        await message.bot.delete_message(message.chat.id, data.get('last_bot_message'))
    except:
        pass
    
    # Проверяем, не существует ли уже город
    result = await db.execute(select(City).where(City.name == city_name))
    existing = result.scalar_one_or_none()
    
    if existing:
        await message.answer(f"❌ Город {city_name} уже существует!")
        await state.clear()
        return
    
    channel_id = message.text if message.text else None
    new_city = City(
        name=city_name,
        channel_id=channel_id,
        is_active=True
    )
    db.add(new_city)
    await db.commit()
    
    await message.answer(f"✅ Город *{city_name}* успешно добавлен!", parse_mode="Markdown")
    await state.clear()

@router.callback_query(lambda c: c.data == "skip_channel")
async def skip_channel(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    # Удаляем сообщение с кнопками
    await callback.message.delete()
    
    data = await state.get_data()
    city_name = data['city_name']
    
    new_city = City(name=city_name, channel_id=None, is_active=True)
    db.add(new_city)
    await db.commit()
    
    await callback.message.answer(f"✅ Город *{city_name}* успешно добавлен без привязки канала!", parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_add_city")
async def cancel_add_city(callback: CallbackQuery, state: FSMContext):
    # Удаляем сообщение с кнопками
    await callback.message.delete()
    
    await state.clear()
    await callback.message.answer("❌ Добавление города отменено")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("edit_channel_"))
async def edit_city_channel_start(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split("_")[2])
    await state.update_data(edit_city_id=city_id)
    await state.set_state(AdminStates.waiting_for_channel_id_edit)
    
    # Удаляем предыдущее сообщение
    await callback.message.delete()
    
    await callback.message.answer(
        "📢 Введите новый ID Telegram-канала для города:\n\n"
        "Пример: @moscow_channel\n\n"
        "Или отправьте '0' чтобы удалить привязку канала",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
        ])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_channel_id_edit)
async def edit_city_channel(message: Message, state: FSMContext, db: AsyncSession):
    # Удаляем сообщение пользователя
    await message.delete()
    
    data = await state.get_data()
    city_id = data['edit_city_id']
    channel_id = message.text if message.text != '0' else None
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    city.channel_id = channel_id
    await db.commit()
    
    if channel_id:
        await message.answer(f"✅ Канал для города *{city.name}* обновлён: @{channel_id}", parse_mode="Markdown")
    else:
        await message.answer(f"✅ Привязка канала для города *{city.name}* удалена", parse_mode="Markdown")
    
    await state.clear()

@router.callback_query(lambda c: c.data == "cancel_edit")
async def cancel_edit(callback: CallbackQuery, state: FSMContext):
    # Удаляем сообщение с кнопками
    await callback.message.delete()
    
    await state.clear()
    await callback.message.answer("❌ Редактирование отменено")
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("toggle_"))
async def toggle_city(callback: CallbackQuery, db: AsyncSession):
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
    notification_type = callback.data.split("_")[1]
    
    if notification_type == "by":
        # Удаляем предыдущее сообщение с кнопками
        await callback.message.delete()
        
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
    
    # Удаляем предыдущее сообщение
    await callback.message.delete()
    
    await state.update_data(notification_role=notification_type)
    await state.set_state(AdminStates.waiting_for_notification_text)
    
    sent_msg = await callback.message.answer(
        "✏️ Введите текст сообщения для рассылки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")]
        ])
    )
    await state.update_data(last_bot_message=sent_msg.message_id)

@router.callback_query(lambda c: c.data.startswith("notify_city_"))
async def notify_by_city(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    city_id = int(callback.data.split("_")[2])
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    # Удаляем сообщение с выбором города
    await callback.message.delete()
    
    await state.update_data(notification_role="by_city")
    await state.update_data(notification_city_id=city_id)
    await state.update_data(notification_city_name=city.name)
    await state.set_state(AdminStates.waiting_for_notification_text)
    
    sent_msg = await callback.message.answer(
        f"✏️ Введите текст сообщения для рассылки пользователям из города *{city.name}*:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")]
        ]),
        parse_mode="Markdown"
    )
    await state.update_data(last_bot_message=sent_msg.message_id)
    await callback.answer()

@router.message(AdminStates.waiting_for_notification_text)
async def send_notification(message: Message, state: FSMContext, db: AsyncSession, bot):
    # Удаляем сообщение пользователя
    await message.delete()
    
    data = await state.get_data()
    role = data.get('notification_role')
    city_id = data.get('notification_city_id')
    city_name = data.get('notification_city_name')
    text = message.text
    
    # Удаляем предыдущее сообщение бота
    try:
        await message.bot.delete_message(message.chat.id, data.get('last_bot_message'))
    except:
        pass
    
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
    
    if role == 'by_city' and city_name:
        title = f"📢 *Уведомление для города {city_name}*"
    elif role == 'customers':
        title = "📢 *Уведомление для заказчиков*"
    elif role == 'workers':
        title = "📢 *Уведомление для исполнителей*"
    else:
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
async def cancel_notification(callback: CallbackQuery, state: FSMContext):
    # Удаляем сообщение с кнопками
    await callback.message.delete()
    
    await state.clear()
    await callback.message.answer("❌ Рассылка отменена")
    await callback.answer()

@router.message(F.text == "📊 Аналитика")
async def show_analytics(message: Message, db: AsyncSession):
    if not await is_admin(message.from_user.id, db):
        await message.answer("⛔ У вас нет доступа к этой функции")
        return
    
    # Ссылка на Google таблицу (потом замените на реальную)
    google_sheets_url = "https://docs.google.com/spreadsheets/d/ВАША_ССЫЛКА/edit"
    
    await message.answer(
        "📊 *Аналитика*\n\n"
        "Все данные собираются в Google таблице.\n\n"
        "🔗 *Ссылка на таблицу:*\n"
        f"{google_sheets_url}\n\n"
        "В таблице доступна следующая статистика:\n"
        "• Общая выручка (сумма переводов от заказчиков)\n"
        "• Расходы на персонал (зарплаты рабочим)\n"
        "• Чистая прибыль (разница между доходами и расходами)",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )