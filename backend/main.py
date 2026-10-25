
from pathlib import Path
import os
import sys
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag_service import ask_rag, get_resources  # noqa: E402


app = FastAPI(
    title="KGRCET RAG Assistant API",
    description=(
        "Answers KGRCET questions using the existing ChromaDB index and Groq."
    ),
    version="1.3.0",
)

# Explicitly allow the deployed frontend and local development.
DEFAULT_ORIGINS = [
    "https://kgrcet-o95j9j71k-sandeepbadavath3-5019s-projects.vercel.app",
    "https://kgrcet-rag-git-main-sandeepbadavath3-5019s-projects.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Also accept any additional origins configured in Render.
env_origins = os.getenv("CORS_ALLOW_ORIGINS", "").split(",")

allowed_origins = list(
    dict.fromkeys(
        origin.strip().rstrip("/")
        for origin in DEFAULT_ORIGINS + env_origins
        if origin.strip()
    )
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=12000)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    history: list[HistoryMessage] = Field(
        default_factory=list,
        max_length=50,
    )


class AskResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]
    resolved_question: str | None = None


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "KGRCET RAG Assistant API",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "KGRCET RAG Assistant",
    }


@app.get("/ready")
def ready():
    try:
        collection, _ = get_resources()
        return {
            "status": "ready",
            "collection": collection.name,
            "indexed_chunks": collection.count(),
        }
    except Exception as exc:
        print(f"Readiness check failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="The RAG resources are not ready. Check backend logs.",
        ) from exc


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Please enter a question.",
        )

    try:
        history = [
            item.model_dump()
            for item in request.history
        ]

        return ask_rag(
            question=question,
            history=history,
        )

    except Exception as exc:
        print(f"RAG request failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=(
                "The assistant could not answer right now. "
                "Check backend logs and environment configuration."
            ),
        ) from exc
