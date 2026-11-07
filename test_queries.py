import sys
sys.path.insert(0, "rag")
from retriever import retrieve

TESTS = [
    {"query": "Как настроить PID-контроллер для двигателя?", "expected": "mechatronics-pid-01"},
    {"query": "Какой алгоритм использовать для роя дронов?", "expected": "swarm-boids-01"},
    {"query": "Как оптимизировать распределение задач между роботами?", "expected": "swarm-pso-01"},
    {"query": "Как роботы обмениваются данными?", "expected": "interaction-ros-01"},
]


def run_tests(k=3):
    hits = 0
    mrr_sum = 0.0

    for test in TESTS:
        results = retrieve(test["query"], k=k)
        found_ids = [r["id"] for r in results]

        if test["expected"] in found_ids:
            hits += 1
            rank = found_ids.index(test["expected"]) + 1
            mrr_sum += 1.0 / rank

        print(f"Запрос: {test['query']}")
        print(f"  Ожидается: {test['expected']}")
        print(f"  Найдено: {found_ids}")
        print(f"  {'✅ HIT' if test['expected'] in found_ids else '❌ MISS'}\n")

    total = len(TESTS)
    print(f"Recall@{k}: {hits/total:.2f} ({hits}/{total})")
    print(f"MRR: {mrr_sum/total:.4f}")


if __name__ == "__main__":
    run_tests(k=3)
