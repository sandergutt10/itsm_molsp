import os
import httpx
from retriever import retrieve

# --- Настройки LLM через переменные окружения ---
# Если LLM_API_KEY не задан — используется шаблонный ответ
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))


def build_prompt(query: str, fragments: list) -> str:
    """Собирает промпт для LLM из найденных фрагментов."""
    context_block = ""
    for i, frag in enumerate(fragments, 1):
        context_block += (
            f"[{i}] (id: {frag['id']}) {frag['title']}: {frag['content']}\n\n"
        )

    return f"""Ты — технический консультант по робототехнике.
Ответь на вопрос пользователя, опираясь ТОЛЬКО на приведённые ниже фрагменты базы знаний.
Обязательно укажи ID статей, которые использовал, в формате [id].
Если информации недостаточно для полного ответа — скажи это прямо и предложи обратиться к инженеру.

Фрагменты базы знаний:
{context_block}

Вопрос: {query}

Ответ:"""


def call_llm(prompt: str) -> str | None:
    """
    Вызывает LLM через OpenAI-совместимый API.
    Возвращает текст ответа или None, если вызов не удался.
    Работает с любым API, совместимым с OpenAI format:
    - OpenAI (https://api.openai.com/v1/chat/completions)
    - Yandex GPT (https://llm.api.cloud.yandex.net/llm/v1/chat/completions)
    - Локальный Ollama (http://localhost:11434/v1/chat/completions)
    - vLLM, LM Studio, и т.д.
    """
    if not LLM_API_KEY:
        return None

    try:
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            resp = client.post(
                LLM_API_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Ты — технический консультант по робототехнике "
                                "и ITSM. Отвечай кратко и по делу. "
                                "Всегда указывай ID использованных статей."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM] Ошибка вызова: {e}")
        return None


def generate_answer(query: str, k: int = 3, category: str = None):
    """
    Полный цикл RAG: поиск + генерация.
    Если настроен LLM — использует реальную модель.
    Если нет — собирает шаблонный ответ из найденных фрагментов.
    """
    fragments = retrieve(query, k=k, category=category)
    prompt = build_prompt(query, fragments)

    # Пытаемся вызвать LLM
    llm_answer = call_llm(prompt)

    if llm_answer:
        answer = llm_answer
        answer_source = "llm"
    else:
        # Откат к шаблонному ответу
        answer_parts = []
        for frag in fragments:
            answer_parts.append(f"[{frag['id']}] {frag['content'][:250]}...")

        answer = (
            f"По вашему вопросу найдены следующие материалы:\n\n"
            + "\n\n".join(answer_parts)
            + "\n\nПодробности — в указанных статьях."
        )
        answer_source = "template"

    sources = [
        {"id": f["id"], "title": f["title"], "score": f["score"]}
        for f in fragments
    ]

    return {
        "answer": answer,
        "sources": sources,
        "prompt": prompt,
        "answer_source": answer_source,
    }


if __name__ == "__main__":
    result = generate_answer("Какой алгоритм использовать для координации роя дронов?")
    print(f"Источник ответа: {result['answer_source']}")
    print(f"\nОТВЕТ:\n{result['answer']}")
    print("\nИСТОЧНИКИ:")
    for s in result["sources"]:
        print(f"  [{s['id']}] {s['title']} (score: {s['score']:.4f})")
