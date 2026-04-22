from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from bot.database.models import User, Customer, City, Order
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.utils.states import OrderStates
from bot.config import settings

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
    
    await state.update_data(customer_id=customer.id)
    await state.update_data(customer_phone=customer.phone)
    await state.update_data(customer_name=customer.full_name)
    
    await message.answer(
        "📝 *Создание новой заявки*\n\n"
        "Введите ФИО или название организации:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.full_name)

@router.message(OrderStates.full_name)
async def order_full_name(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    await state.update_data(full_name=message.text)
    
    data = await state.get_data()
    default_phone = data.get('customer_phone', '')
    
    await message.answer(
        f"📞 Введите контактный номер телефона:\n"
        f"(можно отправить '{default_phone}' чтобы использовать номер из регистрации)",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.phone)

@router.message(OrderStates.phone)
async def order_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    data = await state.get_data()
    if message.text == data.get('customer_phone'):
        await state.update_data(contact_phone=message.text)
    else:
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
    
    # Сохраняем дату как текст
    await state.update_data(start_datetime_text=message.text)
    
    await message.answer(
        "⏱️ Введите ориентировочное время занятости (в часах):\n"
        "Пример: 4, 6.5, 8",
        reply_markup=get_cancel_keyboard()
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
    
    # Получаем список городов
    result = await db.execute(select(City).where(City.is_active == True))
    cities = result.scalars().all()
    
    if not cities:
        await message.answer("❌ Нет доступных городов. Обратитесь к администратору.")
        return
    
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
async def order_address(message: Message, state: FSMContext):
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
    
    # Создаём заявку
    new_order = Order(
        customer_id=data['customer_id'],
        city_id=data['city_id'],
        full_name=data['full_name'],
        contact_phone=data['contact_phone'],
        workers_count=data['workers_count'],
        work_description=data['work_description'],
        start_datetime=datetime.now(),  # Временное значение, не используется
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
        [InlineKeyboardButton(text="📢 Создать пост", callback_data=f"create_post_{new_order.id}")],
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