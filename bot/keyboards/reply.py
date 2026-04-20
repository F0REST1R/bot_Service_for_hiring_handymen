from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(role: str):
    """Главное меню в зависимости от роли"""
    if role == 'customer':
        buttons = [
            [KeyboardButton(text="📝 Создать заявку")],
            [KeyboardButton(text="ℹ️ Мои заявки")],
            [KeyboardButton(text="◀️ Назад")]
        ]
    elif role == 'worker':
        buttons = [
            [KeyboardButton(text="🏙️ Выбрать города")],
            [KeyboardButton(text="📋 Правила работы")],
            [KeyboardButton(text="📊 Мои отклики")],
            [KeyboardButton(text="◀️ Назад")]
        ]
    else:  # admin
        buttons = [
            [KeyboardButton(text="📋 Активные заявки")],
            [KeyboardButton(text="🏙️ Управление городами")],
            [KeyboardButton(text="📢 Уведомления")],
            [KeyboardButton(text="📊 Аналитика")],
            [KeyboardButton(text="◀️ Назад")]
        ]
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )