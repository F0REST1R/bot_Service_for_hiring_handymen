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
        "📅 Введите дату и время начала работ\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Пример: 25.04.2026 10:00",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.start_datetime)

@router.message(OrderStates.start_datetime)
async def order_start_datetime(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    try:
        start_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        await state.update_data(start_datetime=start_time)
    except:
        await message.answer("❌ Неверный формат! Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    
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
        hours = float(message.text.replace(',', '.'))
        await state.update_data(estimated_hours=hours)
    except:
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
    
    await message.answer(
        "👤 Введите username для связи (без @):\n"
        "Пример: username",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.username)

@router.message(OrderStates.username)
async def order_username(message: Message, state: FSMContext, db: AsyncSession, bot):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    await state.update_data(username_for_contact=message.text)
    
    data = await state.get_data()
    
    # Создаём заявку
    new_order = Order(
        customer_id=data['customer_id'],
        city_id=data['city_id'],
        full_name=data['full_name'],
        contact_phone=data['contact_phone'],
        workers_count=data['workers_count'],
        work_description=data['work_description'],
        start_datetime=data['start_datetime'],
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
📢 *Новая заявка!* 🆔 #{new_order.id}

🏢 {data['full_name']}
📞 {data['contact_phone']}
👥 {data['workers_count']} чел.
📝 {data['work_description']}
🕐 {data['start_datetime'].strftime('%d.%m.%Y %H:%M')}
⏱️ {data['estimated_hours']} ч.
🏙️ {data['city_name']}
📍 {data['address']}
👤 @{data['username_for_contact']}

📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, order_text, parse_mode="Markdown")
        except:
            pass
    
    await message.answer(
        "✅ Заявка успешно создана!\n"
        "Администратор свяжется с вами в ближайшее время.",
        reply_markup=get_main_menu('customer')
    )
    await state.clear()

async def cancel_order(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Создание заявки отменено",
        reply_markup=get_main_menu('customer')
    )