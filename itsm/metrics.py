from models import Ticket, get_session
from datetime import datetime, timedelta
import csv
import io


def calculate_metrics(hours=24):
    """Считает метрики за последние hours часов."""
    session = get_session()
    since = datetime.utcnow() - timedelta(hours=hours)

    all_tickets = session.query(Ticket).filter(Ticket.created_at >= since).all()

    total = len(all_tickets)
    resolved = [t for t in all_tickets if t.status in ("resolved", "closed")]
    breached = [t for t in all_tickets if t.sla_breached == 1]
    open_tickets = [t for t in all_tickets if t.status not in ("resolved", "closed")]

    # MTTR — среднее время решения
    if resolved:
        mttr = sum(t.resolution_time_sec for t in resolved if t.resolution_time_sec) / len(resolved)
    else:
        mttr = 0

    # SLA Breach Rate
    breach_rate = (len(breached) / total * 100) if total > 0 else 0

    # Throughput — закрытые заявки
    throughput = len(resolved)

    # Backlog — открытые на конец периода
    backlog = len(open_tickets)

    # Распределение по приоритетам
    by_priority = {}
    for t in all_tickets:
        by_priority.setdefault(t.priority, {"total": 0, "breached": 0})
        by_priority[t.priority]["total"] += 1
        if t.sla_breached == 1:
            by_priority[t.priority]["breached"] += 1

    session.close()

    return {
        "period_hours": hours,
        "total_tickets": total,
        "resolved": len(resolved),
        "open": backlog,
        "mttr_seconds": round(mttr, 1),
        "sla_breach_rate": round(breach_rate, 1),
        "throughput": throughput,
        "backlog": backlog,
        "by_priority": by_priority,
    }


def export_csv(metrics):
    """Экспортирует метрики в CSV-строку."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Period (hours)", metrics["period_hours"]])
    writer.writerow(["Total tickets", metrics["total_tickets"]])
    writer.writerow(["Resolved", metrics["resolved"]])
    writer.writerow(["Open (backlog)", metrics["backlog"]])
    writer.writerow(["MTTR (seconds)", metrics["mttr_seconds"]])
    writer.writerow(["SLA Breach Rate (%)", metrics["sla_breach_rate"]])
    writer.writerow(["Throughput", metrics["throughput"]])

    for priority, data in metrics["by_priority"].items():
        writer.writerow([f"Priority: {priority} (total)", data["total"]])
        writer.writerow([f"Priority: {priority} (breached)", data["breached"]])

    return output.getvalue()
