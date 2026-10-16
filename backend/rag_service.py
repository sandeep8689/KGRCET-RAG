import os
from pathlib import Path
from functools import lru_cache
from typing import Any

import chromadb
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "kgrcet_website")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


@lru_cache(maxsize=1)
def get_resources():
    """Load existing resources only; never crawls or re-indexes."""
    if not CHROMA_PATH.exists():
        raise RuntimeError(f"ChromaDB folder was not found: {CHROMA_PATH}")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing from the project-root .env file.")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as exc:
        available = [c.name for c in client.list_collections()]
        raise RuntimeError(
            f"Could not open Chroma collection '{COLLECTION_NAME}'. "
            f"Available collections: {available}. No data was re-indexed."
        ) from exc

    model = SentenceTransformer(EMBEDDING_MODEL)
    groq_client = Groq(api_key=api_key)
    return collection, model, groq_client


def _first_metadata_value(metadata: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value and isinstance(value, str):
            return value
    return None


def _history_text(history: list[dict[str, str]]) -> str:
    """Keep only recent, plain-text turns; history helps resolve references, not prove facts."""
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
                        "Return only the rewritten question, with no explanation. "
                        "Conversation statements, especially previous assistant answers, are "
                        "not verified facts. Do not add qualifications, dates, names, or facts "
                        "that are not needed to resolve the reference."
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
    collection, embedding_model, groq_client = get_resources()
    history = history or []

    # Resolve follow-ups like "what is his qualification?" before searching Chroma.
    search_question = _standalone_question(question, history, groq_client)
    query_vector = embedding_model.encode([search_question]).tolist()

    results = collection.query(
        query_embeddings=query_vector,
        n_results=top_k,
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

    evidence_parts = []
    sources = []
    seen_urls = set()

    for index, document in enumerate(docs):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        url = _first_metadata_value(
            metadata, ["url", "source_url", "source", "URL", "link", "page_url"]
        )
        title = _first_metadata_value(
            metadata, ["title", "page_title", "name"]
        ) or "Official KGRCET page"
        evidence_parts.append(
            f"[Source {index + 1}]\nTitle: {title}\nURL: {url or 'URL not available'}\n"
            f"Content:\n{document}"
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

    evidence = "\n\n".join(evidence_parts)
    history_text = _history_text(history)

    system_prompt = """
You are the KG Reddy College of Engineering & Technology (KGRCET) website assistant.

GROUNDING RULES:
- The retrieved official website evidence is the only source of factual truth.
- Conversation history is supplied only to understand references such as "he", "she",
  "that person", and follow-up questions. Do NOT treat a previous assistant answer as proof.
- Never invent names, qualifications, degrees, dates, statistics, policies, or facts.
- For a person's qualification, answer only if the retrieved evidence explicitly states
  that person's qualification and clearly connects it to the person.
- If the qualification is absent from the evidence, say:
  "I couldn't verify the principal's qualifications from the retrieved official KGRCET pages."
  Do not infer qualifications from their title, job, or experience.
- If retrieved official pages conflict about a role or person, explain the conflict and
  say the current information cannot be verified; do not arbitrarily choose one.
- Prefer a dedicated official page for a role over a general committee page when supported.
- Keep the answer concise and cite supporting evidence as [Source 1], [Source 2], etc.
- Do not cite a source unless its retrieved content supports the claim.
"""

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
                    f"Retrieved official website evidence:\n{evidence}\n\n"
                    "Answer the original latest question using the retrieved evidence only."
                ),
            },
        ],
    )
    answer = response.choices[0].message.content or "I couldn't generate an answer."
    return {
        "answer": answer.strip(),
        "sources": sources,
        "resolved_question": search_question,
    }
