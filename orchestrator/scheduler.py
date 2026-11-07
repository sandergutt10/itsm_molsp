import pulp
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# --- Структуры данных ---

@dataclass
class Task:
    """Заявка для планирования."""
    id: str
    title: str
    priority: str            # critical, high, medium, low
    sla_slot: int             # крайний слот для SLA (например, 2 = до конца 3-го часа)
    duration_slots: int = 1   # сколько слотов занимает задача (по умолчанию 1)


@dataclass
class Engineer:
    """Инженер с уровнем и доступностью."""
    id: str
    name: str
    level: str                # L1, L2, L3
    max_slots: int = 8        # максимум слотов в день


@dataclass
class Assignment:
    """Результат: назначение заявки инженеру в слот."""
    task_id: str
    engineer_id: str
    engineer_name: str
    slot: int                 # 0-индексированный слот (0 = первый час)
    priority: str
    title: str
    sla_ok: bool              # уложились в SLA?


@dataclass
class ScheduleResult:
    """Полный результат планирования."""
    assignments: List[Assignment] = field(default_factory=list)
    unassigned: List[str] = field(default_factory=list)
    total_penalty: float = 0.0
    max_load: int = 0
    loads: Dict[str, int] = field(default_factory=dict)
    status: str = ""          # "optimal", "feasible", "infeasible"


# --- Веса приоритетов ---

PRIORITY_WEIGHTS = {
    "critical": 100,
    "high": 50,
    "medium": 20,
    "low": 5,
}

# Кто может брать какой приоритет
LEVEL_MATRIX = {
    "critical": ["L3"],
    "high": ["L2", "L3"],
    "medium": ["L1", "L2", "L3"],
    "low": ["L1", "L2", "L3"],
}


def solve_molsp(
    tasks: List[Task],
    engineers: List[Engineer],
    num_slots: int = 8,
    balance_lambda: float = 10.0,
) -> ScheduleResult:
    """
    Решает задачу MOLSP:
    - распределяет задачи по инженерам и слотам;
    - минимизирует штраф за позднее выполнение + балансирует нагрузку.

    Возвращает ScheduleResult с назначениями.
    """
    import os

    print("!!! MOLSP FUNCTION CALLED !!!", flush=True)
    print("SCHEDULER FILE:", os.path.abspath(__file__), flush=True)
    print("TASK COUNT:", len(tasks), flush=True)
    if not tasks:
        return ScheduleResult(
            assignments=[],
            unassigned=[],
            status="empty",
            loads={e.id: 0 for e in engineers},
        )

    if not engineers:
        return ScheduleResult(
            unassigned=[t.id for t in tasks],
            status="no_engineers",
        )

    # --- Создаём задачу линейного программирования ---
    prob = pulp.LpProblem("MOLSP_Schedule", pulp.LpMinimize)

    # --- Переменные ---
    # x[i][j][t] = 1, если задача i назначена инженеру j в слот t
    x = {}
    for i, task in enumerate(tasks):
        for j, eng in enumerate(engineers):
            # Проверяем, может ли инженер этого уровня брать такой приоритет
            if eng.level not in LEVEL_MATRIX.get(task.priority, ["L1", "L2", "L3"]):
                continue
            # Проверяем, помещается ли задача по длительности в оставшиеся слоты
            max_start = num_slots - task.duration_slots
            for t in range(max_start + 1):
                var_name = f"x_{i}_{j}_{t}"
                x[(i, j, t)] = pulp.LpVariable(var_name, cat=pulp.LpBinary)
    print("\n========== MOLSP DEBUG ==========")

    print("Заявки:")
    for task in tasks:
        print(
            f"ID={task.id}, "
            f"priority={task.priority}, "
            f"sla_slot={task.sla_slot}, "
            f"duration={task.duration_slots}"
        )

    print("\nИнженеры:")
    for eng in engineers:
        print(
            f"ID={eng.id}, "
            f"level={eng.level}, "
            f"max_slots={eng.max_slots}"
        )

    print("\nКоличество переменных назначения:", len(x))

    for i, task in enumerate(tasks):
        count = sum(
            1 for j in range(len(engineers))
            for t in range(num_slots)
            if (i, j, t) in x
        )
        print(f"{task.id}: доступных вариантов назначения = {count}")

    print("=================================\n")
    # Ограничение 1: каждая задача должна быть назначена
    # ровно одному инженеру и в один временной слот
    for i, task in enumerate(tasks):
        vars_for_task = [
            x[(i, j, t)]
            for j in range(len(engineers))
            for t in range(num_slots)
            if (i, j, t) in x
        ]

        if vars_for_task:
            prob += pulp.lpSum(vars_for_task) == 1, f"assign_once_{i}"
        else:
            # Если нет подходящего инженера, задача останется неназначенной
            pass

    # --- Ограничение 2: инженер делает не более одной задачи в одном слоте ---
    # (учитываем длительность: если задача занимает 2 слота, она блокирует
    #  слоты t и t+1)
    for j, eng in enumerate(engineers):
        for t in range(num_slots):
            # Сумма всех задач, которые затрагивают слот t у инженера j
            vars_in_slot = []
            for i, task in enumerate(tasks):
                for start_t in range(num_slots):
                    if (i, j, start_t) in x:
                        # Проверяем, покрывает ли задача слот t
                        if start_t <= t < start_t + task.duration_slots:
                            vars_in_slot.append(x[(i, j, start_t)])
            if vars_in_slot:
                prob += pulp.lpSum(vars_in_slot) <= 1, f"one_per_slot_{j}_{t}"

    # --- Ограничение 3: лимит слотов инженера ---
    for j, eng in enumerate(engineers):
        total_work = []
        for i, task in enumerate(tasks):
            for t in range(num_slots):
                if (i, j, t) in x:
                    # Учитываем длительность задачи
                    total_work.append(task.duration_slots * x[(i, j, t)])
        if total_work:
            prob += pulp.lpSum(total_work) <= eng.max_slots, f"max_slots_{j}"

    # --- Ограничение 4: SLA — критичные задачи не позже sla_slot ---
    for i, task in enumerate(tasks):
        if task.sla_slot < num_slots:
            for j in range(len(engineers)):
                for t in range(task.sla_slot + 1, num_slots):
                    if (i, j, t) in x:
                        prob += x[(i, j, t)] == 0, f"sla_{i}_{j}_{t}"

    # --- Вспомогательные переменные: слот назначения и загрузка ---
    # slot_assigned[i] — в какой слот назначена задача i
    # Вспомогательная переменная: слот назначения
    slot_assigned = {}

    for i, task in enumerate(tasks):
        slot_assigned[i] = pulp.LpVariable(
            f"slot_{i}",
            lowBound=0,
            upBound=num_slots - 1,
            cat=pulp.LpInteger
        )

        vars_for_task = [
            (j, t)
            for j in range(len(engineers))
            for t in range(num_slots)
            if (i, j, t) in x
        ]

        if vars_for_task:
            prob += slot_assigned[i] == pulp.lpSum(
                t * x[(i, j, t)] for j, t in vars_for_task
            ), f"slot_link_{i}"
    # load[j] — загрузка инженера j (в слотах)
    load = {}
    for j, eng in enumerate(engineers):
        load[j] = pulp.LpVariable(f"load_{j}", lowBound=0, cat=pulp.LpInteger)
        work_vars = []
        for i, task in enumerate(tasks):
            for t in range(num_slots):
                if (i, j, t) in x:
                    work_vars.append(task.duration_slots * x[(i, j, t)])
        if work_vars:
            prob += load[j] == pulp.lpSum(work_vars), f"load_def_{j}"
        else:
            prob += load[j] == 0, f"load_def_{j}"

    # max_load — максимальная загрузка (через вспомогательную переменную)
    max_load = pulp.LpVariable("max_load", lowBound=0, cat=pulp.LpInteger)
    for j in range(len(engineers)):
        prob += max_load >= load[j], f"max_load_link_{j}"

    # --- Целевая функция ---
    # Штраф 1: сумма (вес * слот) для всех назначенных задач
    penalty_priority = pulp.lpSum(
        PRIORITY_WEIGHTS.get(task.priority, 10) * slot_assigned[i]
        for i, task in enumerate(tasks)
    )

    # Штраф 2: максимальная загрузка (балансировка)
    penalty_balance = balance_lambda * max_load

    prob += penalty_priority + penalty_balance, "TotalPenalty"

    # --- Решаем ---
    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=30)
    prob.solve(solver)
    print("SOLVER STATUS:", pulp.LpStatus[prob.status], flush=True)
    print("VARIABLES:", len(prob.variables()), flush=True)
    print("CONSTRAINTS:", len(prob.constraints), flush=True)
    status = pulp.LpStatus[prob.status]

    # --- Извлекаем результат ---
    result = ScheduleResult()
    result.status = status.lower()
    result.total_penalty = pulp.value(prob.objective) if prob.objective else 0
    result.max_load = int(pulp.value(max_load) or 0)

    assigned_ids = set()
    for i, task in enumerate(tasks):
        for j, eng in enumerate(engineers):
            for t in range(num_slots):
                if (i, j, t) in x and pulp.value(x[(i, j, t)]) is not None:
                    if pulp.value(x[(i, j, t)]) > 0.5:
                        sla_ok = t <= task.sla_slot
                        result.assignments.append(Assignment(
                            task_id=task.id,
                            engineer_id=eng.id,
                            engineer_name=eng.name,
                            slot=t,
                            priority=task.priority,
                            title=task.title,
                            sla_ok=sla_ok,
                        ))
                        assigned_ids.add(task.id)
                        break  # нашли назначение — дальше не ищем

    # Не назначенные заявки
    result.unassigned = [t.id for t in tasks if t.id not in assigned_ids]

    # Загрузка инженеров
    for j, eng in enumerate(engineers):
        load_val = pulp.value(load[j]) if j in load else 0
        result.loads[eng.id] = int(load_val or 0)

    return result


def format_schedule(result: ScheduleResult, engineers: List[Engineer], num_slots: int = 8) -> str:
    """Форматирует расписание в читаемый текст (таблица по слотам)."""
    if not result.assignments:
        return "Нет назначенных задач."

    # Сортируем по слотам
    sorted_assignments = sorted(result.assignments, key=lambda a: (a.slot, a.engineer_name))

    lines = []
    lines.append("=" * 70)
    lines.append("РАСПИСАНИЕ НА ДЕНЬ")
    lines.append("=" * 70)
    lines.append(f"Статус решения: {result.status}")
    lines.append(f"Суммарный штраф: {result.total_penalty:.1f}")
    lines.append(f"Максимальная загрузка: {result.max_load} слотов")
    lines.append("-" * 70)

    # Таблица: слот → инженер → задача
    for t in range(num_slots):
        lines.append(f"\nСлот {t+1} (час {t+1}):")
        slot_tasks = [a for a in sorted_assignments if a.slot == t]
        if not slot_tasks:
            lines.append("  (свободно)")
        for a in slot_tasks:
            sla_mark = "✅" if a.sla_ok else "⚠"
            lines.append(f"  {sla_mark} {a.engineer_name} → {a.task_id} [{a.priority}] {a.title}")

    # Сводка по инженерам
    lines.append("\n" + "-" * 70)
    lines.append("ЗАГРУЗКА ИНЖЕНЕРОВ:")
    for eng in engineers:
        load_val = result.loads.get(eng.id, 0)
        lines.append(f"  {eng.name} ({eng.level}): {load_val}/{eng.max_slots} слотов")

    # Не назначенные
    if result.unassigned:
        lines.append(f"\n⚠ НЕ НАЗНАЧЕНО: {', '.join(result.unassigned)}")

    lines.append("=" * 70)
    return "\n".join(lines)
