"""
Сквозной тест лабораторной работы 3.
Проверяет полный цикл: вопрос → RAG → заявка → MOLSP → расписание.

Запуск: python test_e2e.py
Требования: docker compose up должен быть запущен.
"""

import httpx
import time
import json

ORCHESTRATOR_URL = "http://orchestrator:8000"
ITSM_URL = "http://itsm:8000"
RAG_URL = "http://rag-robotics:8000"


def check_health():
    """Проверяет, что все сервисы живы."""
    print("Проверка сервисов...")
    for name, url in [("ITSM", ITSM_URL), ("RAG", RAG_URL), ("Orchestrator", ORCHESTRATOR_URL)]:
        try:
            resp = httpx.get(f"{url}/health", timeout=10)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                print(f"  ✅ {name}: OK")
            else:
                print(f"  ❌ {name}: плохой ответ")
                return False
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            return False
    return True


def test_pipeline(query, expected_priority=None):
    """Запускает сквозной сценарий и проверяет результат."""
    print(f"\n{'='*60}")
    print(f"Тест: '{query}'")
    print(f"{'='*60}")

    resp = httpx.post(
        f"{ORCHESTRATOR_URL}/pipeline",
        json={"query": query, "auto_create": True},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    # Проверяем шаг 1: RAG
    rag = data.get("step_1_rag", {})
    sources = rag.get("sources", [])
    print(f"\n[1] RAG найдено источников: {len(sources)}")
    for s in sources:
        print(f"    [{s['id']}] {s['title']} (score: {s['score']:.4f})")
    assert len(sources) > 0, "RAG должен найти хотя бы один источник"

    # Проверяем шаг 2: заявка
    ticket = data.get("step_2_ticket", {})
    print(f"\n[2] Создана заявка: {ticket.get('id', 'нет')} (status: {ticket.get('status', 'нет')})")
    assert ticket.get("id"), "Заявка должна быть создана"

    # Проверяем шаг 3: открытые заявки
    tickets_info = data.get("step_3_tickets", {})
    print(f"\n[3] Открытых заявок: {tickets_info.get('count', 0)}")

    # Проверяем шаг 4: расписание
    schedule = data.get("step_4_schedule", {})
    print(f"\n[4] Статус MOLSP: {schedule.get('status', 'неизвестно')}")
    print(f"    Назначено: {schedule.get('assigned', 0)}")
    print(f"    Не назначено: {schedule.get('unassigned', [])}")
    print(f"    Макс. загрузка: {schedule.get('max_load', 0)} слотов")
    print(f"    Загрузка по инженерам: {schedule.get('loads', {})}")

    assignments = schedule.get("assignments", [])
    print(f"\n    Назначения:")
    for a in assignments:
        sla = "✅" if a["sla_ok"] else "⚠"
        print(f"      {sla} Слот {a['slot']+1}: {a['engineer']} → {a['task_id']} [{a['priority']}] {a['title'][:50]}")

    assert schedule.get("status") in ("optimal", "feasible"), f"MOLSP должен найти решение, got: {schedule.get('status')}"
    assert schedule.get("assigned", 0) > 0, "Хотя бы одна задача должна быть назначена"

    # Выводим текст расписания
    schedule_text = data.get("schedule_text", "")
    if schedule_text:
        print(f"\n{schedule_text}")

    print("✅ ТЕСТ ПРОЙДЕН\n")
    return True


def main():
    if not check_health():
        print("\n❌ Не все сервисы запущены. Выполните: docker compose up --build")
        return

    # Тест 1: критичная заявка
    test_pipeline(
        "Сервер не отвечает, нужно срочно восстановить",
        expected_priority="critical",
    )

    # Тест 2: вопрос по робототехнике
    test_pipeline(
        "Какой алгоритм использовать для координации роя дронов?",
    )

    # Тест 3: ещё один технический вопрос
    test_pipeline(
        "Как настроить PID-контроллер для шагового двигателя?",
    )

    print("=" * 60)
    print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
