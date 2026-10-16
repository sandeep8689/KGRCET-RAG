import os
from pathlib import Path
from functools import lru_cache
from typing import Any

import chromadb
import numpy as np
import requests
from dotenv import load_dotenv
from groq import Groq

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "kgrcet_website")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
HF_TOKEN = os.getenv("HF_TOKEN")
HF_EMBEDDING_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
)


@lru_cache(maxsize=1)
def get_resources():
    """Open the existing ChromaDB collection; never crawl or re-index."""
    if not CHROMA_PATH.exists():
        raise RuntimeError(f"ChromaDB folder was not found: {CHROMA_PATH}")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing from the environment.")
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN is missing from the Render environment.")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as exc:
        available = [c.name for c in client.list_collections()]
        raise RuntimeError(
            f"Could not open Chroma collection '{COLLECTION_NAME}'. "
            f"Available collections: {available}. No data was re-indexed."
        ) from exc

    return collection, Groq(api_key=api_key)


def _embed_query(text: str) -> list[float]:
    """Generate a query embedding remotely to avoid loading PyTorch on Render."""
    response = requests.post(
        HF_EMBEDDING_URL,
        headers={
            "Authorization": f"Bearer {HF_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"inputs": text, "options": {"wait_for_model": True}},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"Hugging Face embedding request failed ({response.status_code}): "
            f"{response.text[:400]}"
        )

    arr = np.asarray(response.json(), dtype=np.float32)

    # Expected responses may be a vector [384], token embeddings [tokens, 384],
    # or a batch containing either representation.
    if arr.ndim == 1:
        vector = arr
    elif arr.ndim == 2:
        if arr.shape[-1] != 384:
            raise RuntimeError(f"Unexpected embedding response shape: {arr.shape}")
        vector = arr.mean(axis=0)
    elif arr.ndim == 3:
        if arr.shape[-1] != 384:
            raise RuntimeError(f"Unexpected embedding response shape: {arr.shape}")
        vector = arr[0].mean(axis=0)
    else:
        raise RuntimeError(f"Unexpected embedding response shape: {arr.shape}")

    if vector.shape != (384,):
        raise RuntimeError(f"Expected 384 embedding dimensions, got {vector.shape}")
    return vector.astype(float).tolist()


def _first_metadata_value(metadata: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value and isinstance(value, str):
            return value
    return None


def _history_text(history: list[dict[str, str]]) -> str:
    lines = []
    for item in history[-8:]:
        role = item.get("role", "")
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            lines.append(f"{role.upper()}: {content[:1200]}")
    return "\n".join(lines)


def _standalone_question(question: str, history: list[dict[str, str]], groq_client) -> str:
    history_text = _history_text(history)
    if not history_text:
        return question

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the latest user question as a standalone search question "
                        "using the conversation only to resolve pronouns and omitted context. "
                        "Return only the rewritten question, with no explanation. Conversation "
                        "statements, especially previous assistant answers, are not verified facts. "
                        "Do not add qualifications, dates, names, or facts not needed to resolve the reference."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Recent conversation:\n{history_text}\n\nLatest question:\n{question}",
                },
            ],
        )
        rewritten = (response.choices[0].message.content or "").strip().strip('"')
        if 2 <= len(rewritten) <= 1000:
            return rewritten
    except Exception as exc:
        print(f"Follow-up question rewrite failed: {type(exc).__name__}: {exc}")
    return question


def ask_rag(
    question: str,
    history: list[dict[str, str]] | None = None,
    top_k: int = 6,
) -> dict[str, Any]:
    collection, groq_client = get_resources()
    history = history or []

    search_question = _standalone_question(question, history, groq_client)
    query_vector = _embed_query(search_question)
    count = collection.count()
    if count == 0:
        return {
            "answer": "The KGRCET knowledge base is empty.",
            "sources": [],
            "resolved_question": search_question,
        }

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )
    docs = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    if not docs:
        return {
            "answer": "I couldn't find relevant information in the indexed KGRCET website content.",
            "sources": [],
            "resolved_question": search_question,
        }

    evidence_parts, sources, seen_urls = [], [], set()
    for index, document in enumerate(docs):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        url = _first_metadata_value(metadata, ["url", "source_url", "source", "URL", "link", "page_url"])
        title = _first_metadata_value(metadata, ["title", "page_title", "name"]) or "Official KGRCET page"
        evidence_parts.append(
            f"[Source {index + 1}]\nTitle: {title}\nURL: {url or 'URL not available'}\nContent:\n{document}"
        )
        if url and url.startswith(("https://", "http://")) and url not in seen_urls:
            seen_urls.add(url)
            source = {"title": title, "url": url}
            if index < len(distances) and distances[index] is not None:
                try:
                    source["distance"] = float(distances[index])
                except (TypeError, ValueError):
                    pass
            sources.append(source)

    system_prompt = """
You are the KG Reddy College of Engineering & Technology (KGRCET) website assistant.
GROUNDING RULES:
- Retrieved official website evidence is the only source of factual truth.
- Conversation history only resolves references; it is not factual proof.
- Never invent names, qualifications, degrees, dates, statistics, policies, or facts.
- For a person's qualification, answer only if retrieved evidence explicitly states it
  and clearly connects it to that person.
- If qualification is absent, say you couldn't verify it from retrieved official KGRCET pages.
- If official pages conflict, explain the conflict and say the information cannot be verified.
- Keep answers concise and cite evidence as [Source 1], [Source 2], etc.
- Do not cite a source unless its retrieved content supports the claim.
"""
    history_text = _history_text(history)
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Recent conversation (reference resolution only; not factual proof):\n"
                    f"{history_text or '(No previous conversation)'}\n\n"
                    f"Original latest question: {question}\n"
                    f"Standalone search question: {search_question}\n\n"
                    f"Retrieved official website evidence:\n{chr(10).join(evidence_parts)}\n\n"
                    "Answer the original latest question using retrieved evidence only."
                ),
            },
        ],
    )
    answer = response.choices[0].message.content or "I couldn't generate an answer."
    return {"answer": answer.strip(), "sources": sources, "resolved_question": search_question}
