from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from bot.database.models import Order, City, Worker, worker_city
from bot.utils.states import PostStates
from bot.config import settings

router = Router()

def format_post_text(order, city):
    """Форматирование текста поста для канала"""
    text = f"""
🏗️ *НОВАЯ ЗАЯВКА НА РАБОТУ!*

📋 *Описание работ:*
{order.work_description}

👥 *Требуется человек:* {order.workers_count}

📅 *Дата и время:* {order.start_datetime_text if hasattr(order, 'start_datetime_text') else order.start_datetime.strftime('%d.%m.%Y %H:%M')}

📍 *Адрес:* {order.address}

⏱️ *Ориентировочное время:* {order.estimated_hours} ч.

🏙️ *Город:* {city.name}

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться на заявку!
"""
    return text

@router.callback_query(lambda c: c.data.startswith("create_post_"))
async def create_post_start(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    """Начало создания поста для заявки"""
    order_id = int(callback.data.split("_")[2])
    
    # Получаем заявку
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        await callback.message.answer("❌ Заявка не найдена")
        await callback.answer()
        return
    
    # Проверяем, не выложен ли уже пост
    if order.channel_post_id:
        await callback.message.answer(
            f"⚠️ Пост для этой заявки уже был выложен!\n"
            f"ID сообщения в канале: {order.channel_post_id}"
        )
        await callback.answer()
        return
    
    await state.update_data(order_id=order_id)
    
    # Получаем список городов
    result = await db.execute(select(City).where(City.is_active == True))
    cities = result.scalars().all()
    
    if not cities:
        await callback.message.answer("❌ Нет доступных городов для публикации")
        await callback.answer()
        return
    
    keyboard = []
    for city in cities:
        keyboard.append([InlineKeyboardButton(text=city.name, callback_data=f"post_city_{city.id}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")])
    
    await callback.message.answer(
        "🏙️ *Выберите город для публикации поста:*\n\n"
        "Пост будет отправлен в Telegram-канал, привязанный к этому городу",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.choosing_city)
    await callback.answer()

@router.callback_query(PostStates.choosing_city, lambda c: c.data.startswith("post_city_"))
async def choose_city_for_post(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    """Выбор города для публикации"""
    city_id = int(callback.data.split("_")[2])
    
    # Получаем город
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    if not city.channel_id:
        await callback.message.answer(
            f"❌ К городу {city.name} не привязан Telegram-канал!\n"
            f"Сначала привяжите канал в управлении городами"
        )
        await callback.answer()
        return
    
    # Получаем заявку
    data = await state.get_data()
    order_id = data['order_id']
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    
    await state.update_data(city_id=city_id)
    await state.update_data(city_name=city.name)
    await state.update_data(channel_id=city.channel_id)
    
    # Формируем текст поста
    post_text = format_post_text(order, city)
    
    # Сохраняем текст в состояние
    await state.update_data(post_text=post_text)
    
    # Показываем предпросмотр
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_post")],
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_post")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
    ])
    
    await callback.message.answer(
        f"📝 *Предпросмотр поста для канала {city.name}:*\n\n"
        f"{post_text}\n\n"
        f"---\n"
        f"Проверьте текст и выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.confirming_post)
    await callback.answer()

@router.callback_query(PostStates.confirming_post, lambda c: c.data == "edit_post")
async def edit_post_text(callback: CallbackQuery, state: FSMContext):
    """Редактирование текста поста"""
    await state.set_state(PostStates.editing_post)
    
    await callback.message.answer(
        "✏️ *Редактирование поста*\n\n"
        "Отправьте новый текст поста:\n"
        "Или нажмите 'Отмена'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(PostStates.editing_post)
async def save_edited_post(message: Message, state: FSMContext):
    """Сохранение отредактированного текста"""
    if message.text == "❌ Отмена":
        await state.set_state(PostStates.confirming_post)
        data = await state.get_data()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_post")],
            [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_post")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
        ])
        
        await message.answer(
            f"📝 *Вернулись к предпросмотру:*\n\n{data['post_text']}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(post_text=message.text)
    await state.set_state(PostStates.confirming_post)
    
    data = await state.get_data()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_post")],
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_post")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
    ])
    
    await message.answer(
        f"📝 *Обновленный предпросмотр:*\n\n{data['post_text']}\n\n---\nПроверьте текст и выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(PostStates.confirming_post, lambda c: c.data == "publish_post")
async def publish_post(callback: CallbackQuery, state: FSMContext, db: AsyncSession, bot):
    """Публикация поста в канал"""
    data = await state.get_data()
    order_id = data['order_id']
    city_id = data['city_id']
    channel_id = data['channel_id']
    post_text = data['post_text']
    
    # Получаем заявку и город
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    # Клавиатура для поста
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{order_id}")]
    ])
    
    try:
        # Отправляем пост в канал
        sent_message = await bot.send_message(
            chat_id=channel_id,
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Обновляем заявку
        order.channel_post_id = sent_message.message_id
        order.posted_at = datetime.now()
        await db.commit()
        
        await callback.message.answer(
            f"✅ *Пост успешно опубликован!*\n\n"
            f"🏙️ Город: {city.name}\n"
            f"📢 Канал: {channel_id}\n"
            f"🆔 ID сообщения: {sent_message.message_id}\n"
            f"📅 Время публикации: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при публикации: {str(e)}")
    
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_edit")
async def cancel_edit(callback: CallbackQuery, state: FSMContext):
    """Отмена редактирования"""
    await state.set_state(PostStates.confirming_post)
    data = await state.get_data()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_post")],
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_post")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
    ])
    
    await callback.message.answer(
        f"📝 *Вернулись к предпросмотру:*\n\n{data['post_text']}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_post")
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    """Отмена создания поста"""
    await state.clear()
    await callback.message.answer("❌ Создание поста отменено")
    await callback.answer()