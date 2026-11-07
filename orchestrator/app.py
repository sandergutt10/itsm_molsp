from fastapi import FastAPI
from pydantic import BaseModel
from pipeline import run_full_pipeline, get_open_tickets, get_default_engineers, tickets_to_tasks
from scheduler import solve_molsp, format_schedule
import asyncio

app = FastAPI(title="ITSM Orchestrator", version="1.0")


class PipelineRequest(BaseModel):
    query: str
    category: str | None = None
    auto_create: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pipeline")
async def pipeline(req: PipelineRequest):
    """
    Полный сквозной сценарий:
    вопрос → RAG → заявка → MOLSP → расписание.
    """
    result = await run_full_pipeline(
        query=req.query,
        category=req.category,
        auto_create=req.auto_create,
    )
    return result


@app.get("/schedule")
async def get_schedule():
    """
    Получить расписание на день по текущим открытым заявкам.
    (Без RAG — только ITSM + MOLSP.)
    """
    tickets = await get_open_tickets()
    tasks = tickets_to_tasks(tickets)
    engineers = get_default_engineers()

    schedule = solve_molsp(tasks, engineers, num_slots=8)
    text = format_schedule(schedule, engineers, num_slots=8)

    return {
        "status": schedule.status,
        "total_penalty": schedule.total_penalty,
        "max_load": schedule.max_load,
        "loads": schedule.loads,
        "assigned": len(schedule.assignments),
        "unassigned": schedule.unassigned,
        "assignments": [
            {
                "task_id": a.task_id,
                "engineer": a.engineer_name,
                "slot": a.slot,
                "priority": a.priority,
                "title": a.title,
                "sla_ok": a.sla_ok,
            }
            for a in schedule.assignments
        ],
        "schedule_text": text,
    }
