from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.models import User, Customer, Worker, City, worker_city
from bot.keyboards.reply import get_main_menu, get_cancel_keyboard
from bot.utils.states import RegistrationStates
from bot.config import settings

router = Router()

async def is_user_registered(telegram_id: int, db: AsyncSession) -> bool:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user is not None and user.is_registered

async def get_user_role(telegram_id: int, db: AsyncSession) -> str:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    return user.role if user else None

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: AsyncSession):
    await state.clear()
    
    if message.from_user.id in settings.ADMIN_IDS:
        result = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
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
    
    registered = await is_user_registered(message.from_user.id, db)
    
    if registered:
        role = await get_user_role(message.from_user.id, db)
        await message.answer(
            f"👋 С возвращением!",
            reply_markup=get_main_menu(role)
        )
    else:
        await message.answer(
            "📝 Добро пожаловать! Давайте зарегистрируемся.\n\nКто вы?",
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
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    await state.update_data(full_name=message.text)
    await message.answer("📅 Введите ваш возраст:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.worker_age)

@router.message(RegistrationStates.worker_age)
async def process_worker_age(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите число (возраст):")
        return
    
    age = int(message.text)

    if age < 16:
        await message.answer(
            "❌ Извините, мы принимаем заявки только от исполнителей старше 16 лет.\n\n"
            "Пожалуйста, введите ваш возраст:"
        )
        return
    
    if age > 100:
        await message.answer(
            "❌ Пожалуйста, введите корректный возраст (не более 100 лет):"
        )
        return
    
    await state.update_data(age=int(message.text))
    await message.answer("🌍 Введите ваше гражданство:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.worker_citizenship)

@router.message(RegistrationStates.worker_citizenship)
async def process_worker_citizenship(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    await state.update_data(citizenship=message.text)
    await message.answer("📞 Введите ваш номер телефона:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.worker_phone)

@router.message(RegistrationStates.worker_phone)
async def process_worker_phone(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    data = await state.update_data(phone=message.text)
    
    new_user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        role='worker',
        is_registered=True
    )
    db.add(new_user)
    await db.flush()
    
    new_worker = Worker(
        user_id=new_user.id,
        full_name=data['full_name'],
        age=data['age'],
        citizenship=data['citizenship'],
        phone=data['phone']
    )
    db.add(new_worker)
    await db.commit()
    
    result = await db.execute(select(City).where(City.is_active == True))
    cities = result.scalars().all()
    
    if not cities:
        default_cities = ["Мытищи", "Королёв", "Пушкино"]
        for city_name in default_cities:
            new_city = City(name=city_name, is_active=True)
            db.add(new_city)
        await db.commit()
        
        result = await db.execute(select(City).where(City.is_active == True))
        cities = result.scalars().all()
    
    city_buttons = [[KeyboardButton(text=city.name)] for city in cities]
    city_buttons.append([KeyboardButton(text="✅ Завершить выбор")])
    
    await message.answer(
        "🏙️ Выберите города, в которых вы готовы работать (можно выбрать несколько):\nПосле выбора нажмите 'Завершить выбор'",
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
        
        worker_id = data['worker_id']
        
        # Добавляем города через таблицу worker_city напрямую
        for city_name in selected_cities:
            result = await db.execute(select(City).where(City.name == city_name))
            city = result.scalar_one()
            
            await db.execute(
                worker_city.insert().values(worker_id=worker_id, city_id=city.id)
            )
        
        await db.commit()
        
        await message.answer(
            "✅ Регистрация завершена!",
            reply_markup=get_main_menu('worker')
        )
        await state.clear()
        return
    
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
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    await state.update_data(full_name=message.text)
    await message.answer("📞 Введите ваш номер телефона:", reply_markup=get_cancel_keyboard())
    await state.set_state(RegistrationStates.customer_phone)

@router.message(RegistrationStates.customer_phone)
async def process_customer_phone(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "❌ Отмена":
        await cancel_registration(message, state)
        return
    
    data = await state.update_data(phone=message.text)
    
    new_user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        role='customer',
        is_registered=True
    )
    db.add(new_user)
    await db.flush()
    
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
    await state.clear()
    await message.answer(
        "❌ Регистрация отменена. Нажмите /start для повторной регистрации.",
        reply_markup=ReplyKeyboardRemove()
    )