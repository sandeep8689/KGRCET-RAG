
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).parent
RAW_FILE = ROOT / "data" / "raw" / "pages.jsonl"
PDF_DIR = ROOT / "data" / "pdfs"
MANIFEST = PDF_DIR / "pdf_manifest.json"
OUTPUT = ROOT / "data" / "processed" / "chunks.jsonl"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


def split_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()

        if len(chunk) >= 50:
            chunks.append(chunk)

        if end == len(text):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records = []

    # Process collected webpage text.
    if RAW_FILE.exists():
        with RAW_FILE.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, 1):
                try:
                    page = json.loads(line)
                except json.JSONDecodeError:
                    print(f"Invalid JSON at line {line_number}")
                    continue

                text = page.get("text", "")
                url = page.get("url", "")

                for index, chunk in enumerate(split_text(text)):
                    records.append({
                        "id": f"web_{len(records)}",
                        "source": url,
                        "title": page.get("title", ""),
                        "type": "webpage",
                        "chunk_index": index,
                        "text": chunk
                    })

    # Process PDFs listed in the manifest.
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        for url, info in manifest.items():
            filename = info.get("filename", "")
            pdf_path = PDF_DIR / filename

            if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
                continue

            try:
                reader = PdfReader(str(pdf_path))

                for page_number, pdf_page in enumerate(reader.pages, 1):
                    text = pdf_page.extract_text() or ""

                    for index, chunk in enumerate(split_text(text)):
                        records.append({
                            "id": f"pdf_{len(records)}",
                            "source": url,
                            "title": pdf_path.stem,
                            "type": "pdf",
                            "page": page_number,
                            "chunk_index": index,
                            "text": chunk
                        })

            except Exception as error:
                print(f"PDF extraction failed: {filename}: {error}")

    # Replace the output with the current processed dataset.
    with OUTPUT.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("Webpage and PDF processing completed.")
    print("Total text chunks:", len(records))
    print("Output:", OUTPUT)


if __name__ == "__main__":
    main()
