"""
Демонстрация MOLSP-планировщика на 20 заявках с разными приоритетами.

Запуск:
  1. docker compose up --build
  2. python demo_20_tickets.py

Скрипт:
  - загружает 20 заявок в ITSM;
  - запускает планировщик через оркестратор;
  - выводит расписание в консоль.
"""

import httpx
import time
import json

ITSM_URL = "http://localhost:8001"
ORCHESTRATOR_URL = "http://localhost:8003"

# 20 заявок: 4 critical, 6 high, 6 medium, 4 low
TICKETS = [
    # --- Critical (4) ---
    {"title": "Сервер БД не отвечает (prod)",      "description": "Продуктивная база данных недоступна, бизнес остановлен", "priority": "critical"},
    {"title": "Сайт компании недоступен",          "description": "Внешний сайт выдаёт 502, клиенты не могут оформить заказы", "priority": "critical"},
    {"title": "AD контроллер домена недоступен",    "description": "Пользователи не могут авторизоваться в домене", "priority": "critical"},
    {"title": "Сбой почтового сервера (exchange)", "description": "Входящая почта не доставляется, очередь растёт", "priority": "critical"},

    # --- High (6) ---
    {"title": "VPN туннель в филиал нестабилен",    "description": "Периодические обрывы туннеля, филиал теряет доступ к 1С", "priority": "high"},
    {"title": "Ошибка в CRM при оформлении сделки", "description": "Менеджеры не могут создать сделку, форма выдаёт 500", "priority": "high"},
    {"title": "Диск на файловом сервере 95% занят", "description": "Approaching disk full, требуется срочная чистка или расширение", "priority": "high"},
    {"title": "Сертификат на портале истекает",     "description": "SSL сертификат истекает через 2 дня, нужен перевыпуск", "priority": "high"},
    {"title": "Бэкап не выполнился ночью",          "description": "Последний успешный бэкап — 3 дня назад, нужна диагностика", "priority": "high"},
    {"title": "Пользователь заблокирован в AD",     "description": "Руководитель отдела заблокирован, нужна срочная разблокировка", "priority": "high"},

    # --- Medium (6) ---
    {"title": "Не печатает принтер в бухгалтерии", "description": "Сетевой принтер не виден в списке устройств", "priority": "medium"},
    {"title": "Тормозит 1С у трёх пользователей",   "description": "Жалобы на медленную работу в модуле «Зарплата»", "priority": "medium"},
    {"title": "Запрос на установку ПО",             "description": "Нужно установить Visual Studio Code на 5 рабочих мест", "priority": "medium"},
    {"title": "Не работает сканер в отделе кадров","description": "Сканер не определяется по USB, драйвер слетел", "priority": "medium"},
    {"title": "Запрос на доступ к сетевой папке",   "description": "Новый сотрудник нуждается в доступе к папке «Проекты»", "priority": "medium"},
    {"title": "Настройка почтовой подписи",         "description": "Нужно настроить корпоративную подпись для 3 сотрудников", "priority": "medium"},

    # --- Low (4) ---
    {"title": "Запрос на новый монитор",           "description": "Сотрудник просит заменить монитор на больший", "priority": "low"},
    {"title": "Обновить браузер на ПК ресепшена",  "description": "Установить актуальную версию Chrome", "priority": "low"},
    {"title": "Настроить заставку на ноутбуке",    "description": "Пользователь просит поменять обои рабочего стола", "priority": "low"},
    {"title": "Запрос на шредер для документов",   "description": "Отдел просит установить шредер рядом с кабинетом", "priority": "low"},
]


def check_services():
    """Проверяет, что ITSM и оркестратор запущены."""
    for name, url in [("ITSM", ITSM_URL), ("Orchestrator", ORCHESTRATOR_URL)]:
        try:
            resp = httpx.get(f"{url}/health", timeout=10)
            if resp.status_code != 200:
                print(f"❌ {name} не отвечает корректно")
                return False
            print(f"✅ {name}: OK")
        except Exception as e:
            print(f"❌ {name}: {e}")
            print("\nСначала запустите: docker compose up --build")
            return False
    return True


def load_tickets():
    """Создаёт 20 заявок в ITSM."""
    print(f"\n{'='*60}")
    print("ЗАГРУЗКА 20 ЗАЯВОК В ITSM")
    print(f"{'='*60}")

    created = []
    for i, t in enumerate(TICKETS, 1):
        resp = httpx.post(
            f"{ITSM_URL}/tickets",
            json={
                "title": t["title"],
                "description": t["description"],
                "priority": t["priority"],
                "type": "incident",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            ticket_id = resp.json()["id"]
            created.append(ticket_id)
            print(f"  [{i:2d}/20] {ticket_id} [{t['priority']:8s}] {t['title']}")
        else:
            print(f"  [{i:2d}/20] ОШИБКА: {resp.status_code} - {resp.text}")

    print(f"\nСоздано заявок: {len(created)}")
    return created


def show_schedule():
    """Получает и выводит расписание от оркестратора."""
    print(f"\n{'='*60}")
    print("ЗАПУСК MOLSP-ПЛАНИРОВЩИКА")
    print(f"{'='*60}")

    resp = httpx.get(f"{ORCHESTRATOR_URL}/schedule", timeout=60)
    resp.raise_for_status()
    data = resp.json()

    print(f"\nСтатус решения: {data.get('status', 'неизвестно')}")
    print(f"Суммарный штраф: {data.get('total_penalty', 0):.1f}")
    print(f"Макс. загрузка: {data.get('max_load', 0)} слотов")
    print(f"Назначено: {data.get('assigned', 0)}")
    print(f"Не назначено: {data.get('unassigned', [])}")
    print(f"Загрузка инженеров: {data.get('loads', {})}")

    # Подробные назначения
    assignments = data.get("assignments", [])
    print(f"\n{'='*60}")
    print("ДЕТАЛЬНОЕ РАСПИСАНИЕ:")
    print(f"{'='*60}")

    # Группируем по слотам
    by_slot = {}
    for a in assignments:
        by_slot.setdefault(a["slot"], []).append(a)

    for slot in sorted(by_slot.keys()):
        print(f"\n--- Слот {slot+1} (час {slot+1}) ---")
        for a in by_slot[slot]:
            sla = "✅" if a["sla_ok"] else "⚠"
            print(f"  {sla} {a['engineer']:15s} → {a['task_id']} [{a['priority']:8s}] {a['title'][:50]}")

    # Текстовая версия
    text = data.get("schedule_text", "")
    if text:
        print(f"\n{text}")

    return data


def main():
    if not check_services():
        return

    # Создаём заявки
    ticket_ids = load_tickets()
    if not ticket_ids:
        print("❌ Не удалось создать заявки")
        return

    # Небольшая пауза, чтобы ITSM записал в базу
    print("\nОжидание 2 секунды...")
    time.sleep(2)

    # Запускаем планировщик
    show_schedule()

    print(f"\n{'='*60}")
    print("ДЕМО ЗАВЕРШЕНО ✅")
    print(f"{'='*60}")
    print("\nДополнительно можно:")
    print(f"  - Открыть ITSM Swagger:      {ITSM_URL}/docs")
    print(f"  - Открыть оркестратор:      {ORCHESTRATOR_URL}/docs")
    print(f"  - Открыть Streamlit UI:     http://localhost:8501")
    print(f"  - Посмотреть метрики:       curl {ITSM_URL}/metrics")


if __name__ == "__main__":
    main()
