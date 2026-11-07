from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from models import Ticket, get_session, init_db, SLA_TIMES
from generator import generate_ticket
from engine import advance_ticket, check_sla
from metrics import calculate_metrics, export_csv
from datetime import datetime, timedelta
import random
import string

app = FastAPI(title="ITSM Simulator", version="1.0")


class TicketCreate(BaseModel):
    """Модель для ручного создания заявки."""
    title: str
    description: str = ""
    priority: str = "medium"       # critical, high, medium, low
    type: str = "incident"         # incident или service_request


class StatusUpdate(BaseModel):
    """Модель для смены статуса."""
    status: str                    # new, assigned, in_progress, resolved, closed


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tickets")
def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    limit: int = Query(default=50, le=200),
):
    """Список заявок с фильтром по статусу и приоритету."""
    session = get_session()
    query = session.query(Ticket)

    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)

    tickets = query.order_by(Ticket.created_at.desc()).limit(limit).all()
    session.close()

    return [
        {
            "id": t.id,
            "title": t.title,
            "priority": t.priority,
            "status": t.status,
            "type": t.type,
            "created_at": t.created_at.isoformat(),
            "sla_deadline": t.sla_deadline.isoformat(),
            "sla_breached": bool(t.sla_breached),
            "assigned_to": t.assigned_to,
            "resolution_time_sec": t.resolution_time_sec,
        }
        for t in tickets
    ]


@app.post("/tickets")
def create_ticket(req: TicketCreate):
    """Создать заявку вручную."""
    session = get_session()
    now = datetime.utcnow()
    sla_time = SLA_TIMES.get(req.priority, 86400)

    ticket_id = "TKT-" + "".join(random.choices(string.digits, k=6))

    ticket = Ticket(
        id=ticket_id,
        type=req.type,
        title=req.title,
        description=req.description,
        priority=req.priority,
        status="new",
        created_at=now,
        updated_at=now,
        sla_deadline=now + timedelta(seconds=sla_time),
    )

    session.add(ticket)
    session.commit()
    session.close()

    return {"id": ticket_id, "status": "created"}


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    """Детали конкретной заявки."""
    session = get_session()
    ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        session.close()
        raise HTTPException(status_code=404, detail="Ticket not found")

    result = {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "type": ticket.type,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "sla_deadline": ticket.sla_deadline.isoformat(),
        "sla_breached": bool(ticket.sla_breached),
        "assigned_to": ticket.assigned_to,
        "resolution_time_sec": ticket.resolution_time_sec,
    }
    session.close()
    return result


@app.patch("/tickets/{ticket_id}")
def update_status(ticket_id: str, req: StatusUpdate):
    """Сменить статус заявки."""
    session = get_session()
    ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        session.close()
        raise HTTPException(status_code=404, detail="Ticket not found")

    valid_statuses = ["new", "assigned", "in_progress", "resolved", "closed"]
    if req.status not in valid_statuses:
        session.close()
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {valid_statuses}")

    ticket.status = req.status
    ticket.updated_at = datetime.utcnow()

    if req.status == "resolved":
        ticket.resolved_at = datetime.utcnow()
        ticket.resolution_time_sec = int(
            (ticket.resolved_at - ticket.created_at).total_seconds()
        )

    session.commit()
    session.close()
    return {"id": ticket_id, "status": req.status}


@app.post("/simulate")
def simulate_batch(count: int = Query(default=10, le=50)):
    """Создать count случайных заявок (для быстрой демонстрации)."""
    ids = []
    for _ in range(count):
        tid = generate_ticket()
        ids.append(tid)
    return {"created": len(ids), "ids": ids}


@app.post("/tick")
def tick():
    """Один шаг движка: продвинуть все заявки по статусам + проверить SLA."""
    session = get_session()
    tickets = session.query(Ticket).filter(
        Ticket.status.in_(["new", "assigned", "in_progress"])
    ).all()

    messages = []
    for ticket in tickets:
        msg = advance_ticket(ticket)
        if msg:
            messages.append(msg)

    session.commit()
    session.close()

    breached = check_sla()

    return {"advanced": len(messages), "sla_breached_now": breached, "details": messages}


@app.get("/metrics")
def get_metrics(hours: int = Query(default=24, le=168)):
    """Отчёт по метрикам."""
    return calculate_metrics(hours=hours)


@app.get("/metrics/export")
def export_metrics(hours: int = Query(default=24, le=168)):
    """Выгрузка отчёта в CSV."""
    metrics = calculate_metrics(hours=hours)
    csv_text = export_csv(metrics)

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=metrics.csv"},
    )
