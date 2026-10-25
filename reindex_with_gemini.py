
import os
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

CHROMA_PATH = ROOT / "chroma_db"
SOURCE = "kgrcet_website"
TARGET = "kgrcet_website_gemini"
MODEL = "gemini-embedding-001"
DIMENSIONS = 768
BATCH_SIZE = 5


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing from the root .env file.")

    db = chromadb.PersistentClient(path=str(CHROMA_PATH))
    source = db.get_collection(SOURCE)

    names = [c.name for c in db.list_collections()]
    if TARGET in names:
        target = db.get_collection(TARGET)
        print(f"Resuming existing target: {target.count()} chunks.")
    else:
        target = db.create_collection(
            name=TARGET,
            metadata={"hnsw:space": "cosine"},
        )

    gemini = genai.Client(api_key=api_key)
    total = source.count()
    existing_ids = set()

    # Collect IDs already present in the target.
    offset = 0
    while offset < target.count():
        page = target.get(
            limit=500,
            offset=offset,
            include=[],
        )
        existing_ids.update(page["ids"])
        offset += len(page["ids"])

    print(f"Source chunks: {total}")
    print(f"Already indexed: {len(existing_ids)}")

    offset = 0
    while offset < total:
        page = source.get(
            limit=100,
            offset=offset,
            include=["documents", "metadatas"],
        )
        offset += len(page["ids"])

        pending = [
            (doc_id, doc, meta)
            for doc_id, doc, meta in zip(
                page["ids"], page["documents"], page["metadatas"]
            )
            if doc_id not in existing_ids and doc
        ]

        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            if not batch:
                continue

            docs = [item[1] for item in batch]
            result = gemini.models.embed_content(
                model=MODEL,
                contents=docs,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=DIMENSIONS,
                ),
            )

            vectors = [
                [float(value) for value in item.values]
                for item in (result.embeddings or [])
            ]
            if len(vectors) != len(batch):
                raise RuntimeError("Gemini returned an unexpected number of embeddings.")

            target.add(
                ids=[item[0] for item in batch],
                documents=docs,
                metadatas=[item[2] or {} for item in batch],
                embeddings=vectors,
            )
            existing_ids.update(item[0] for item in batch)

            print(f"Indexed {len(existing_ids)}/{total}")
            time.sleep(2)

    final_count = target.count()
    if final_count != total:
        raise RuntimeError(
            f"Count mismatch: target={final_count}, source={total}. "
            "You can rerun this script to resume."
        )

    print(f"SUCCESS: {TARGET} contains {final_count} chunks.")
    print("Original collection remains unchanged.")


if __name__ == "__main__":
    main()
