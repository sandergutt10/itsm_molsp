from fastapi import FastAPI
from pydantic import BaseModel
from generator import generate_answer
from retriever import retrieve

app = FastAPI(title="Robotics RAG Bot", version="1.0")


class AskRequest(BaseModel):
    query: str
    category: str | None = None
    k: int = 3


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest):
    return generate_answer(query=request.query, k=request.k, category=request.category)


@app.post("/search")
def search(request: AskRequest):
    results = retrieve(query=request.query, k=request.k, category=request.category)
    return {"results": results}
