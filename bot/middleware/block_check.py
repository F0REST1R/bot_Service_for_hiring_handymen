from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from bot.database.models import User


class BlockCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        db = data.get("db")

        if not db:
            return await handler(event, data)

        telegram_id = None

        if isinstance(event, Message):
            telegram_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id

        if telegram_id:
            result = await db.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user and user.is_blocked:
                if isinstance(event, Message):
                    await event.answer("⛔ Вы заблокированы")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔ Вы заблокированы", show_alert=True)

                return  # 🚫 стопаем ВСЕ

        return await handler(event, data)