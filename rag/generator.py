from retriever import retrieve


def build_prompt(query, fragments):
    context = ""
    for i, frag in enumerate(fragments, 1):
        context += f"[{i}] (id: {frag['id']}) {frag['title']}: {frag['content']}\n\n"

    return f"""Ты — технический консультант по робототехнике.
Ответь на вопрос, опираясь на приведённые фрагменты.
Укажи ID использованных статей.

Фрагменты:
{context}

Вопрос: {query}

Ответ:"""


def generate_answer(query: str, k: int = 3, category: str = None):
    fragments = retrieve(query, k=k, category=category)
    prompt = build_prompt(query, fragments)

    # Шаблонный ответ (без LLM)
    answer_parts = []
    for frag in fragments:
        answer_parts.append(f"[{frag['id']}] {frag['content'][:250]}...")

    answer = (
        f"По вашему вопросу найдены следующие материалы:\n\n"
        + "\n\n".join(answer_parts)
        + "\n\nПодробности — в указанных статьях."
    )

    sources = [
        {"id": f["id"], "title": f["title"], "score": f["score"]}
        for f in fragments
    ]

    return {"answer": answer, "sources": sources, "prompt": prompt}


if __name__ == "__main__":
    result = generate_answer("Какой алгоритм использовать для координации роя дронов?")
    print(result["answer"])
    for s in result["sources"]:
        print(f"  [{s['id']}] {s['title']}")
