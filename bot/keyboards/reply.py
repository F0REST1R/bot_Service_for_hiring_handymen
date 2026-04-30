from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(role: str):
    """Главное меню в зависимости от роли"""
    if role == 'customer':
        buttons = [
            [KeyboardButton(text="📝 Создать заявку")],
            [KeyboardButton(text="ℹ️ Мои заявки")],
            [KeyboardButton(text="🔄 Сменить роль", callback_data="switch_role")]
        ]
    elif role == 'worker':
        buttons = [
            [KeyboardButton(text="🏙️ Выбрать города")],
            [KeyboardButton(text="📋 Правила работы")],
            [KeyboardButton(text="📊 Мои отклики")],
            [KeyboardButton(text="🔄 Сменить роль", callback_data="switch_role")]
        ]
    else:  # admin
        buttons = [
            [KeyboardButton(text="📋 Активные заявки")],
            [KeyboardButton(text="🏙️ Управление городами")],
            [KeyboardButton(text="📢 Уведомления")],
            [KeyboardButton(text="📝 Создать пост")],
            [KeyboardButton(text="📊 Аналитика")]
        ]
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

