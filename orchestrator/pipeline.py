import httpx
import asyncio
from scheduler import (
    solve_molsp, format_schedule,
    Task, Engineer, ScheduleResult,
)


# Адреса сервисов (по умолчанию — имена из docker-compose)
RAG_URL = "http://rag-robotics:8000"
ITSM_URL = "http://itsm:8000"


async def ask_rag(query: str, category: str = None, k: int = 3) -> dict:
    """Отправляет вопрос в RAG-сервис и возвращает ответ с источниками."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"query": query, "k": k}
        if category:
            payload["category"] = category
        resp = await client.post(f"{RAG_URL}/ask", json=payload)
        resp.raise_for_status()
        return resp.json()


async def create_ticket(title: str, description: str, priority: str = "medium") -> dict:
    """Создаёт заявку в ITSM-симуляторе."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "title": title,
            "description": description,
            "priority": priority,
            "type": "incident",
        }
        resp = await client.post(f"{ITSM_URL}/tickets", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_open_tickets() -> list:
    """Получает список открытых заявок из ITSM."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{ITSM_URL}/tickets?limit=100")
        resp.raise_for_status()
        tickets = resp.json()
        # Только открытые
        return [t for t in tickets if t["status"] not in ("resolved", "closed")]


async def advance_tickets():
    """Делает шаг движка ITSM — продвигает заявки по статусам."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{ITSM_URL}/tick")
        resp.raise_for_status()
        return resp.json()


# --- SLA в слотах: сколько слотов даём на каждый приоритет ---
# (рабочий день = 8 слотов по 1 часу)
PRIORITY_SLA_SLOTS = {
    "critical": 1,   # 1-й час
    "high": 3,        # до конца 3-го часа
    "medium": 6,      # до конца 6-го часа
    "low": 8,         # до конца дня
}


def tickets_to_tasks(tickets: list) -> list:
    """Преобразует заявки из ITSM в задачи для планировщика."""
    tasks = []
    for t in tickets:
        priority = t.get("priority", "medium")
        sla_slot = PRIORITY_SLA_SLOTS.get(priority, 8)
        # Длительность зависит от приоритета (упрощённо)
        duration = {
            "critical": 2,   # критичные — сложнее, 2 часа
            "high": 2,
            "medium": 1,
            "low": 1,
        }.get(priority, 1)

        tasks.append(Task(
            id=t["id"],
            title=t["title"],
            priority=priority,
            sla_slot=sla_slot,
            duration_slots=duration,
        ))
    return tasks


def get_default_engineers() -> list:
    """Команда поддержки по умолчанию."""
    return [
        Engineer(id="eng-1", name="Иванов И.", level="L1", max_slots=8),
        Engineer(id="eng-2", name="Петрова П.", level="L2", max_slots=8),
        Engineer(id="eng-3", name="Сидоров С.", level="L3", max_slots=6),  # L3 — меньше, он на сложных
    ]


async def run_full_pipeline(query: str, category: str = None, auto_create: bool = True):
    """
    Полный сквозной сценарий:
    1. Вопрос → RAG
    2. Если RAG недостаточен → создать заявку
    3. Все открытые заявки → MOLSP
    4. Расписание на день
    """
    result = {
        "step_1_rag": None,
        "step_2_ticket": None,
        "step_3_tickets": None,
        "step_4_schedule": None,
        "schedule_text": None,
    }

    # --- Шаг 1: спрашиваем RAG ---
    print("[1/4] Запрос к RAG...")
    rag_response = await ask_rag(query, category=category)
    result["step_1_rag"] = rag_response

    sources = rag_response.get("sources", [])
    answer = rag_response.get("answer", "")

    # --- Шаг 2: если источников мало — создаём заявку ---
    # Эвристика: если найдено 0 источников или score очень плохой — нужен инженер
    need_ticket = False
    if not sources:
        need_ticket = True
    elif sources and sources[0].get("score", 1.0) > 0.8:
        # score > 0.8 в ChromaDB = большое расстояние = слабое сходство
        need_ticket = True

    # Определяем приоритет заявки по ключевым словам в запросе
    query_lower = query.lower()
    if any(w in query_lower for w in [
        "упал",
        "сбой",
        "критич",
        "недоступен",
        "не работает",
        "не отвечает",
        "ошибка",
        "срочно",
        "восстановить",
        "авария"
    ]):
        priority = "critical"

    elif any(w in query_lower for w in [
        "не могу",
        "проблема",
        "сломал",
        "завис"
    ]):
        priority = "high"

    elif any(w in query_lower for w in [
        "как",
        "настроить",
        "обновить",
        "установить"
    ]):
        priority = "medium"

    else:
        priority = "low"

    if auto_create and need_ticket:
        print("[2/4] RAG недостаточен — создаём заявку...")
        ticket = await create_ticket(
            title=f"Автозаявка: {query[:80]}",
            description=f"Создано автоматически. Вопрос пользователя: {query}. RAG-ответ: {answer[:200]}",
            priority=priority,
        )
        result["step_2_ticket"] = ticket
    elif auto_create:
        print("[2/4] RAG нашёл ответ — создаём заявку для отслеживания...")
        ticket = await create_ticket(
            title=f"Консультация: {query[:80]}",
            description=f"RAG ответил. Вопрос: {query}",
            priority=priority,
        )
        result["step_2_ticket"] = ticket
    else:
        print("[2/4] Автосоздание отключено — заявку не создаём.")

    # --- Шаг 3: получаем все открытые заявки ---
    print("[3/4] Получение открытых заявок из ITSM...")
    open_tickets = await get_open_tickets()
    result["step_3_tickets"] = {
        "count": len(open_tickets),
        "tickets": [{"id": t["id"], "title": t["title"], "priority": t["priority"], "status": t["status"]} for t in open_tickets],
    }

    # --- Шаг 4: планирование через MOLSP ---
    print("[4/4] Запуск MOLSP-планировщика...")
    tasks = tickets_to_tasks(open_tickets)
    engineers = get_default_engineers()

    schedule = solve_molsp(tasks, engineers, num_slots=8, balance_lambda=10.0)
    schedule_text = format_schedule(schedule, engineers, num_slots=8)

    result["step_4_schedule"] = {
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
    }
    result["schedule_text"] = schedule_text

    print("Готово!")
    return result
