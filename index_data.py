
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent

CHUNKS_FILE = ROOT / "data" / "processed" / "chunks.jsonl"
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION_NAME = "kgrcet_website"

BATCH_SIZE = 64
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main():
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(
            f"Processed chunks not found: {CHUNKS_FILE}\n"
            "Run: python process_documents.py"
        )

    records = []
    with CHUNKS_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                text = record.get("text", "").strip()
                if text:
                    records.append(record)

    if not records:
        print("No text chunks found.")
        return

    print(f"Loaded {len(records)} text chunks.")
    print(f"Loading embedding model: {EMBEDDING_MODEL}")

    model = SentenceTransformer(EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Rebuild only this project's collection so repeated runs
    # do not create duplicate records.
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    total = len(records)

    for start in range(0, total, BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]

        ids = []
        documents = []
        metadatas = []

        for position, record in enumerate(batch, start=start):
            source_id = str(
                record.get("id") or f"chunk-{position}"
            )

            ids.append(source_id)
            documents.append(record["text"])

            metadata = {
                "source": str(record.get("source", "")),
                "title": str(record.get("title", "")),
                "type": str(record.get("type", "")),
                "chunk_index": int(
                    record.get("chunk_index", position)
                )
            }
            metadatas.append(metadata)

        embeddings = model.encode(
            documents,
            normalize_embeddings=True,
            show_progress_bar=False
        ).tolist()

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )

        print(f"Indexed {min(start + len(batch), total)}/{total}")

    print("\nIndexing completed successfully.")
    print("Collection:", COLLECTION_NAME)
    print("Stored chunks:", collection.count())
    print("Database:", CHROMA_DIR)


if __name__ == "__main__":
    main()
