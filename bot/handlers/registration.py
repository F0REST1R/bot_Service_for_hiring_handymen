from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.database import get_db
from bot.database.models import User, Customer, Worker, City
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.utils.states import RegistrationStates
from bot.config import settings

router = Router()

async def is_user_registered(telegram_id: int, db: AsyncSession) -> bool:
    """Проверка, зарегистрирован ли пользователь"""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user is not None and user.is_registered

async def get_user_role(telegram_id: int, db: AsyncSession) -> str:
    """Получение роли пользователя"""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user.role if user else None

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: AsyncSession):
    """Обработчик команды /start - проверка регистрации и перенаправление"""
    await state.clear()
    
    # Проверка на админа
    if message.from_user.id in settings.ADMIN_IDS:
        # Проверяем, есть ли админ в БД
        result = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            # Регистрируем админа
            new_user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                role='admin',
                is_registered=True
            )
            db.add(new_user)
            await db.commit()
        
        await message.answer(
            "👋 Добро пожаловать в админ-панель!",
            reply_markup=get_main_menu('admin')
        )
        return
    
    # Проверка регистрации обычного пользователя
    registered = await is_user_registered(message.from_user.id, db)
    
    if registered:
        role = await get_user_role(message.from_user.id, db)
        await message.answer(
            f"👋 С возвращением!",
            reply_markup=get_main_menu(role)
        )
    else:
        # Начинаем регистрацию
        await message.answer(
            "📝 Добро пожаловать! Давайте зарегистрируемся.\n\n"
            "Кто вы?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="👤 Заказчик")],
                    [KeyboardButton(text="🔧 Исполнитель")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(RegistrationStates.role_choice)

@router.message(RegistrationStates.role_choice, F.text.in_(["👤 Заказчик", "🔧 Исполнитель"]))
async def process_role_choice(message: Message, state: FSMContext, db: AsyncSession):
    """Обработка выбора роли при регистрации"""
    role = "customer" if message.text == "👤 Заказчик" else "worker"
    await state.update_data(role=role)
    
    if role == "worker":
        await message.answer(
            "📝 Введите ваше ФИО:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(RegistrationStates.worker_full_name)
    else:
        await message.answer(
            "📝 Введите ваше ФИО или название организации:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(RegistrationStates.customer_full_name)

@router.message(RegistrationStates.worker_full_name)
async def process_worker_full_name(message: Message, state: FSMContext):
    """Обработка ввода ФИО исполнителя"""
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    await state.update_data(full_name=message.text)
    await message.answer("📅 Введите ваш возраст:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.worker_age)

@router.message(RegistrationStates.worker_age)
async def process_worker_age(message: Message, state: FSMContext):
    """Обработка ввода возраста исполнителя"""
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите число (возраст):")
        return
    
    await state.update_data(age=int(message.text))
    await message.answer("🌍 Введите ваше гражданство:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.worker_citizenship)

@router.message(RegistrationStates.worker_citizenship)
async def process_worker_citizenship(message: Message, state: FSMContext):
    """Обработка ввода гражданства исполнителя"""
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    await state.update_data(citizenship=message.text)
    await message.answer("📞 Введите ваш номер телефона:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.worker_phone)

@router.message(RegistrationStates.worker_phone)
async def process_worker_phone(message: Message, state: FSMContext, db: AsyncSession):
    """Обработка ввода телефона и завершение регистрации исполнителя"""
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    data = await state.update_data(phone=message.text)
    
    # Создаем пользователя
    new_user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        role='worker',
        is_registered=True
    )
    db.add(new_user)
    await db.flush()
    
    # Создаем исполнителя
    new_worker = Worker(
        user_id=new_user.id,
        full_name=data['full_name'],
        age=data['age'],
        citizenship=data['citizenship'],
        phone=data['phone']
    )
    db.add(new_worker)
    await db.commit()
    
    # Получаем список городов для выбора
    result = await db.execute(select(City).where(City.is_active == True))
    cities = result.scalars().all()
    
    if not cities:
        # Если городов нет, добавляем стандартные
        default_cities = ["Мытищи", "Королёв", "Пушкино"]
        for city_name in default_cities:
            new_city = City(name=city_name, is_active=True)
            db.add(new_city)
        await db.commit()
        
        result = await db.execute(select(City).where(City.is_active == True))
        cities = result.scalars().all()
    
    # Создаем клавиатуру для выбора городов
    city_buttons = [[KeyboardButton(text=city.name)] for city in cities]
    city_buttons.append([KeyboardButton(text="✅ Завершить выбор")])
    
    await message.answer(
        "🏙️ Выберите города, в которых вы готовы работать (можно выбрать несколько):\n"
        "После выбора нажмите 'Завершить выбор'",
        reply_markup=ReplyKeyboardMarkup(keyboard=city_buttons, resize_keyboard=True)
    )
    
    await state.update_data(worker_id=new_worker.id)
    await state.set_state(RegistrationStates.worker_cities)

@router.message(RegistrationStates.worker_cities)
async def process_worker_cities(message: Message, state: FSMContext, db: AsyncSession):
    """Обработка выбора городов исполнителем"""
    if message.text == "✅ Завершить выбор":
        data = await state.get_data()
        selected_cities = data.get('selected_cities', [])
        
        if not selected_cities:
            await message.answer("❌ Выберите хотя бы один город!")
            return
        
        # Сохраняем выбранные города
        worker_id = data['worker_id']
        
        # Получаем объект Worker
        from sqlalchemy import select
        result = await db.execute(select(Worker).where(Worker.id == worker_id))
        worker = result.scalar_one()
        
        # Добавляем города через relationship
        for city_name in selected_cities:
            result = await db.execute(select(City).where(City.name == city_name))
            city = result.scalar_one()
            worker.cities.append(city)  # Правильный способ добавления
        
        await db.commit()
        
        await message.answer(
            "✅ Регистрация завершена!",
            reply_markup=get_main_menu('worker')
        )
        await state.clear()
    else:
        # Сохраняем выбранный город
        data = await state.get_data()
        selected_cities = data.get('selected_cities', [])
        
        if message.text not in selected_cities:
            selected_cities.append(message.text)
            await state.update_data(selected_cities=selected_cities)
            await message.answer(f"✅ Добавлен город: {message.text}")
        else:
            await message.answer(f"⚠️ Город {message.text} уже выбран")

@router.message(RegistrationStates.customer_full_name)
async def process_customer_full_name(message: Message, state: FSMContext):
    """Обработка ввода ФИО заказчика"""
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    await state.update_data(full_name=message.text)
    await message.answer("📞 Введите ваш номер телефона:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.customer_phone)

@router.message(RegistrationStates.customer_phone)
async def process_customer_phone(message: Message, state: FSMContext, db: AsyncSession):
    """Обработка ввода телефона и завершение регистрации заказчика"""
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    data = await state.update_data(phone=message.text)
    
    # Создаем пользователя
    new_user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        role='customer',
        is_registered=True
    )
    db.add(new_user)
    await db.flush()
    
    # Создаем заказчика
    new_customer = Customer(
        user_id=new_user.id,
        full_name=data['full_name'],
        phone=data['phone']
    )
    db.add(new_customer)
    await db.commit()
    
    await message.answer(
        "✅ Регистрация завершена!",
        reply_markup=get_main_menu('customer')
    )
    await state.clear()

async def cancel_registration(message: Message, state: FSMContext):
    """Отмена регистрации"""
    await state.clear()
    await message.answer(
        "❌ Регистрация отменена. Нажмите /start для повторной регистрации.",
        reply_markup=ReplyKeyboardRemove()
    )