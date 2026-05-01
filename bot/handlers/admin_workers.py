from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.database.models import User
from bot.keyboards.reply import get_main_menu
from bot.utils.states import AdminWorkerStates

router = Router()




# ================= МЕНЮ =================
@router.message(F.text == "👷 Взаимодействие с рабочими")
async def workers_admin_menu(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data="block_worker")],
        [InlineKeyboardButton(text="✅ Разблокировать", callback_data="unblock_worker")],
        [InlineKeyboardButton(text="⚠️ Предупреждение", callback_data="warn_worker")],
        [InlineKeyboardButton(text="💬 Комментарий", callback_data="comment_worker")],
        [InlineKeyboardButton(text="❌ Назад", callback_data="cancel_workers_admin")]
    ])

    await message.answer("👷 Управление рабочими:", reply_markup=keyboard)


# ================= НАЗАД =================
@router.callback_query(lambda c: c.data == "cancel_workers_admin")
async def cancel_workers_admin(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("👋 Главное меню", reply_markup=get_main_menu("admin"))
    await callback.answer()


# ================= БЛОК =================
@router.callback_query(lambda c: c.data == "block_worker")
async def block_worker_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminWorkerStates.entering_id)
    await state.update_data(action="block")

    await callback.message.answer("Введите ID пользователя для блокировки:")
    await callback.answer()


# ================= РАЗБЛОК =================
@router.callback_query(lambda c: c.data == "unblock_worker")
async def unblock_worker_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminWorkerStates.entering_id)
    await state.update_data(action="unblock")

    await callback.message.answer("Введите ID пользователя для разблокировки:")
    await callback.answer()


# ================= WARN =================
@router.callback_query(lambda c: c.data == "warn_worker")
async def warn_worker_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminWorkerStates.entering_id)
    await state.update_data(action="warn")

    await callback.message.answer("Введите ID рабочего:")
    await callback.answer()


# ================= COMMENT =================
@router.callback_query(lambda c: c.data == "comment_worker")
async def comment_worker_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminWorkerStates.entering_id)
    await state.update_data(action="comment")

    await callback.message.answer("Введите ID рабочего:")
    await callback.answer()


# ================= ОБРАБОТКА ID =================
@router.message(AdminWorkerStates.entering_id)
async def process_worker_id(message: Message, state: FSMContext, db: AsyncSession, google_client = None):
    try:
        user_id = int(message.text)
    except:
        await message.answer("❌ Введите числовой ID")
        return

    data = await state.get_data()
    action = data.get("action")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("❌ Пользователь не найден")
        return

    if action == "block":
        user.is_blocked = True
        await db.commit()
        if google_client:
            google_client.update_worker_status(user.id, True)
        await message.answer("🚫 Пользователь заблокирован")
        await state.clear()
        return

    if action == "unblock":
        user.is_blocked = False
        await db.commit()
        if google_client:
            google_client.update_worker_status(user.id, False)
        await message.answer("✅ Пользователь разблокирован")
        await state.clear()
        return

    # для warn / comment
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminWorkerStates.entering_message)
    await message.answer("Введите сообщение:")


# ================= ОБРАБОТКА СООБЩЕНИЯ =================
@router.message(AdminWorkerStates.entering_message)
async def process_worker_message(message: Message, state: FSMContext, db: AsyncSession, google_client = None):
    data = await state.get_data()
    user_id = data.get("target_user_id")
    action = data.get("action")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    if action == "warn":
        user.warnings_count += 1
        await db.commit()
        if google_client:
            google_client.increment_worker_warning(user.id)
        await message.bot.send_message(
            user.telegram_id,
            f"⚠️ Вам выдано предупреждение:\n\n{message.text}"
        )

        await message.answer("✅ Предупреждение отправлено")

    elif action == "comment":
        if google_client:
            google_client.add_worker_comment(user_id, message.text)

        await message.answer("💬 Комментарий добавлен")

    await state.clear()