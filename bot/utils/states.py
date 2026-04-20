from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    """Состояния регистрации"""
    role_choice = State()
    worker_full_name = State()
    worker_age = State()
    worker_citizenship = State()
    worker_phone = State()
    worker_cities = State()
    customer_full_name = State()
    customer_phone = State()

class OrderStates(StatesGroup):
    """Состояния создания заявки"""
    full_name = State()
    phone = State()
    workers_count = State()
    work_description = State()
    start_datetime = State()
    estimated_hours = State()
    city = State()
    address = State()
    username = State()