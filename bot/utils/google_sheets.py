import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsClient:
    """Клиент для работы с Google Sheets"""
    
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.sheet = None
        self._connect()
    
    def _connect(self):
        """Подключение к Google Sheets"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file, scope
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(self.spreadsheet_id)
            logger.info("✅ Успешное подключение к Google Sheets")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            raise
    
    def init_sheets(self):
        """Инициализация листов в таблице, если их нет"""
        try:
            # Создаем лист для заявок, если его нет
            try:
                orders_sheet = self.sheet.worksheet("Заявки")
                logger.info("Лист 'Заявки' уже существует")
            except gspread.WorksheetNotFound:
                orders_sheet = self.sheet.add_worksheet(
                    title="Заявки", rows=1000, cols=20
                )
                # Добавляем заголовки
                headers = [
                    "ID заявки", "Дата создания", "Город", "Заказчик",
                    "Телефон", "Количество человек", "Дата начала работ",
                    "Продолжительность (ч)", "Адрес", "Описание работ",
                    "Оплата (руб./чел.)", "Цена для клиента", "Статус поста", "Статус набора",
                    "Количество откликов", "Общий доход", "Расходы на персонал",
                    "Чистая прибыль"
                ]
                orders_sheet.append_row(headers, value_input_option="USER_ENTERED")
                logger.info("✅ Создан лист 'Заявки'")
            
            # Создаем лист для финансов, если его нет
            try:
                finance_sheet = self.sheet.worksheet("Финансы")
                logger.info("Лист 'Финансы' уже существует")
            except gspread.WorksheetNotFound:
                finance_sheet = self.sheet.add_worksheet(
                    title="Финансы", rows=100, cols=10
                )
                headers = [
                    "Дата", "Тип операции", "Сумма", 
                    "ID заявки", "Описание", "Примечание"
                ]
                finance_sheet.append_row(headers, value_input_option="USER_ENTERED")
                logger.info("✅ Создан лист 'Финансы'")
                
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации листов: {e}")
    
    def save_order(self, order_data: dict):
        """
        Сохранение информации о заявке в Google Sheets
        Вызывается при публикации поста
        """
        try:
            orders_sheet = self.sheet.worksheet("Заявки")
            
            # Формируем строку данных
            row = [
                order_data.get('order_id', ''),
                order_data.get('created_at', datetime.now().strftime('%d.%m.%Y %H:%M')),
                order_data.get('city', ''),
                order_data.get('customer_name', ''),
                order_data.get('customer_phone', ''),
                order_data.get('workers_count', 0),
                order_data.get('start_datetime', ''),
                order_data.get('estimated_hours', 0),
                order_data.get('address', ''),
                order_data.get('work_description', ''),
                order_data.get('price_per_person', 0),
                order_data.get('price_for_client', 0),
                order_data.get('post_status', 'Опубликован'),
                order_data.get('recruitment_status', 'Набор открыт'),
                order_data.get('responses_count', 0),
                0,  # Общий доход (заполнится позже)
                0,  # Расходы на персонал (заполнится позже)
                0   # Чистая прибыль (заполнится позже)
            ]
            
            orders_sheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info(f"✅ Заявка #{order_data.get('order_id')} сохранена в Google Sheets")
            
            # Обновляем финансовую статистику
            self.update_financial_stats()
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения заявки в Google Sheets: {e}")
    
    def update_financial_stats(self):
        """Обновление финансовой статистики в отдельном листе"""
        try:
            orders_sheet = self.sheet.worksheet("Заявки")
            finance_sheet = self.sheet.worksheet("Финансы")
            
            # Получаем все заявки кроме заголовка
            all_orders = orders_sheet.get_all_values()
            if len(all_orders) <= 1:
                return
            
            # Очищаем старые финансовые данные (кроме заголовка)
            finance_sheet.resize(rows=1)
            
            total_revenue = 0
            total_expenses = 0
            
            # Перебираем заявки и считаем финансы
            for i, order in enumerate(all_orders[1:], start=2):
                order_id = order[0]
                price_per_person = float(order[10]) if order[10] and order[10] != '' else 0
                workers_count = int(order[5]) if order[5] and order[5] != '' else 0
                
                # Общая выручка от этой заявки (допустим, заказчик платит по ставке)
                revenue = price_per_person * workers_count
                total_revenue += revenue
                
                # Расходы на персонал (зарплата рабочим)
                # Допустим, рабочие получают 80% от оплаты
                expenses = revenue * 0.8
                total_expenses += expenses
                
                # Очистка для демонстрации
                # Реальную сумму перевода нужно будет получать из другого источника
            
            # Чистая прибыль
            net_profit = total_revenue - total_expenses
            
            # Добавляем финансовый отчёт
            report_data = [
                ["Финансовый отчёт", datetime.now().strftime('%d.%m.%Y %H:%M')],
                ["Общая выручка", f"{total_revenue:,.2f} руб."],
                ["Расходы на персонал", f"{total_expenses:,.2f} руб."],
                ["Чистая прибыль", f"{net_profit:,.2f} руб."]
            ]
            
            for row in report_data:
                finance_sheet.append_row(row, value_input_option="USER_ENTERED")
            
            logger.info(f"✅ Финансовая статистика обновлена: Прибыль {net_profit:,.2f} руб.")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления финансовой статистики: {e}")
    
    def update_order_status(self, order_id: int, status_field: str, new_value: str):
        """Обновление статуса заявки в таблице"""
        try:
            orders_sheet = self.sheet.worksheet("Заявки")
            all_orders = orders_sheet.get_all_values()
            
            # Находим заявку по ID
            col_map = {
                'post_status': 11,      # Колонка M (0-based: 11)
                'recruitment_status': 12, # Колонка N (0-based: 12)
                'responses_count': 13     # Колонка O (0-based: 13)
            }
            
            col_index = col_map.get(status_field)
            if col_index is None:
                return
            
            for i, order in enumerate(all_orders[1:], start=2):
                if order[0] == str(order_id):
                    # Обновляем ячейку
                    cell = orders_sheet.cell(i, col_index + 1)  # +1 т.к. колонки с 1
                    cell.value = new_value
                    orders_sheet.update_cell(i, col_index + 1, new_value)
                    logger.info(f"✅ Обновлен статус {status_field} для заявки #{order_id}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса: {e}")
    
    def add_response(self, order_id: int, worker_name: str, worker_phone: str):
        """Добавление отклика в таблицу"""
        try:
            orders_sheet = self.sheet.worksheet("Заявки")
            all_orders = orders_sheet.get_all_values()
            
            for i, order in enumerate(all_orders[1:], start=2):
                if order[0] == str(order_id):
                    # Получаем текущее количество откликов
                    current_count = int(order[14]) if order[13] and order[13] != '' else 0
                    new_count = current_count + 1
                    
                    # Обновляем количество
                    orders_sheet.update_cell(i, 15, new_count)  # Колонка N (14)
                    
                    # Добавляем запись об отклике в лист "Отклики"
                    try:
                        responses_sheet = self.sheet.worksheet("Отклики")
                    except gspread.WorksheetNotFound:
                        responses_sheet = self.sheet.add_worksheet(
                            title="Отклики", rows=1000, cols=10
                        )
                        # Добавляем заголовки если лист новый
                        headers = ["ID заявки", "Исполнитель", "Телефон", "Дата отклика"]
                        responses_sheet.append_row(headers, value_input_option="USER_ENTERED")
                    
                    responses_sheet.append_row([
                        order_id, worker_name, worker_phone,
                        datetime.now().strftime('%d.%m.%Y %H:%M')
                    ], value_input_option="USER_ENTERED")
                    
                    logger.info(f"✅ Добавлен отклик на заявку #{order_id} (всего: {new_count})")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Ошибка добавления отклика: {e}")