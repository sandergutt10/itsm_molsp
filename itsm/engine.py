import time
import random
from datetime import datetime
from models import Ticket, get_session, init_db

# Время нахождения в каждом статусе (в секундах) — для симуляции
# В реальной жизни это зависит от сложности задачи и числа инженеров
STATUS_DELAYS = {
    "new": (2, 5),         # new → assigned: 2-5 секунд
    "assigned": (3, 7),    # assigned → in_progress: 3-7 секунд
    "in_progress": (5, 15)  # in_progress → resolved: 5-15 секунд
}


def advance_ticket(ticket):
    """Продвигает заявку на следующий статус, если прошло достаточно времени."""
    now = datetime.utcnow()
    elapsed = (now - ticket.updated_at).total_seconds()

    if ticket.status == "new":
        min_sec, max_sec = STATUS_DELAYS["new"]
        if elapsed >= random.randint(min_sec, max_sec):
            ticket.status = "assigned"
            ticket.updated_at = now
            return f"  {ticket.id}: new → assigned"

    elif ticket.status == "assigned":
        min_sec, max_sec = STATUS_DELAYS["assigned"]
        if elapsed >= random.randint(min_sec, max_sec):
            ticket.status = "in_progress"
            ticket.updated_at = now
            return f"  {ticket.id}: assigned → in_progress"

    elif ticket.status == "in_progress":
        min_sec, max_sec = STATUS_DELAYS["in_progress"]
        if elapsed >= random.randint(min_sec, max_sec):
            ticket.status = "resolved"
            ticket.resolved_at = now
            ticket.updated_at = now
            ticket.resolution_time_sec = int(
                (ticket.resolved_at - ticket.created_at).total_seconds()
            )
            return f"  {ticket.id}: in_progress → resolved"

    return None


def check_sla():
    """Проверяет SLA для всех открытых заявок."""
    session = get_session()
    now = datetime.utcnow()

    open_tickets = session.query(Ticket).filter(
        Ticket.status.in_(["new", "assigned", "in_progress"])
    ).all()

    breached = 0
    for ticket in open_tickets:
        if now > ticket.sla_deadline and ticket.sla_breached == 0:
            ticket.sla_breached = 1
            breached += 1
            print(f"  ⚠ SLA BREACH: {ticket.id} (priority={ticket.priority})")

    session.commit()
    session.close()
    return breached


def run_engine(interval=3):
    """Бесконечно обрабатывает заявки с интервалом interval секунд."""
    init_db()
    while True:
        session = get_session()
        tickets = session.query(Ticket).filter(
            Ticket.status.in_(["new", "assigned", "in_progress"])
        ).all()

        for ticket in tickets:
            msg = advance_ticket(ticket)
            if msg:
                print(msg)

        session.commit()
        session.close()

        # Проверяем SLA
        check_sla()

        time.sleep(interval)


if __name__ == "__main__":
    print("Запуск движка симулятора...")
    run_engine(interval=3)
