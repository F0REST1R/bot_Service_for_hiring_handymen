from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import re
from bot.database.models import User, Customer, City, Order
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.utils.states import OrderStates
from bot.config import settings

router = Router()

def parse_datetime(date_string: str):
    """Парсинг даты и времени из разных форматов"""
    date_string = date_string.strip()
    
    # Поддерживаемые форматы
    formats = [
        "%d.%m.%Y %H:%M",  # 25.04.2026 10:00
        "%d.%m.%y %H:%M",  # 25.04.26 10:00
        "%d-%m-%Y %H:%M",  # 25-04-2026 10:00
        "%d/%m/%Y %H:%M",  # 25/04/2026 10:00
        "%d.%m.%Y %H:%M:%S",  # 25.04.2026 10:00:00
        "%Y-%m-%d %H:%M",  # 2026-04-25 10:00
        "%d.%m.%Y %H",  # 25.04.2026 10
        "%d.%m.%Y",  # 25.04.2026 (будет 00:00)
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # Если ни один формат не подошёл, пробуем извлечь цифры
    match = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\s+(\d{1,2}):?(\d{0,2})', date_string)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5)) if match.group(5) else 0
        
        if year < 100:
            year += 2000
        
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            pass
    
    return None

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
        "📅 Введите дату и время начала работ\n\n"
        "*Поддерживаемые форматы:*\n"
        "• 25.04.2026 10:00\n"
        "• 25-04-2026 10:00\n"
        "• 25/04/2026 10:00\n"
        "• 2026-04-25 10:00\n"
        "• 25.04.2026 10 (будет 10:00)\n"
        "• 25.04.2026 (будет 00:00)\n\n"
        "Пример: 25.04.2026 10:00",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.start_datetime)

@router.message(OrderStates.start_datetime)
async def order_start_datetime(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    start_time = parse_datetime(message.text)
    
    if not start_time:
        await message.answer(
            "❌ Неверный формат даты!\n\n"
            "Используйте один из форматов:\n"
            "• 25.04.2026 10:00\n"
            "• 25-04-2026 10:00\n"
            "• 25/04/2026 10:00\n"
            "• 2026-04-25 10:00\n\n"
            "Пример: 25.04.2026 10:00"
        )
        return
    
    # Проверяем, что дата не в прошлом
    if start_time < datetime.now():
        await message.answer("❌ Дата и время не могут быть в прошлом! Укажите будущую дату.")
        return
    
    # Сохраняем как строку для JSON сериализации, а также сохраняем объект для использования
    await state.update_data(start_datetime_str=start_time.strftime("%Y-%m-%d %H:%M:%S"))
    await state.update_data(start_datetime=start_time)
    
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
    
    await message.answer(
        "👤 Введите username для связи (без @):\n"
        "Пример: username\n\n"
        "Или отправьте 'нет' если не хотите указывать",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(OrderStates.username)

@router.message(OrderStates.username)
async def order_username(message: Message, state: FSMContext, db: AsyncSession, bot):
    if message.text == "❌ Отмена":
        await cancel_order(message, state)
        return
    
    username = None if message.text.lower() == 'нет' else message.text
    await state.update_data(username_for_contact=username)
    
    data = await state.get_data()
    
    # Получаем datetime из строки или из объекта
    start_datetime = data.get('start_datetime')
    if not start_datetime and data.get('start_datetime_str'):
        start_datetime = datetime.strptime(data['start_datetime_str'], "%Y-%m-%d %H:%M:%S")
    
    # Создаём заявку
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
🕐 *Дата и время:* {start_datetime.strftime('%d.%m.%Y %H:%M')}
⏱️ *Время занятости:* {data['estimated_hours']} ч.
🏙️ *Город:* {data['city_name']}
📍 *Адрес:* {data['address']}
👤 *Username:* @{data['username_for_contact'] if data['username_for_contact'] else 'не указан'}

📅 *Создана:* {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, order_text, parse_mode="Markdown")
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
    