from aiogram import Router, F
from aiogram.types import Message
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