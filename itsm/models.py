from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import os

# SQLite-база хранится в файле
DB_PATH = os.environ.get("DB_PATH", "/app/data/tickets.db")
engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String, primary_key=True)          # Уникальный ID заявки
    type = Column(String)                            # incident или service_request
    title = Column(String)
    description = Column(Text)
    priority = Column(String)                        # critical, high, medium, low
    status = Column(String, default="new")           # new, assigned, in_progress, resolved, closed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    assigned_to = Column(String, nullable=True)
    sla_deadline = Column(DateTime)
    sla_breached = Column(Integer, default=0)         # 0 = не нарушен, 1 = нарушен
    resolution_time_sec = Column(Integer, nullable=True)  # Время решения в секундах


# SLA по приоритетам (в секундах — для симуляции; в реальной жизни — часы)
SLA_TIMES = {
    "critical": 3600,    # 1 час
    "high": 14400,       # 4 часа
    "medium": 28800,     # 8 часов
    "low": 86400,        # 24 часа
}

# Для тестов/демо можно использовать ускоренные значения:
# SLA_TIMES = {"critical": 10, "high": 30, "medium": 60, "low": 120}


def init_db():
    """Создаёт таблицы в базе."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(engine)


def get_session():
    """Возвращает сессию для работы с базой."""
    return SessionLocal()
