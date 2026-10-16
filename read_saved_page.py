
from pathlib import Path
from bs4 import BeautifulSoup
import json

ROOT = Path(__file__).parent
HTML_FILE = ROOT / "data" / "raw" / "academic_calendars.html"
OUTPUT_FILE = ROOT / "data" / "raw" / "saved_pages.json"

if not HTML_FILE.exists():
    print("File not found:", HTML_FILE)
    raise SystemExit(1)

html = HTML_FILE.read_text(encoding="utf-8", errors="replace")
soup = BeautifulSoup(html, "html.parser")

for tag in soup(["script", "style", "noscript"]):
    tag.decompose()

title = soup.title.get_text(" ", strip=True) if soup.title else ""
text = soup.get_text("\n", strip=True)

record = {
    "title": title,
    "source_url": "https://kgr.ac.in/academic-calenders/",
    "text": text,
    "collection_method": "browser_saved_html"
}

OUTPUT_FILE.write_text(
    json.dumps([record], ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("Title:", title)
print("Extracted characters:", len(text))
print("Saved to:", OUTPUT_FILE)
print("\nPreview:\n", text[:1000])
