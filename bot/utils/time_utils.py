from datetime import datetime, timedelta
import re

MOSCOW_TZ = 3  # Москва UTC+3

def parse_datetime_moscow(date_string: str) -> datetime:
    """Парсинг даты и времени с учётом московского времени (UTC+3)"""
    date_string = date_string.strip()
    
    # Форматы для парсинга
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
            dt = datetime.strptime(date_string, fmt)
            # Вычитаем 3 часа, так как в БД время хранится в UTC
            return dt - timedelta(hours=MOSCOW_TZ)
        except ValueError:
            continue
    
    return None

def format_datetime_moscow(dt: datetime) -> str:
    """Форматирование даты из UTC в московское время"""
    if dt.tzinfo is None:
        # Если время без часового пояса, прибавляем 3 часа для отображения
        moscow_dt = dt + timedelta(hours=MOSCOW_TZ)
    else:
        moscow_dt = dt + timedelta(hours=MOSCOW_TZ)
    return moscow_dt.strftime("%d.%m.%Y %H:%M")