from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from bot.database.models import User
from bot.keyboards.reply import get_main_menu

router = Router()

@router.message(F.text == "❌ Отмена")
async def universal_cancel(message: Message, state: FSMContext, db: AsyncSession):
    """Универсальная отмена для любых действий"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer("❌ Нечего отменять. Вы не находитесь в процессе создания чего-либо.")
        return
    
    # Получаем роль пользователя
    result = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    role = user.role if user else 'customer'
    
    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=get_main_menu(role))

@router.callback_query(F.data == "cancel", state="*")
async def cancel_handler_callback(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await state.clear()

    await callback.message.answer(
        "❌ Действие отменено",
        reply_markup=await get_main_menu(callback.from_user.id, db)
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_notification")
async def cancel_notification(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ Рассылка отменена")
    
    # Возвращаемся в главное меню админа
    await callback.message.answer(
        "👋 Главное меню:",
        reply_markup=get_main_menu('admin')
    )
    await callback.answer()

async def cancel_create_post(message: Message, state: FSMContext):
    """Отмена создания поста - возврат в меню администратора"""
    await state.clear()
    await message.answer(
        "❌ Создание поста отменено",
        reply_markup=get_main_menu('admin')
    )

@router.callback_query(lambda c: c.data == "cancel_edit", state="*")
async def cancel_edit_handler(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    await state.clear()

    await callback.message.answer(
        "❌ Редактирование отменено",
        reply_markup=await get_main_menu(callback.from_user.id, db)
    )

    await callback.answer()