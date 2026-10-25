import os
from pathlib import Path
from functools import lru_cache
from typing import Any

import chromadb
from dotenv import load_dotenv
from groq import Groq
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "kgrcet_website_gemini")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768


@lru_cache(maxsize=1)
def get_resources():
    if not CHROMA_PATH.exists():
        raise RuntimeError(f"ChromaDB folder not found: {CHROMA_PATH}")
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY is missing.")
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY is missing from Render.")
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        available = [c.name for c in client.list_collections()]
        raise RuntimeError(
            f"Could not open '{COLLECTION_NAME}'. Available collections: {available}. "
            "Run reindex_with_gemini.py locally first."
        ) from exc
    if collection.count() == 0:
        raise RuntimeError(f"Collection '{COLLECTION_NAME}' is empty.")
    return collection, Groq(api_key=groq_key), genai.Client(api_key=gemini_key)


def _embed_query(text: str, gemini_client) -> list[float]:
    result = gemini_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    if not result.embeddings or not result.embeddings[0].values:
        raise RuntimeError("Gemini returned an empty embedding.")
    vector = [float(v) for v in result.embeddings[0].values]
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise RuntimeError(f"Expected {EMBEDDING_DIMENSIONS} dimensions; got {len(vector)}.")
    return vector


def _first_metadata_value(metadata: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value:
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
                {"role": "system", "content":
                 "Rewrite the latest user question as a standalone search question using "
                 "conversation only to resolve pronouns and omitted context. Return only the "
                 "rewritten question. Previous assistant answers are not verified facts."},
                {"role": "user", "content":
                 f"Recent conversation:\n{history_text}\n\nLatest question:\n{question}"},
            ],
        )
        rewritten = (response.choices[0].message.content or "").strip().strip('"')
        if 2 <= len(rewritten) <= 1000:
            return rewritten
    except Exception as exc:
        print(f"Follow-up rewrite failed: {type(exc).__name__}: {exc}")
    return question


def ask_rag(question: str, history: list[dict[str, str]] | None = None, top_k: int = 6) -> dict[str, Any]:
    collection, groq_client, gemini_client = get_resources()
    history = history or []
    search_question = _standalone_question(question, history, groq_client)
    query_vector = _embed_query(search_question, gemini_client)
    count = collection.count()
    if count == 0:
        return {"answer": "The KGRCET knowledge base is empty.", "sources": [],
                "resolved_question": search_question}
    results = collection.query(
        query_embeddings=[query_vector], n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )
    docs = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    if not docs:
        return {"answer": "I couldn't find relevant information in the indexed KGRCET website content.",
                "sources": [], "resolved_question": search_question}

    evidence_parts, sources, seen_urls = [], [], set()
    for i, document in enumerate(docs):
        if not document:
            continue
        metadata = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
        url = _first_metadata_value(metadata, ["url", "source_url", "source", "URL", "link", "page_url"])
        title = _first_metadata_value(metadata, ["title", "page_title", "name"]) or "Official KGRCET page"
        evidence_parts.append(f"[Source {len(evidence_parts)+1}]\nTitle: {title}\nURL: {url or 'URL not available'}\nContent:\n{document}")
        if url and url.startswith(("https://", "http://")) and url not in seen_urls:
            seen_urls.add(url)
            source = {"title": title, "url": url}
            if i < len(distances) and distances[i] is not None:
                try:
                    source["distance"] = float(distances[i])
                except (TypeError, ValueError):
                    pass
            sources.append(source)

    system_prompt = """You are the KG Reddy College of Engineering & Technology (KGRCET) website assistant.
Use retrieved official website evidence as the only factual source. Conversation history only resolves references; it is not factual proof. Never invent facts. If evidence is absent or conflicting, say it could not be verified. Keep answers concise and cite evidence as [Source 1], [Source 2]. Do not cite a source unless it supports the claim."""
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL, temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content":
             f"Recent conversation (reference resolution only):\n{_history_text(history) or '(none)'}\n\n"
             f"Original question: {question}\nStandalone search question: {search_question}\n\n"
             f"Retrieved official website evidence:\n{chr(10).join(evidence_parts)}\n\n"
             "Answer the original question using retrieved evidence only."},
        ],
    )
    answer = response.choices[0].message.content or "I couldn't generate an answer."
    return {"answer": answer.strip(), "sources": sources, "resolved_question": search_question}
