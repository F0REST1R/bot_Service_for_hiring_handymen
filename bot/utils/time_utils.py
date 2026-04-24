from datetime import datetime, timedelta
import pytz

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def parse_datetime_moscow(date_string: str) -> datetime:
    """Парсинг даты и времени как московского времени, сохраняем в UTC"""
    date_string = date_string.strip()
    
    formats = [
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%y %H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
    ]
    
    for fmt in formats:
        try:
            # Парсим как наивную дату
            naive_dt = datetime.strptime(date_string, fmt)
            # Добавляем московский часовой пояс
            moscow_dt = MOSCOW_TZ.localize(naive_dt)
            # Конвертируем в UTC для хранения в БД
            utc_dt = moscow_dt.astimezone(pytz.UTC)
            return utc_dt.replace(tzinfo=None)
        except ValueError:
            continue
    
    return None

def format_datetime_moscow(dt: datetime) -> str:
    """Форматирование UTC времени в московское"""
    if dt.tzinfo is None:
        # Если время без часового пояса, добавляем UTC и конвертируем
        dt = pytz.UTC.localize(dt)
    moscow_dt = dt.astimezone(MOSCOW_TZ)
    return moscow_dt.strftime('%d.%m.%Y %H:%M')