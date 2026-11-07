import random
import string
import time
from datetime import datetime, timedelta
from models import Ticket, SLA_TIMES, get_session, init_db

# Шаблоны заявок
TITLES = [
    "Сервер не отвечает",
    "Нет доступа к почте",
    "Не печатает принтер",
    "Ошибка в CRM",
    "Сайт недоступен",
    "Сбой базы данных",
    "Не работает VPN",
    "Зависла виртуальная машина",
    "Нет сети в отделе",
    "Ошибка сертификата",
]

DESCRIPTIONS = [
    "Пользователь сообщает о невозможности работы.",
    "Сервис недоступен для всего отдела.",
    "Одиночный пользователь столкнулся с проблемой.",
    "Массовое обращение от нескольких пользователей.",
    "Проблема возникла после планового обслуживания.",
]

PRIORITIES = ["critical", "high", "medium", "low"]
TYPES = ["incident", "service_request"]


def generate_ticket():
    """Создаёт одну случайную заявку и сохраняет в базу."""
    session = get_session()

    ticket_id = "TKT-" + "".join(random.choices(string.digits, k=6))
    priority = random.choice(PRIORITIES)
    now = datetime.utcnow()
    sla_time = SLA_TIMES.get(priority, 86400)

    ticket = Ticket(
        id=ticket_id,
        type=random.choice(TYPES),
        title=random.choice(TITLES),
        description=random.choice(DESCRIPTIONS),
        priority=priority,
        status="new",
        created_at=now,
        updated_at=now,
        sla_deadline=now + timedelta(seconds=sla_time),
    )

    session.add(ticket)
    session.commit()
    session.close()
    print(f"  [+] Создана заявка {ticket_id} (priority={priority})")
    return ticket_id


def run_generator(interval=15, max_tickets=None):
    """
    Бесконечно создаёт заявки с интервалом interval секунд.
    Если max_tickets задан — остановится после этого количества.
    """
    init_db()
    count = 0
    while True:
        generate_ticket()
        count += 1
        if max_tickets and count >= max_tickets:
            print(f"Генератор остановлен. Создано {count} заявок.")
            break
        time.sleep(interval)


if __name__ == "__main__":
    # Создать 5 заявок с интервалом 5 секунд
    run_generator(interval=5, max_tickets=5)
