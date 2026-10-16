
import os
from pathlib import Path

import chromadb
from groq import Groq
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION_NAME = "kgrcet_website"

load_dotenv(ROOT / ".env")

groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    raise RuntimeError(
        "GROQ_API_KEY is missing. Add it to your .env file."
    )

# --------------------------------------------------
# 2. Initialize ChromaDB
# --------------------------------------------------

client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)

available_collections = [
    item.name for item in client.list_collections()
]

if COLLECTION_NAME not in available_collections:
    raise RuntimeError(
        f"Collection '{COLLECTION_NAME}' not found. "
        f"Available collections: {available_collections}"
    )

collection = client.get_collection(
    name=COLLECTION_NAME
)

if collection.count() == 0:
    raise RuntimeError(
        "The ChromaDB collection is empty. "
        "Run index_data.py first."
    )

# --------------------------------------------------
# 3. Initialize embedding model and Groq
# --------------------------------------------------

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)

llm = Groq(api_key=groq_api_key)

GROQ_MODEL = "openai/gpt-oss-120b"

# --------------------------------------------------
# 4. Retrieve relevant website content
# --------------------------------------------------

def ask_question(question):
    question = question.strip()

    if not question:
        return

    query_vector = model.encode(
        [question],
        normalize_embeddings=True
    ).tolist()

    results = collection.query(
        query_embeddings=query_vector,
        n_results=min(8, collection.count()),
        include=[
            "documents",
            "metadatas",
            "distances"
        ]
    )

    documents = results.get("documents", [[]])[0] or []
    metadatas = results.get("metadatas", [[]])[0] or []
    distances = results.get("distances", [[]])[0] or []

    # Keep only usable results.
    evidence = []

    for doc, meta, distance in zip(
        documents, metadatas, distances
    ):
        if not doc or not doc.strip():
            continue

        meta = meta or {}

        source = (
            meta.get("source_url")
            or meta.get("source")
            or ""
        )

        title = meta.get("title") or "KGRCET website"

        evidence.append({
            "title": title,
            "source": source,
            "text": doc.strip(),
            "distance": distance
        })

    if not evidence:
        print("\nNo relevant website content found.")
        return

    # Prioritize pages whose content matches the question.
    # Lower ChromaDB distance generally means a closer match.
    evidence.sort(key=lambda item: item["distance"])

    # Limit prompt size.
    selected = evidence[:5]

    context_parts = []

    for i, item in enumerate(selected, start=1):
        context_parts.append(
            f"[Source {i}]\n"
            f"Title: {item['title']}\n"
            f"URL: {item['source'] or 'URL unavailable'}\n"
            f"Content:\n{item['text'][:2500]}"
        )

    context = "\n\n".join(context_parts)

    # --------------------------------------------------
    # 5. Generate answer with Groq
    # --------------------------------------------------

    try:
        response = llm.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the official KG Reddy College of "
                        "Engineering and Technology information assistant.\n"
                        "Use only the supplied website evidence.\n"
                        "Answer the exact question directly and concisely.\n"
                        "Do not repeat unrelated website navigation text.\n"
                        "For names, designations, dates, and contact details, "
                        "use only information explicitly supported by evidence.\n"
                        "If evidence is insufficient or conflicting, clearly "
                        "say that the information could not be verified.\n"
                        "Never invent facts or sources.\n"
                        "Cite the supporting URL at the end of the answer."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Retrieved official website evidence:\n{context}"
                    )
                }
            ],
            temperature=0.1,
            max_tokens=500
        )

        answer = response.choices[0].message.content

        print("\nAnswer:\n")
        print(answer or "The model returned an empty answer.")

    except Exception as error:
        print("\nGroq API request failed.")
        print("Error:", str(error))


# --------------------------------------------------
# 6. Interactive question-answer loop
# --------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("KG Reddy College RAG Assistant")
    print("=" * 50)
    print("Indexed chunks:", collection.count())
    print("Type 'exit' to quit.")

    while True:
        try:
            question = input(
                "\nAsk about KG Reddy: "
            ).strip()

            if question.lower() in {"exit", "quit"}:
                print("Goodbye!")
                break

            if question:
                ask_question(question)

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
