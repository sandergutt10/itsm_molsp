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
import os

# Новые импорты для экспорта
from export_utils import export_excel, export_pdf
from gantt_utils import build_gantt, build_gantt_summary
from auth import init_auth_state, require_auth, render_user_header, logout, has_role



# Адреса сервисов
# В Docker — имена контейнеров; локально — localhost
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
    resp = httpx.post(
        f"{ITSM_URL}/tickets",
        json={"title": title, "description": description, "priority": priority, "type": "incident"},
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

# ========================
# Точка входа
# ========================

init_auth_state()

if not require_auth():
    st.stop()

# Шапка с пользователем
render_user_header()

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

# Вкладки
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

    # Только admin и engineer могут запускать сквозной сценарий
    can_execute = has_role("admin", "engineer")

    with st.form("pipeline_form"):
        query = st.text_input(
            "Вопрос пользователя:",
            value="Сервер не отвечает, нужно срочно восстановить",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            category = st.selectbox(
                "Категория (опционально)",
                ["", "Swarm Robotics", "Robot Interaction", "Mechatronics",
                 "Incident Management", "Problem Management", "Change Enablement"],
            )
        with col_b:
            auto_create = st.checkbox("Автосоздание заявки", value=True)

        if can_execute:
            submitted = st.form_submit_button("🚀 Запустить сценарий")
        else:
            submitted = st.form_submit_button("🚀 Запустить (только просмотр)", disabled=True)
            if not can_execute:
                st.info("💡 Только инженеры и админы могут создавать заявки. Войдите как engineer или admin.")

    if submitted and can_execute:
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
                answer_source = rag.get("answer_source", "template")

                source_badge = "🤖 LLM" if answer_source == "llm" else "📝 Шаблон"
                st.write(f"**Источник ответа:** {source_badge}")
                st.text_area("Ответ RAG", value=answer, height=150, key="rag_answer")

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
                    st.info("Заявка не создана")

                st.divider()

                # Шаг 3: Открытые заявки
                st.subheader("Шаг 3: Открытые заявки в ITSM")
                tickets_info = result.get("step_3_tickets", {})
                count = tickets_info.get("count", 0)
                st.write(f"Всего открытых заявок: **{count}**")

                tickets_list = tickets_info.get("tickets", [])
                if tickets_list:
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

                # Диаграмма Ганта
                st.write("**Диаграмма Ганта:**")
                fig = build_gantt(schedule)
                st.plotly_chart(fig, use_container_width=True)

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

                # Показываем источник ответа
                answer_source = result.get("answer_source", "template")
                source_badge = "🤖 LLM" if answer_source == "llm" else "📝 Шаблон"
                st.write(f"**Источник ответа:** {source_badge}")

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
        if has_role("admin", "engineer"):
            if st.button("🎲 Создать 10 случайных заявок"):
                result = call_itsm_simulate(10)
                st.success(f"Создано: {result.get('created', 0)} заявок")
        else:
            st.button("🎲 Создать заявки", disabled=True, help="Только инженеры и админы")
    with col2:
        if has_role("admin", "engineer"):
            if st.button("⏭ Продвинуть статусы"):
                result = call_itsm_tick()
                st.info(f"Продвинуто: {result.get('advanced', 0)}, SLA нарушено: {result.get('sla_breached_now', 0)}")
        else:
            st.button("⏭ Продвинуть", disabled=True, help="Только инженеры и админы")
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
            st.info("Заявок нет.")
    except Exception as e:
        st.error(f"Ошибка: {e}")

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
        st.error(f"Ошибка: {e}")


# ========================
# Вкладка 4: Расписание MOLSP
# ========================
with tab4:
    st.header("📅 Расписание MOLSP")
    st.write("Планировщик берёт все открытые заявки из ITSM и распределяет их между инженерами по слотам дня.")

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        run_scheduler = st.button("🚀 Запустить планировщик", type="primary")
    with col_btn2:
        st.write("")  # пусто для выравнивания

    if run_scheduler:
        with st.spinner("Решение задачи MOLSP..."):
            try:
                data = call_schedule()
                st.session_state["last_schedule"] = data
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.session_state["last_schedule"] = None

    if "last_schedule" in st.session_state and st.session_state["last_schedule"]:
        data = st.session_state["last_schedule"]

        # --- Экспорт ---
        st.divider()
        st.subheader("📥 Экспорт расписания")
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        with col_exp1:
            if st.button("📊 Скачать Excel"):
                xlsx_bytes = export_excel(data)
                st.download_button(
                    label="💾 Сохранить .xlsx",
                    data=xlsx_bytes,
                    file_name=f"schedule_{data.get('status','unknown')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        with col_exp2:
            if st.button("📄 Скачать PDF"):
                pdf_bytes = export_pdf(data)
                st.download_button(
                    label="💾 Сохранить .pdf",
                    data=pdf_bytes,
                    file_name=f"schedule_{data.get('status','unknown')}.pdf",
                    mime="application/pdf",
                )
        with col_exp3:
            if st.button("📋 Скачать JSON"):
                st.download_button(
                    label="💾 Сохранить .json",
                    data=json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"),
                    file_name=f"schedule_{data.get('status','unknown')}.json",
                    mime="application/json",
                )
        st.divider()

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

        # --- Диаграмма Ганта ---
        st.subheader("📊 Диаграмма Ганта")
        fig = build_gantt(data)
        st.plotly_chart(fig, use_container_width=True)

        # Сводка под диаграммой
        gantt_summary = build_gantt_summary(data)
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            st.write("**По приоритетам:**")
            for p, count in gantt_summary["by_priority"].items():
                st.write(f"  {p}: {count}")
        with col_g2:
            st.write("**SLA:**")
            st.write(f"  ✅ OK: {gantt_summary['sla_ok']}")
            st.write(f"  ⚠ Нарушено: {gantt_summary['sla_violated']}")
        with col_g3:
            st.write("**Утилизация:**")
            for eng, util in gantt_summary["utilization"].items():
                st.write(f"  {eng}: {util}")

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
            with st.expander("Полное расписание (текст)", expanded=False):
                st.code(text, language="text")
    elif run_scheduler:
        st.info("Нет открытых заявок для планирования.")

