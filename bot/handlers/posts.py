from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from bot.database.models import Order, City, Worker, Assignment, worker_city, User
from bot.utils.states import PostStates
from bot.config import settings
from bot.keyboards.reply import get_main_menu

router = Router()

def format_post_text(order, city, price_per_person):
    """Форматирование текста поста для канала и рассылки"""
    # Получаем дату из заявки
    if hasattr(order, 'start_datetime_text') and order.start_datetime_text:
        date_text = order.start_datetime_text
        # Пытаемся извлечь дату и время отдельно
        parts = date_text.split()
        if len(parts) >= 2:
            date_str = parts[0]
            time_str = parts[1]
        else:
            date_str = date_text
            time_str = "уточняется"
    else:
        date_str = order.start_datetime.strftime('%d.%m.%Y')
        time_str = order.start_datetime.strftime('%H:%M')
    
    text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {date_str}
🕐 *Время:* {time_str}

📍 *Адрес:* {order.address}

👥 *Требуется человек:* {order.workers_count}

📝 *Суть работы:*
{order.work_description}

💰 *Оплата:* {price_per_person} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться на заявку!
"""
    return text

@router.callback_query(lambda c: c.data.startswith("post_create_"))
async def create_post_start(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await callback.answer()
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
    await callback.answer()
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
    
    await state.update_data(city_id=city_id)
    await state.update_data(city_name=city.name)
    await state.update_data(channel_id=city.channel_id)
    
    try:
        await callback.message.delete()
    except:
        pass
    # Запрашиваем стоимость
    await callback.message.answer(
        f"💰 *Укажите стоимость оплаты для исполнителя*\n\n"
        f"Город: {city.name}\n\n"
        f"Введите сумму в рублях за одного человека:\n"
        f"Пример: 2000",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.entering_price)
    await callback.answer()

@router.message(PostStates.entering_price)
async def enter_price(message: Message, state: FSMContext, db: AsyncSession):
    """Ввод стоимости"""
    if message.text == "❌ Отмена":
        await cancel_post(message, state)
        return
    
    try:
        price = int(message.text)
        if price <= 0:
            await message.answer("❌ Стоимость должна быть больше 0!")
            return
        await state.update_data(price_per_person=price)
    except ValueError:
        await message.answer("❌ Введите число! Пример: 2000")
        return
    
    # Получаем заявку и город
    data = await state.get_data()
    order_id = data['order_id']
    city_id = data['city_id']
    price = data['price_per_person']
    
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    # Формируем текст поста
    post_text = format_post_text(order, city, price)
    
    # Сохраняем текст в состояние
    await state.update_data(post_text=post_text)
    
    # Показываем предпросмотр
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_post")],
        [InlineKeyboardButton(text="💰 Изменить стоимость", callback_data="edit_price")],
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_post")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
    ])
    
    await message.answer(
        f"📝 *Предпросмотр поста для канала {city.name}:*\n\n"
        f"{post_text}\n"
        f"---\n"
        f"Проверьте текст и выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(PostStates.confirming_post)

@router.callback_query(PostStates.confirming_post, lambda c: c.data == "edit_price")
async def edit_price(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    """Редактирование стоимости"""
    await state.set_state(PostStates.entering_price)

    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        "💰 *Введите новую стоимость:*\n"
        "Пример: 2500",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(PostStates.confirming_post, lambda c: c.data == "edit_post")
async def edit_post_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
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
            [InlineKeyboardButton(text="💰 Изменить стоимость", callback_data="edit_price")],
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
        [InlineKeyboardButton(text="💰 Изменить стоимость", callback_data="edit_price")],
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
    await callback.answer()
    """Публикация поста в канал и рассылка исполнителям"""
    data = await state.get_data()
    order_id = data['order_id']
    city_id = data['city_id']
    channel_id = data['channel_id']
    post_text = data['post_text']
    price_per_person = data['price_per_person']
    
    # Получаем заявку и город
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one()
    
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one()
    
    # Сохраняем стоимость в заявку
    order.price_per_person = price_per_person
    await db.commit()
    
    # Клавиатура для поста
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{order_id}")]
    ])
    
    # Формируем красивый текст для поста
    # Получаем дату
    if hasattr(order, 'start_datetime_text') and order.start_datetime_text:
        date_text = order.start_datetime_text
    else:
        date_text = order.start_datetime.strftime('%d.%m.%Y %H:%M')
    
    # Парсим дату и время
    post_text = f"""
🏗️ *ЗАЯВКА НА РАБОТУ*

📅 *Дата:* {order.start_datetime.strftime('%d.%m.%Y') if not hasattr(order, 'start_datetime_text') else order.start_datetime_text.split()[0]}
🕐 *Время:* {order.start_datetime.strftime('%H:%M') if not hasattr(order, 'start_datetime_text') else 'уточняется'}

📍 *Адрес:* {order.address}

👥 *Требуется человек:* {order.workers_count}

📝 *Суть работы:*
{order.work_description}

💰 *Оплата:* {price_per_person} ₽

---
Нажмите кнопку "✅ Я поеду", чтобы откликнуться на заявку!
"""
    
    try:
        # 1. Отправляем пост в канал
        sent_message = await bot.send_message(
            chat_id=channel_id,
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # 2. Отправляем пост исполнителям, выбравшим этот город
        # Получаем всех исполнителей, у которых выбран этот город
        result = await db.execute(
            select(User, Worker)
            .join(Worker, User.id == Worker.user_id)
            .join(worker_city, Worker.id == worker_city.c.worker_id)
            .where(worker_city.c.city_id == city_id)
            .where(User.is_registered == True)
        )
        workers = result.all()
        
        sent_to_workers = 0
        for user, worker in workers:
            try:
                # Создаём клавиатуру для отклика в боте
                worker_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Я поеду", callback_data=f"apply_order_{order_id}")]
                ])
                
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"🔔 *Новая заявка в вашем городе!*\n\n{post_text}",
                    reply_markup=worker_keyboard,
                    parse_mode="Markdown"
                )
                sent_to_workers += 1
            except Exception as e:
                print(f"Не удалось отправить сообщение исполнителю {user.telegram_id}: {e}")
        
        # Обновляем заявку
        order.channel_post_id = sent_message.message_id
        order.posted_at = datetime.now()
        await db.commit()

        try:
            await callback.message.delete()
        except:
            pass

        await callback.message.answer(
            f"✅ *Пост успешно опубликован!*\n\n"
            f"🏙️ Город: {city.name}\n"
            f"📢 Канал: {channel_id}\n"
            f"💰 Стоимость: {price_per_person} руб./чел.\n"
            f"🆔 ID сообщения: {sent_message.message_id}\n"
            f"👥 Отправлено исполнителям: {sent_to_workers} чел.\n"
            f"📅 Время публикации: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при публикации: {str(e)}")
    
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_edit")
async def cancel_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    """Отмена редактирования"""
    await state.set_state(PostStates.confirming_post)
    data = await state.get_data()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="edit_post")],
        [InlineKeyboardButton(text="💰 Изменить стоимость", callback_data="edit_price")],
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
async def cancel_post_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    """Отмена создания поста (callback)"""
    await state.clear()
    await callback.message.answer("❌ Создание поста отменено")
    await callback.answer()

async def cancel_post(message: Message, state: FSMContext):
    """Отмена создания поста (из сообщения)"""
    await state.clear()
    await message.answer("❌ Создание поста отменено", reply_markup=get_main_menu('admin'))
