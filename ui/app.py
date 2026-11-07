"""
Streamlit UI для лабораторной работы 3.
Веб-интерфейс для сквозного сценария: вопрос → RAG → заявка → MOLSP.

Запуск (в Docker):
  docker compose up --build
  Откройте http://localhost:8501

Запуск (локально, без Docker):
  streamlit run ui/app.py
"""

import streamlit as st
import httpx
import json

# Адреса сервисов
# В Docker — имена контейнеров; локально — localhost
import os
ITSM_URL = os.environ.get("ITSM_URL", "http://localhost:8001")
RAG_URL = os.environ.get("RAG_URL", "http://localhost:8002")
ORCH_URL = os.environ.get("ORCH_URL", "http://localhost:8003")


# --- Настройки страницы ---
st.set_page_config(
    page_title="ITSM: RAG + MOLSP",
    page_icon="🛠️",
    layout="wide",
)


@st.cache_data(ttl=5)
def check_health():
    """Проверяет доступность сервисов (кэш 5 секунд)."""
    results = {}
    for name, url in [("ITSM", ITSM_URL), ("RAG", RAG_URL), ("Orchestrator", ORCH_URL)]:
        try:
            resp = httpx.get(f"{url}/health", timeout=5)
            results[name] = resp.status_code == 200
        except Exception:
            results[name] = False
    return results


def call_rag(query, category=None, k=3):
    """Запрос к RAG-сервису."""
    payload = {"query": query, "k": k}
    if category:
        payload["category"] = category
    resp = httpx.post(f"{RAG_URL}/ask", json=payload, timeout=30)
    return resp.json()


def call_itsm_create(title, description, priority):
    """Создание заявки в ITSM."""
    resp = httpx.post(
        f"{ITSM_URL}/tickets",
        json={
            "title": title,
            "description": description,
            "priority": priority,
            "type": "incident",
        },
        timeout=10,
    )
    return resp.json()


def call_itsm_tickets(status=None, limit=100):
    """Получение списка заявок."""
    url = f"{ITSM_URL}/tickets?limit={limit}"
    if status:
        url += f"&status={status}"
    resp = httpx.get(url, timeout=10)
    return resp.json()


def call_itsm_simulate(count=10):
    """Создание случайных заявок."""
    resp = httpx.post(f"{ITSM_URL}/simulate?count={count}", timeout=30)
    return resp.json()


def call_itsm_tick():
    """Шаг движка статусов."""
    resp = httpx.post(f"{ITSM_URL}/tick", timeout=10)
    return resp.json()


def call_itsm_metrics(hours=24):
    """Получение метрик."""
    resp = httpx.get(f"{ITSM_URL}/metrics?hours={hours}", timeout=10)
    return resp.json()


def call_schedule():
    """Получение расписания от MOLSP."""
    resp = httpx.get(f"{ORCH_URL}/schedule", timeout=60)
    return resp.json()


def call_pipeline(query, category=None, auto_create=True):
    """Сквозной сценарий через оркестратор."""
    payload = {"query": query, "auto_create": auto_create}
    if category:
        payload["category"] = category
    resp = httpx.post(f"{ORCH_URL}/pipeline", json=payload, timeout=60)
    return resp.json()


# --- Интерфейс ---

st.title("🛠️ ITSM: RAG + Заявки + MOLSP")
st.caption("Лабораторная работа 3: сквозной сценарий")

# Проверка сервисов
health = check_health()
cols = st.columns(3)
for i, (name, ok) in enumerate(health.items()):
    with cols[i]:
        if ok:
            st.success(f"✅ {name}")
        else:
            st.error(f"❌ {name} недоступен")

st.divider()

# --- Вкладки ---
tab1, tab2, tab3, tab4 = st.tabs([
    "🔄 Сквозной сценарий",
    "🔍 RAG-бот",
    "📋 Заявки и метрики",
    "📅 Расписание MOLSP",
])

# ========================
# Вкладка 1: Сквозной сценарий
# ========================
with tab1:
    st.header("Сквозной сценарий: вопрос → RAG → заявка → расписание")

    with st.form("pipeline_form"):
        query = st.text_input(
            "Вопрос пользователя:",
            value="Сервер не отвечает, нужно срочно восстановить",
            help="Введите вопрос или описание проблемы",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            category = st.selectbox(
                "Категория (опционально)",
                ["", "Swarm Robotics", "Robot Interaction", "Mechatronics",
                 "Incident Management", "Problem Management", "Change Enablement"],
                help="Фильтр по категории базы знаний",
            )
        with col_b:
            auto_create = st.checkbox("Автосоздание заявки", value=True,
                help="Если RAG не нашёл ответ — создать заявку автоматически")

        submitted = st.form_submit_button("🚀 Запустить сценарий")

    if submitted:
        with st.spinner("Выполняется сквозной сценарий..."):
            try:
                result = call_pipeline(
                    query,
                    category=category if category else None,
                    auto_create=auto_create,
                )

                # Шаг 1: RAG
                st.subheader("Шаг 1: RAG-поиск")
                rag = result.get("step_1_rag", {})
                sources = rag.get("sources", [])
                answer = rag.get("answer", "")

                st.write("**Ответ RAG:**")
                st.text_area("Answer", value=answer, height=150, key="rag_answer")

                if sources:
                    st.write("**Найденные источники:**")
                    for s in sources:
                        st.write(f"- `[{s['id']}]` {s['title']} (score: {s['score']:.4f})")
                else:
                    st.warning("Источники не найдены — будет создана заявка")

                st.divider()

                # Шаг 2: Заявка
                st.subheader("Шаг 2: Создание заявки")
                ticket = result.get("step_2_ticket", {})
                if ticket.get("id"):
                    st.success(f"Создана заявка: **{ticket['id']}** (статус: {ticket.get('status', '?')})")
                else:
                    st.info("Заявка не создана (автосоздание отключено или RAG нашёл ответ)")

                st.divider()

                # Шаг 3: Открытые заявки
                st.subheader("Шаг 3: Открытые заявки в ITSM")
                tickets_info = result.get("step_3_tickets", {})
                count = tickets_info.get("count", 0)
                st.write(f"Всего открытых заявок: **{count}**")

                tickets_list = tickets_info.get("tickets", [])
                if tickets_list:
                    # Таблица
                    st.dataframe(
                        data=[
                            {"ID": t["id"], "Заголовок": t["title"],
                             "Приоритет": t["priority"], "Статус": t["status"]}
                            for t in tickets_list
                        ],
                        use_container_width=True,
                    )

                st.divider()

                # Шаг 4: Расписание
                st.subheader("Шаг 4: Расписание MOLSP")
                schedule = result.get("step_4_schedule", {})

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Статус", schedule.get("status", "?"))
                with col2:
                    st.metric("Назначено", schedule.get("assigned", 0))
                with col3:
                    st.metric("Не назначено", len(schedule.get("unassigned", [])))

                # Таблица назначений
                assignments = schedule.get("assignments", [])
                if assignments:
                    st.write("**Назначения:**")
                    st.dataframe(
                        data=[
                            {
                                "Слот": f"Час {a['slot']+1}",
                                "Инженер": a["engineer"],
                                "Заявка": a["task_id"],
                                "Приоритет": a["priority"],
                                "Заголовок": a["title"][:60],
                                "SLA": "✅" if a["sla_ok"] else "⚠",
                            }
                            for a in sorted(assignments, key=lambda x: (x["slot"], x["engineer"]))
                        ],
                        use_container_width=True,
                    )

                # Текст расписания
                schedule_text = result.get("schedule_text", "")
                if schedule_text:
                    with st.expander("Текст расписания", expanded=False):
                        st.code(schedule_text, language="text")

            except Exception as e:
                st.error(f"Ошибка: {e}")

# ========================
# Вкладка 2: RAG-бот
# ========================
with tab2:
    st.header("🔍 RAG-бот по робототехнике")

    with st.form("rag_form"):
        rag_query = st.text_input(
            "Вопрос:",
            value="Как настроить PID-контроллер для двигателя?",
        )
        rag_cat = st.selectbox(
            "Категория:",
            ["", "Swarm Robotics", "Robot Interaction", "Mechatronics"],
        )
        rag_k = st.slider("Количество результатов (k)", 1, 10, 3)
        rag_submitted = st.form_submit_button("Найти")

    if rag_submitted:
        with st.spinner("Поиск..."):
            try:
                result = call_rag(rag_query, category=rag_cat or None, k=rag_k)

                st.subheader("Ответ")
                st.write(result.get("answer", ""))

                sources = result.get("sources", [])
                if sources:
                    st.subheader("Источники")
                    for s in sources:
                        with st.expander(f"[{s['id']}] {s['title']} (score: {s['score']:.4f})"):
                            st.write(f"**Score:** {s['score']:.4f}")
                            st.write(f"**ID:** {s['id']}")

            except Exception as e:
                st.error(f"Ошибка: {e}")

# ========================
# Вкладка 3: Заявки и метрики
# ========================
with tab3:
    st.header("📋 Заявки ITSM и метрики")

    # Управление
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🎲 Создать 10 случайных заявок"):
            result = call_itsm_simulate(10)
            st.success(f"Создано: {result.get('created', 0)} заявок")
    with col2:
        if st.button("⏭ Продвинуть статусы"):
            result = call_itsm_tick()
            st.info(f"Продвинуто: {result.get('advanced', 0)}, SLA нарушено: {result.get('sla_breached_now', 0)}")
    with col3:
        if st.button("🔄 Обновить"):
            st.rerun()

    st.divider()

    # Список заявок
    st.subheader("Заявки")
    filter_status = st.selectbox(
        "Фильтр по статусу:",
        ["Все", "new", "assigned", "in_progress", "resolved", "closed"],
    )

    try:
        tickets = call_itsm_tickets(
            status=None if filter_status == "Все" else filter_status,
        )
        if tickets:
            st.dataframe(
                data=[
                    {
                        "ID": t["id"],
                        "Заголовок": t["title"],
                        "Приоритет": t["priority"],
                        "Статус": t["status"],
                        "Тип": t["type"],
                        "SLA нарушен": "⚠" if t.get("sla_breached") else "✅",
                        "Создана": t["created_at"][:19] if t.get("created_at") else "",
                    }
                    for t in tickets
                ],
                use_container_width=True,
            )
        else:
            st.info("Заявок нет. Создайте через кнопку выше или через сквозной сценарий.")
    except Exception as e:
        st.error(f"Ошибка получения заявок: {e}")

    st.divider()

    # Метрики
    st.subheader("Метрики")
    try:
        metrics = call_itsm_metrics(hours=24)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего заявок", metrics.get("total_tickets", 0))
        with col2:
            st.metric("Решено", metrics.get("resolved", 0))
        with col3:
            st.metric("MTTR (сек)", metrics.get("mttr_seconds", 0))
        with col4:
            st.metric("SLA Breach (%)", metrics.get("sla_breach_rate", 0))

        st.write("**По приоритетам:**")
        by_priority = metrics.get("by_priority", {})
        if by_priority:
            st.dataframe(
                data=[
                    {
                        "Приоритет": p,
                        "Всего": data["total"],
                        "Нарушено SLA": data["breached"],
                        "% нарушений": f"{(data['breached']/data['total']*100) if data['total'] > 0 else 0:.1f}%",
                    }
                    for p, data in by_priority.items()
                ],
                use_container_width=True,
            )
    except Exception as e:
        st.error(f"Ошибка получения метрик: {e}")

# ========================
# Вкладка 4: Расписание MOLSP
# ========================
with tab4:
    st.header("📅 Расписание MOLSP")

    st.write("Планировщик берёт все открытые заявки из ITSM и распределяет их между инженерами по слотам дня.")

    if st.button("🚀 Запустить планировщик", type="primary"):
        with st.spinner("Решение задачи MOLSP..."):
            try:
                data = call_schedule()

                # Сводка
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Статус", data.get("status", "?"))
                with col2:
                    st.metric("Назначено", data.get("assigned", 0))
                with col3:
                    st.metric("Не назначено", len(data.get("unassigned", [])))
                with col4:
                    st.metric("Макс. загрузка", f"{data.get('max_load', 0)} слотов")

                
                # Загрузка инженеров
                st.subheader("Загрузка инженеров")
                loads = data.get("loads", {})

                if loads:
                    import pandas as pd

                    df_loads = pd.DataFrame({
                        "Инженер": list(loads.keys()),
                        "Слоты": list(loads.values()),
                    })

                    st.bar_chart(
                        data=df_loads,
                        x="Инженер",
                        y="Слоты",
                        use_container_width=True,
                    )

                    for eng, load in loads.items():
                        st.write(f"**{eng}**: {load} слотов")


                # Назначения
                st.subheader("Назначения")
                assignments = data.get("assignments", [])
                if assignments:
                    st.dataframe(
                        data=[
                            {
                                "Слот": f"Час {a['slot']+1}",
                                "Инженер": a["engineer"],
                                "Заявка": a["task_id"],
                                "Приоритет": a["priority"],
                                "Заголовок": a["title"][:60],
                                "SLA": "✅" if a["sla_ok"] else "⚠",
                            }
                            for a in sorted(assignments, key=lambda x: (x["slot"], x["engineer"]))
                        ],
                        use_container_width=True,
                    )

                # Не назначенные
                unassigned = data.get("unassigned", [])
                if unassigned:
                    st.warning(f"Не назначено: {', '.join(unassigned)}")

                # Текст расписания
                text = data.get("schedule_text", "")
                if text:
                    with st.expander("Полное расписание (текст)", expanded=True):
                        st.code(text, language="text")

            except Exception as e:
                st.error(f"Ошибка: {e}")
