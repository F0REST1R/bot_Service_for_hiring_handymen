from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.models import Worker, City, worker_city, Order, Assignment, User
from bot.keyboards.reply import get_main_menu
from bot.utils.states import WorkerStates, RegistrationStates
from bot.config import settings
from bot.utils.time_utils import format_datetime_moscow 
router = Router()

@router.message(F.text == "🏙️ Выбрать города")
async def select_cities(message: Message, db: AsyncSession):
    # Получаем текущего исполнителя
    result = await db.execute(
        select(Worker).join(User).where(User.telegram_id == message.from_user.id)
    )
    worker = result.scalar_one_or_none()
    
    if not worker:
        await message.answer("❌ Сначала зарегистрируйтесь с помощью /start")
        return
    
    # Получаем все активные города
    cities_result = await db.execute(select(City).where(City.is_active == True))
    cities = cities_result.scalars().all()
    
    # Получаем выбранные города исполнителя
    selected_result = await db.execute(
        select(City).join(worker_city).where(worker_city.c.worker_id == worker.id)
    )
    selected_cities = selected_result.scalars().all()
    selected_names = [c.name for c in selected_cities]
    
    # Создаём клавиатуру
    keyboard = []
    for city in cities:
        status = "✅ " if city.name in selected_names else "⬜ "
        keyboard.append([KeyboardButton(text=f"{status}{city.name}")])
    
    keyboard.append([KeyboardButton(text="💾 Сохранить изменения")])
    keyboard.append([KeyboardButton(text="◀️ Назад")])
    
    await message.answer(
        "🏙️ *Выберите города для работы*\n\n"
        "✅ - уже выбран\n"
        "⬜ - не выбран\n\n"
        "Нажимайте на города, чтобы выбрать/отменить\n"
        "После выбора нажмите 'Сохранить изменения'",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    
    # Сохраняем в состояние список выбранных городов
    await WorkerStates.selecting_cities.set()
    await WorkerStates.worker_id.set(worker.id)

@router.message(WorkerStates.selecting_cities, F.text.startswith(("✅ ", "⬜ ")))
async def toggle_city_selection(message: Message, state: FSMContext, db: AsyncSession):
    # Получаем название города (без префикса)
    city_name = message.text[2:]  # Убираем "✅ " или "⬜ "
    
    data = await state.get_data()
    selected = data.get('temp_selected', [])
    
    if city_name in selected:
        selected.remove(city_name)
    else:
        selected.append(city_name)
    
    await state.update_data(temp_selected=selected)
    await message.answer(f"{'✅' if city_name in selected else '⬜'} {city_name}")

@router.message(WorkerStates.selecting_cities, F.text == "💾 Сохранить изменения")
async def save_cities(message: Message, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    worker_id = data.get('worker_id')
    selected_cities = data.get('temp_selected', [])
    
    # Очищаем старые связи
    await db.execute(worker_city.delete().where(worker_city.c.worker_id == worker_id))
    
    # Добавляем новые
    for city_name in selected_cities:
        result = await db.execute(select(City).where(City.name == city_name))
        city = result.scalar_one()
        await db.execute(
            worker_city.insert().values(worker_id=worker_id, city_id=city.id)
        )
    
    await db.commit()
    
    await message.answer(
        f"✅ Города сохранены! Выбрано: {', '.join(selected_cities) if selected_cities else 'ни одного'}",
        reply_markup=get_main_menu('worker')
    )
    await state.clear()

@router.message(F.text == "📋 Правила работы")
async def show_rules(message: Message):
    rules_text = """
📋 *Правила работы*

1. Вы выбираете города, в которых готовы работать
2. Заявки приходят только из выбранных вами городов
3. Чтобы откликнуться на заявку, нажмите кнопку "Поеду"
4. После отклика с вами свяжется администратор
5. При возникновении вопросов обращайтесь к администратору

*Важно:* 
- Своевременно откликайтесь на заявки
- При изменении графика работы обновите выбор городов
"""
    await message.answer(rules_text, parse_mode="Markdown")

@router.message(F.text == "📊 Мои отклики")
async def show_my_responses(message: Message, db: AsyncSession):
    # Получаем исполнителя
    result = await db.execute(
        select(Worker).join(User).where(User.telegram_id == message.from_user.id)
    )
    worker = result.scalar_one_or_none()
    
    if not worker:
        await message.answer("❌ Сначала зарегистрируйтесь с помощью /start")
        return
    
    # Получаем отклики
    from datetime import datetime
    result = await db.execute(
        select(Assignment, Order, City)
        .join(Order, Assignment.order_id == Order.id)
        .join(City, Order.city_id == City.id)
        .where(Assignment.worker_id == worker.id)
        .order_by(Assignment.assigned_at.desc())
    )
    assignments = result.all()
    
    if not assignments:
        await message.answer("📭 У вас пока нет откликов на заявки")
        return
    
    text = "📊 *Мои отклики*\n\n"
    for assignment, order, city in assignments:
        text += f"🏙️ *{city.name}*\n"
        text += f"📅 Дата: {format_datetime_moscow(order.start_datetime)}\n"
        text += f"📌 Отклик: {assignment.assigned_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "◀️ Назад")
async def back_to_main_menu(message: Message, state: FSMContext, db: AsyncSession):
    """Возврат в главное меню"""
    await state.clear()
    
    # Получаем роль пользователя
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    
    if user:
        await message.answer(
            "👋 Главное меню:",
            reply_markup=get_main_menu(user.role)
        )
    else:
        await message.answer(
            "👋 Нажмите /start для начала работы"
        )
        
@router.message(F.text == "🔄 Сменить роль")
async def switch_role(message: Message, state: FSMContext, db: AsyncSession):
    result = await db.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = result.scalar_one()

    if user.role == "worker":
        user.role = "customer"
        new_role = "Заказчик"
    else:
        user.role = "worker"
        new_role = "Исполнитель"

    await db.commit()

    # проверка профиля исполнителя
    if user.role == "worker":
        result = await db.execute(
            select(Worker).where(Worker.user_id == user.id)
        )
        worker = result.scalar_one_or_none()

        if not worker:
            await message.answer(
                "📝 Для работы исполнителем нужно заполнить данные\n\n"
                "Введите ваше имя:"
            )
            await state.set_state(RegistrationStates.worker_full_name)
            return

    await message.answer(
        f"🔄 Роль изменена на: <b>{new_role}</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu(user.role)
    )