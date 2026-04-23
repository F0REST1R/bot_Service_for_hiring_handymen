from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.models import Worker, City, worker_city, Order, Assignment, User
from bot.keyboards.reply import get_main_menu
from bot.utils.states import WorkerStates
from bot.config import settings

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
        text += f"📅 Дата: {order.start_datetime.strftime('%d.%m.%Y %H:%M')}\n"
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

@router.callback_query(lambda c: c.data.startswith("apply_order_"))
async def apply_for_order(callback: CallbackQuery, db: AsyncSession):
    await callback.answer()
    """Обработчик нажатия кнопки 'Я поеду' в боте"""
    order_id = int(callback.data.split("_")[2])
    
    # Проверяем, зарегистрирован ли пользователь
    result = await db.execute(select(User).where(User.telegram_id == callback.from_user.id))
    user = result.scalar_one_or_none()
    
    if not user or user.role != 'worker':
        await callback.answer("❌ Сначала зарегистрируйтесь как исполнитель!", show_alert=True)
        return
    
    # Получаем исполнителя
    result = await db.execute(select(Worker).where(Worker.user_id == user.id))
    worker = result.scalar_one_or_none()
    
    if not worker:
        await callback.answer("❌ Сначала зарегистрируйтесь!", show_alert=True)
        return
    
    # Получаем заявку
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order or order.status != 'active':
        await callback.answer("❌ Эта заявка уже закрыта!", show_alert=True)
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
        await callback.answer("❌ Вы уже откликнулись на эту заявку!", show_alert=True)
        return
    
    # Создаём отклик
    new_assignment = Assignment(
        order_id=order_id,
        worker_id=worker.id
    )
    db.add(new_assignment)
    await db.commit()
    
    # Уведомляем администратора
    admin_ids = settings.ADMIN_IDS
    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                f"✅ *Новый отклик!*\n\n"
                f"👤 Исполнитель: {worker.full_name}\n"
                f"📞 Телефон: {worker.phone}\n"
                f"🆔 Заявка #{order_id}",
                parse_mode="Markdown"
            )
        except:
            pass
    
    await callback.answer("✅ Вы успешно откликнулись на заявку!", show_alert=True)
    
    # Обновляем сообщение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Вы откликнулись", callback_data=f"already_applied_{order_id}")]
    ])
    await callback.message.edit_reply_markup(reply_markup=keyboard)
