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
    use_registration_data = State()
    full_name = State()
    phone = State()
    workers_count = State()
    work_description = State()
    start_datetime = State()
    estimated_hours = State()
    city = State()
    address = State()

class WorkerStates(StatesGroup):
    """Состояния исполнителя"""
    selecting_cities = State()
    worker_id = State()

class AdminStates(StatesGroup):
    """Состояния администратора"""
    waiting_for_city_name = State()
    waiting_for_channel_id = State()
    waiting_for_notification_text = State()
    waiting_for_order_close = State()
    waiting_for_channel_id_edit = State()
    waiting_for_post_city = State()
    waiting_for_post_text = State()


class PostStates(StatesGroup):
    """Состояния создания поста"""
    choosing_city = State()
    entering_price = State() 
    entering_price_order = State() 
    entering_price_client = State()
    editing_workers_count = State()
    editing_post = State()
    editing_date = State()
    editing_duration = State()
    editing_address = State()
    editing_description = State()
    confirming_post = State()
    editing_field = State()