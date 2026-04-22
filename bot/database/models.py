from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Text, ForeignKey, Table, Float
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

# Связь многие-ко-многим: исполнитель - города
worker_city = Table(
    'worker_city',
    Base.metadata,
    Column('worker_id', Integer, ForeignKey('workers.id')),
    Column('city_id', Integer, ForeignKey('cities.id'))
)

class User(Base):
    """Общая таблица пользователей"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False)  # customer, worker, admin
    is_registered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # Связи
    customer = relationship("Customer", back_populates="user", uselist=False)
    worker = relationship("Worker", back_populates="user", uselist=False)

class Customer(Base):
    """Таблица заказчиков"""
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    full_name = Column(String(200), nullable=False)  # ФИО или организация
    phone = Column(String(20), nullable=False)
    
    # Связи
    user = relationship("User", back_populates="customer")

class Worker(Base):
    """Таблица исполнителей"""
    __tablename__ = 'workers'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    full_name = Column(String(200), nullable=False)
    age = Column(Integer, nullable=False)
    citizenship = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    
    # Связи
    user = relationship("User", back_populates="worker")
    cities = relationship("City", secondary=worker_city, back_populates="workers")

class City(Base):
    """Таблица городов"""
    __tablename__ = 'cities'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    channel_id = Column(String(100), nullable=True)  # ID Telegram канала
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    
    # Связи
    workers = relationship("Worker", secondary=worker_city, back_populates="cities")
    orders = relationship("Order", back_populates="city")

class Order(Base):
    """Таблица заявок"""
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'))
    city_id = Column(Integer, ForeignKey('cities.id'))
    
    # Данные заявки
    full_name = Column(String(200), nullable=False)
    contact_phone = Column(String(20), nullable=False)
    workers_count = Column(Integer, nullable=False)
    work_description = Column(Text, nullable=False)
    start_datetime = Column(DateTime, nullable=False)
    estimated_hours = Column(Float, nullable=False)
    address = Column(Text, nullable=False)
    username_for_contact = Column(String(100), nullable=True)
    
    status = Column(String(20), default='active')  # active, closed
    created_at = Column(DateTime, default=datetime.now)
    is_active_for_today = Column(Boolean, default=True)
    channel_post_id = Column(Integer, nullable=True)  # ID сообщения в канале
    posted_at = Column(DateTime, nullable=True)  # Дата публикации в канале
    
    # Связи
    customer = relationship("Customer")
    city = relationship("City", back_populates="orders")
    assignments = relationship("Assignment", back_populates="order")

class Assignment(Base):
    """Таблица назначений исполнителей на заявки"""
    __tablename__ = 'assignments'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    worker_id = Column(Integer, ForeignKey('workers.id'))
    assigned_at = Column(DateTime, default=datetime.now)
    
    # Связи
    order = relationship("Order", back_populates="assignments")
    worker = relationship("Worker")