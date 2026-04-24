from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from bot.database.models import User, Customer, City, Order, Assignment, Worker
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.utils.states import OrderStates
from bot.utils.time_utils import parse_datetime_moscow
from bot.config import settings
import re

router = Router()

@router.message(F.text == "📝 Создать заявку")
async def create_order_start(message: Message, state: FSMContext, db: AsyncSession):
    # Получаем данные заказчика
    result = await db.execute(
        select(Customer).join(User).where(User.telegram_id == message.from_user.id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        await message.answer("❌ Сначала зарегистрируйтесь с помощью /start")
        return
    
    # Сохраняем данные из регистрации
    await state.update_data(customer_id=customer.id)
    await state.update_data(customer_phone=customer.phone)
    await state.update_data(customer_name=customer.full_name)
    
    # Спрашиваем, использовать ли данные из регистрации
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Да, использовать данные из регистрации")],
            [KeyboardButton(text="✏️ Нет, ввести новые данные")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"📝 *Создание новой заявки*\n\n"
        f"Ваши данные из регистрации:\n"
        f"📛 ФИО/Организация: {customer.full_name}\n"
        f"📞 Телефон: {customer.phone}\n\n"
        f"Использовать эти данные для заявки?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.use_registration_data)

@router.message(OrderStates.use_registration_data, F.text.in_(["✅ Да, использовать данные из регистрации", "✏️ Нет, ввести новые данные"]))
async def order_use_registration_data(message: Message, state: FSMContext):
    if message.text == "✅ Да, использовать данные из регистрации":
        data = await state.get_data()
        await state.update_data(full_name=data['customer_name'])
        await state.update_data(contact_phone=data['customer_phone'])
        
        # Переходим к следующему шагу - количество человек
        await message.answer(
            "👥 Введите количество необходимых человек:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(OrderStates.workers_count)
    
    else:  # Нет, ввести новые данные
        await message.answer(
            "📝 Введите ФИО или название организации:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(OrderStates.full_name)

@router.message(OrderStates.full_name)
async def order_full_name(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    await state.update_data(full_name=message.text)
    
    await message.answer(
        "📞 Введите контактный номер телефона:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.phone)

@router.message(OrderStates.phone)
async def order_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    await state.update_data(contact_phone=message.text)
    
    await message.answer(
        "👥 Введите количество необходимых человек:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.workers_count)

@router.message(OrderStates.workers_count)
async def order_workers_count(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите число")
        return
    
    await state.update_data(workers_count=int(message.text))
    
    await message.answer(
        "📝 Опишите суть работы:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.work_description)

@router.message(OrderStates.work_description)
async def order_work_description(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    await state.update_data(work_description=message.text)
    
    await message.answer(
        "📅 Введите дату и время начала работ:\n\n"
        "Пример: 25 апреля 2026, 10:00\n"
        "Любой удобный для вас формат",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.start_datetime)

@router.message(OrderStates.start_datetime)
async def order_start_datetime(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    # Парсим дату в формате ДД.ММ.ГГГГ ЧЧ:ММ
    start_datetime = parse_datetime_moscow(message.text)
    
    if not start_datetime:
        await message.answer(
            "❌ Неверный формат даты!\n\n"
            "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Пример: 25.05.2026 10:15\n\n"
            "Пожалуйста, введите заново:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Проверяем, что дата не в прошлом
    if start_datetime < datetime.now():
        await message.answer(
            "❌ Дата и время не могут быть в прошлом!\n"
            "Пожалуйста, укажите будущую дату:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Сохраняем как строку и как объект
    await state.update_data(
        start_datetime=start_datetime,
        start_datetime_text=message.text
    )
    
    await message.answer(
        "⏱️ *Введите ориентировочное время занятости* (в часах)\n\n"
        "Сколько примерно времени займёт работа?\n"
        "Пример: 4, 6.5, 8",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.estimated_hours)

@router.message(OrderStates.estimated_hours)
async def order_estimated_hours(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    try:
        # Заменяем запятую на точку
        hours = float(message.text.replace(',', '.'))
        if hours <= 0:
            await message.answer("❌ Время занятости должно быть больше 0")
            return
        await state.update_data(estimated_hours=hours)
    except ValueError:
        await message.answer("❌ Введите число (например: 4, 6.5, 8)")
        return
    
    # Получаем список активных городов
    result = await db.execute(select(City).where(City.is_active == True))
    cities = result.scalars().all()
    
    if not cities:
        await message.answer(
            "❌ Нет доступных городов.\n\n"
            "Пожалуйста, сообщите администратору о проблеме.\n"
            "Администратор может добавить города в панели управления."
        )
        return
    
    # Создаём клавиатуру с городами
    keyboard = [[KeyboardButton(text=city.name)] for city in cities]
    keyboard.append([KeyboardButton(text="❌ Отмена")])
    
    await message.answer(
        "🏙️ Выберите город:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )
    await state.set_state(OrderStates.city)

@router.message(OrderStates.city)
async def order_city(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    # Проверяем, существует ли город
    result = await db.execute(select(City).where(City.name == message.text))
    city = result.scalar_one_or_none()
    
    if not city:
        await message.answer("❌ Выберите город из списка!")
        return
    
    await state.update_data(city_id=city.id)
    await state.update_data(city_name=city.name)
    
    await message.answer(
        "📍 Введите адрес проведения работ:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.address)

@router.message(OrderStates.address)
async def order_address(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    await state.update_data(address=message.text)
    
    # Автоматически получаем username
    username = message.from_user.username
    if username:
        username_for_contact = username
        username_text = f"@{username}"
    else:
        username_for_contact = None
        username_text = "❌ У пользователя нет username"
    
    await state.update_data(username_for_contact=username_for_contact)
    
    data = await state.get_data()

    start_datetime = data.get('start_datetime')
    if not start_datetime and data.get('start_datetime_text'):
        start_datetime = parse_datetime_moscow(data['start_datetime_text'])

    new_order = Order(
        customer_id=data['customer_id'],
        city_id=data['city_id'],
        full_name=data['full_name'],
        contact_phone=data['contact_phone'],
        workers_count=data['workers_count'],
        work_description=data['work_description'],
        start_datetime=start_datetime,
        estimated_hours=data['estimated_hours'],
        address=data['address'],
        username_for_contact=data['username_for_contact'],
        status='active'
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)
    
    # Уведомляем администраторов
    admin_ids = settings.ADMIN_IDS
    order_text = f"""
📢 *НОВАЯ ЗАЯВКА!* 🆔 #{new_order.id}

🏢 *Заказчик:* {data['full_name']}
📞 *Телефон:* {data['contact_phone']}
👥 *Количество человек:* {data['workers_count']}
📝 *Суть работы:* {data['work_description']}
🕐 *Дата и время:* {data['start_datetime_text']}
⏱️ *Время занятости:* {data['estimated_hours']} ч.
🏙️ *Город:* {data['city_name']}
📍 *Адрес:* {data['address']}
👤 *Username:* {username_text}

📅 *Создана:* {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    # Кнопки для администратора
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Создать пост", callback_data=f"post_create_{new_order.id}")],
        [InlineKeyboardButton(text="🔒 Закрыть набор", callback_data=f"close_order_{new_order.id}")]
    ])
    
    for admin_id in admin_ids:
        try:
            await message.bot.send_message(admin_id, order_text, reply_markup=admin_keyboard, parse_mode="Markdown")
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")
    
    await message.answer(
        "✅ *Заявка успешно создана!*\n\n"
        "Администратор свяжется с вами в ближайшее время.",
        parse_mode="Markdown",
        reply_markup=get_main_menu('customer')
    )
    await state.clear()

async def cancel_order(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Создание заявки отменено",
        reply_markup=get_main_menu('customer')
    )

@router.message(F.text == "ℹ️ Мои заявки")
async def show_my_orders(message: Message, db: AsyncSession):
    """Показать заявки текущего заказчика"""
    # Получаем заказчика
    result = await db.execute(
        select(Customer).join(User).where(User.telegram_id == message.from_user.id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        await message.answer("❌ Сначала зарегистрируйтесь с помощью /start")
        return
    
    # Получаем все заявки заказчика
    result = await db.execute(
        select(Order, City)
        .join(City, Order.city_id == City.id)
        .where(Order.customer_id == customer.id)
        .order_by(Order.created_at.desc())
    )
    orders = result.all()
    
    if not orders:
        await message.answer("📭 У вас пока нет созданных заявок")
        return
    
    text = "📋 *Мои заявки*\n\n"
    for order, city in orders:
        # Определяем статус
        if order.status == 'active':
            status_icon = "🟢"
            status_text = "Активна"
        else:
            status_icon = "🔴"
            status_text = "Закрыта"
        
        # Определяем, опубликован ли пост
        post_status = "✅ Опубликован" if order.channel_post_id else "❌ Не опубликован"
        
        text += f"🆔 *Заявка #{order.id}*\n"
        text += f"🏙️ Город: {city.name}\n"
        text += f"📅 Дата: {order.start_datetime.strftime('%d.%m.%Y %H:%M') if not hasattr(order, 'start_datetime_text') else order.start_datetime_text}\n"
        text += f"👥 Человек: {order.workers_count}\n"
        text += f"💰 Оплата: {order.price_per_person if order.price_per_person else 'не указана'} руб./чел.\n"
        text += f"📊 Статус: {status_icon} {status_text}\n"
        text += f"📢 Пост: {post_status}\n"
        
        # Количество откликнувшихся
        assignments_result = await db.execute(
            select(Assignment).where(Assignment.order_id == order.id)
        )
        assignments_count = len(assignments_result.scalars().all())
        text += f"👥 Откликнулось: {assignments_count} чел.\n"
        text += f"---\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text.regexp(r'^Заявка\s+(\d+)$', flags=re.IGNORECASE))
async def show_my_order_details(message: Message, db: AsyncSession):
    """Показать детали заявки по ID для заказчика"""
    import re
    match = re.match(r'^Заявка\s+(\d+)$', message.text, re.IGNORECASE)
    if not match:
        return
    
    order_id = int(match.group(1))
    
    # Получаем пользователя
    result = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    
    if not user:
        await message.answer("❌ Сначала зарегистрируйтесь с помощью /start")
        return
    
    # Если админ - показываем все заявки
    if user.role == 'admin':
        # Получаем заявку без проверки принадлежности
        result = await db.execute(
            select(Order, City)
            .join(City, Order.city_id == City.id)
            .where(Order.id == order_id)
        )
    else:
        # Получаем заказчика
        result = await db.execute(
            select(Customer).where(Customer.user_id == user.id)
        )
        customer = result.scalar_one_or_none()
        
        if not customer:
            await message.answer("❌ Сначала зарегистрируйтесь как заказчик!")
            return
        
        # Получаем заявку и проверяем, что она принадлежит этому заказчику
        result = await db.execute(
            select(Order, City)
            .join(City, Order.city_id == City.id)
            .where(Order.id == order_id, Order.customer_id == customer.id)
        )
    
    order_data = result.first()
    
    if not order_data:
        await message.answer(f"❌ Заявка с ID {order_id} не найдена")
        return
    
    order, city = order_data
    
    # Получаем откликнувшихся
    assignments_result = await db.execute(
        select(Assignment, Worker)
        .join(Worker, Assignment.worker_id == Worker.id)
        .where(Assignment.order_id == order_id)
    )
    assignments = assignments_result.all()
    
    # Статус
    if user.role == 'admin':
        status_icon = "❌" if order.status == 'active' else "✅"
        status_text = "Набор открыт" if order.status == 'active' else "Набор закрыт"
    else:
        status_icon = "🟢" if order.status == 'active' else "🔴"
        status_text = "Активна" if order.status == 'active' else "Закрыта"
    
    post_status = "✅ Опубликован" if order.channel_post_id else "❌ Не опубликован"
    
    text = f"""
📋 *ДЕТАЛИ ЗАЯВКИ* 🆔 #{order.id}

🏢 *Заказчик:* {order.full_name}
📞 *Телефон:* {order.contact_phone}
👥 *Количество человек:* {order.workers_count}
📝 *Суть работы:* {order.work_description}
🕐 *Дата и время:* {order.start_datetime.strftime('%d.%m.%Y %H:%M') if not hasattr(order, 'start_datetime_text') else order.start_datetime_text}
⏱️ *Время занятости:* {order.estimated_hours} ч.
🏙️ *Город:* {city.name}
📍 *Адрес:* {order.address}
👤 *Username:* @{order.username_for_contact if order.username_for_contact else 'не указан'}
💰 *Оплата:* {order.price_per_person if order.price_per_person else 'не указана'} руб./чел.

📊 *Статус:* {status_icon} {status_text}
📢 *Пост:* {post_status}
📅 *Создана:* {order.created_at.strftime('%d.%m.%Y %H:%M')}
"""
    
    if assignments:
        text += f"\n👥 *Откликнувшиеся исполнители:* ({len(assignments)} чел.)\n"
        for i, (assignment, worker) in enumerate(assignments, 1):
            text += f"\n{i}. *{worker.full_name}*\n"
            text += f"   📞 Телефон: {worker.phone}\n"
            text += f"   📌 Отклик: {assignment.assigned_at.strftime('%d.%m.%Y %H:%M')}"
    else:
        text += "\n📭 *Откликнувшиеся исполнители:* пока нет"
    
    await message.answer(text, parse_mode="Markdown")