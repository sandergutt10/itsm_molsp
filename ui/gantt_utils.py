"""
Диаграмма Ганта для расписания MOLSP.
Показывает таймлайн по часам (X) и инженерам (Y).
Каждая задача — цветной прямоугольник, цвет зависит от приоритета.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Цвета по приоритетам (hex для Plotly)
PRIORITY_COLORS = {
    "critical": "#FF4444",
    "high": "#FF8800",
    "medium": "#FFCC00",
    "low": "#88CC88",
}

# Подписи приоритетов для легенды
PRIORITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


def build_gantt(schedule_data: dict) -> go.Figure:
    """
    Строит интерактивную диаграмму Ганта.

    schedule_data — ответ от /schedule эндпоинта оркестратора.

    Возвращает plotly Figure, которую можно показать через st.plotly_chart.
    """
    assignments = schedule_data.get("assignments", [])
    loads = schedule_data.get("loads", {})

    if not assignments:
        fig = go.Figure()
        fig.add_annotation(
            text="Нет данных для отображения",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=20, color="gray"),
        )
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            height=300,
        )
        return fig

    # Список инженеров (ось Y)
    # Берём из loads, чтобы показать всех, даже если не загружен
    engineers = list(loads.keys()) if loads else []
    if not engineers:
        # Если loads пуст — берём из назначений
        engineers = sorted(set(a["engineer"] for a in assignments))

    # Словарь: инженер → уровень для подписи
    eng_levels = {
        "eng-1": "L1", "eng-2": "L2", "eng-3": "L3",
    }

    # Определяем количество слотов
    max_slot = max(a["slot"] for a in assignments) if assignments else 8

    fig = go.Figure()

    # Рисуем прямоугольники для каждой задачи
    for a in sorted(assignments, key=lambda x: (x["slot"], x["engineer"])):
        eng_name = a["engineer"]
        slot = a["slot"]
        priority = a["priority"]
        color = PRIORITY_COLORS.get(priority, "#CCCCCC")

        # Длительность: определяем по пересечению с другими задачами того же инженера
        # По умолчанию — 1 слот
        duration = 1
        # Если в данных есть duration_slots — используем его
        # (в текущей модели передаётся через task, но в assignment не возвращается)
        # Проверяем: если та же задача у того же инженера в следующем слоте — это продолжение
        same_task_next = any(
            x["task_id"] == a["task_id"]
            and x["engineer"] == eng_name
            and x["slot"] == slot + 1
            for x in assignments
        )
        if same_task_next:
            # Это продолжение — пропускаем, будет показано в следующем слоте
            continue

        # Проверяем, есть ли продолжение задачи
        # Ищем, сколько слотов подряд занимает задача у этого инженера
        task_slots = [slot]
        for next_slot in range(slot + 1, max_slot + 2):
            found = any(
                x["task_id"] == a["task_id"]
                and x["engineer"] == eng_name
                and x["slot"] == next_slot
                for x in assignments
            )
            if found:
                task_slots.append(next_slot)
            else:
                break
        duration = len(task_slots)

        # Текст при наведении
        sla_text = "✅ SLA OK" if a["sla_ok"] else "⚠ SLA VIOLATION"
        hover_text = (
            f"<b>{a['task_id']}</b><br>"
            f"Задача: {a['title'][:50]}<br>"
            f"Приоритет: {priority}<br>"
            f"Инженер: {eng_name}<br>"
            f"Слот: {slot + 1}–{slot + duration}<br>"
            f"{sla_text}"
        )

        # Прямоугольник (bar) от slot до slot + duration
        fig.add_trace(go.Bar(
            x=[duration],
            y=[eng_name],
            base=[slot],
            orientation="h",
            marker_color=color,
            marker_line_color="white",
            marker_line_width=1,
            text=a["task_id"],
            textposition="inside",
            textfont=dict(size=10, color="white"),
            hovertemplate=hover_text + "<extra></extra>",
            name=PRIORITY_LABELS.get(priority, priority),
            showlegend=False,
            width=0.6,
        ))

    # Легенда — добавляем невидимые трассы
    for priority, color in PRIORITY_COLORS.items():
        if any(a["priority"] == priority for a in assignments):
            fig.add_trace(go.Bar(
                x=[0],
                y=["__legend__"],
                marker_color=color,
                name=PRIORITY_LABELS.get(priority, priority),
                showlegend=True,
                hoverinfo="skip",
                visible="legendonly",
            ))

    # Настройка осей
    fig.update_layout(
        title=dict(
            text="Диаграмма Ганта: расписание работ",
            x=0.5,
            font=dict(size=16),
        ),
        barmode="overlay",
        height=max(350, 120 + len(engineers) * 60),
        margin=dict(l=120, r=40, t=60, b=60),
        xaxis=dict(
            title="Часы рабочего дня",
            dtick=1,
            range=[0, max_slot + 2],
            tickvals=list(range(0, max_slot + 2)),
            ticktext=[f"{h}:00" for h in range(0, max_slot + 2)],
            gridcolor="#E0E0E0",
            gridwidth=1,
        ),
        yaxis=dict(
            title="Инженеры",
            categoryorder="array",
            categoryarray=list(reversed(engineers)),  # L1 сверху, L3 снизу
            gridcolor="#E0E0E0",
            gridwidth=1,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
        ),
        plot_bgcolor="#FAFAFA",
    )

    # Добавляем вертикальные линии для каждого часа
    for h in range(1, max_slot + 2):
        fig.add_vline(
            x=h,
            line_dash="dash",
            line_color="#D0D0D0",
            line_width=1,
            layer="below",
        )

    return fig


def build_gantt_summary(schedule_data: dict) -> dict:
    """
    Возвращает сводку по расписанию для отображения под диаграммой.
    """
    assignments = schedule_data.get("assignments", [])
    loads = schedule_data.get("loads", {})
    unassigned = schedule_data.get("unassigned", [])

    # Считаем по приоритетам
    by_priority = {}
    for a in assignments:
        by_priority.setdefault(a["priority"], 0)
        by_priority[a["priority"]] += 1

    # Считаем SLA
    sla_ok = sum(1 for a in assignments if a["sla_ok"])
    sla_violated = sum(1 for a in assignments if not a["sla_ok"])

    # Загрузка инженеров в %
    max_slots = 8
    utilization = {}
    for eng, load in loads.items():
        utilization[eng] = f"{(load / max_slots * 100):.0f}%" if max_slots > 0 else "0%"

    return {
        "total_assigned": len(assignments),
        "total_unassigned": len(unassigned),
        "by_priority": by_priority,
        "sla_ok": sla_ok,
        "sla_violated": sla_violated,
        "utilization": utilization,
    }
