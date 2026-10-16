
import asyncio
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright

# --------------------------------------------------
# PATHS AND SETTINGS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / "data" / "url_inventory.json"
RAW_DIR = ROOT / "data" / "raw"
PDF_DIR = ROOT / "data" / "pdfs"

PAGES_FILE = RAW_DIR / "pages.jsonl"
PDF_MANIFEST = PDF_DIR / "pdf_manifest.json"
REPORT_FILE = RAW_DIR / "crawl_report.json"

BASE_DOMAIN = "kgr.ac.in"
CURRENT_ACADEMIC_YEAR = "2026-27"
MAX_PAGES = 508
TIMEOUT = 45000
SAVE_EVERY = 10

RAW_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

# Exclude examination-related content.
EXCLUDED_KEYWORDS = (
    "examination",
    "exam-timetable",
    "exam-timetables",
    "exam-notification",
    "exam-notifications",
    "examination-timetable",
    "examination-timetables",
    "examination-notification",
    "examination-notifications",
)

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def is_official_url(url):
    host = (urlparse(url).hostname or "").lower()
    return (
        host == BASE_DOMAIN
        or host.endswith("." + BASE_DOMAIN)
    )


def normalized_url_text(url):
    return unquote(url).lower().replace("_", "-")


def is_excluded_url(url):
    value = normalized_url_text(url)
    return any(keyword in value for keyword in EXCLUDED_KEYWORDS)


def is_pdf_url(url):
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def is_current_pdf(url):
    value = normalized_url_text(url)
    return (
        is_pdf_url(url)
        and CURRENT_ACADEMIC_YEAR in value
        and not is_excluded_url(url)
    )


def safe_filename(url):
    name = unquote(Path(urlparse(url).path).name)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

    if not name.lower().endswith(".pdf"):
        name = "document.pdf"

    short_hash = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()[:12]

    return f"{short_hash}_{name}"


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Warning: Could not read {path}; using empty data.")
        return default


def load_inventory():
    data = load_json(INVENTORY, [])

    if isinstance(data, dict):
        data = data.get("urls", [])

    urls = []

    for item in data:
        url = item.get("url") if isinstance(item, dict) else item

        if not url or not isinstance(url, str):
            continue

        if not is_official_url(url):
            continue

        if is_excluded_url(url):
            continue

        # Don't crawl PDFs as HTML pages.
        if is_pdf_url(url):
            continue

        urls.append(url)

    return list(dict.fromkeys(urls))


def load_existing_pages():
    pages = {}

    if not PAGES_FILE.exists():
        return pages

    with PAGES_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                item = json.loads(line)
                url = item.get("url")

                if url and not is_excluded_url(url):
                    pages[url] = item

            except json.JSONDecodeError:
                continue

    return pages


def save_pages(pages):
    # Rewrite the JSONL file from the current URL-keyed records.
    with PAGES_FILE.open("w", encoding="utf-8") as file:
        for item in pages.values():
            file.write(
                json.dumps(item, ensure_ascii=False) + "\n"
            )


def save_manifest(pdfs):
    PDF_MANIFEST.write_text(
        json.dumps(pdfs, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def save_report(report):
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# --------------------------------------------------
# MAIN COLLECTION
# --------------------------------------------------

async def main():
    if not INVENTORY.exists():
        print(f"Missing inventory file: {INVENTORY}")
        return

    urls = load_inventory()[:MAX_PAGES]

    print("Official HTML URLs queued:", len(urls))
    print("Academic year filter:", CURRENT_ACADEMIC_YEAR)
    print("Examination content: excluded")

    saved_pages = load_existing_pages()
    pdfs = load_json(PDF_MANIFEST, {})

    report = {
        "started_at": datetime.now().isoformat(),
        "academic_year_filter": CURRENT_ACADEMIC_YEAR,
        "examination_content_excluded": True,
        "successful": [],
        "failed": [],
        "skipped": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            accept_downloads=False
        )
        page = await context.new_page()

        async def download_pdf(url):
            if not is_official_url(url):
                return

            if is_excluded_url(url) or not is_current_pdf(url):
                return

            existing_record = pdfs.get(url, {})
            existing_file = PDF_DIR / existing_record.get(
                "filename", ""
            )

            if existing_file.is_file() and existing_file.stat().st_size > 0:
                return

            filename = safe_filename(url)
            destination = PDF_DIR / filename

            try:
                response = await context.request.get(
                    url, timeout=TIMEOUT
                )

                if not response.ok:
                    report["failed"].append({
                        "url": url,
                        "reason": f"PDF HTTP {response.status}"
                    })
                    return

                content_type = response.headers.get(
                    "content-type", ""
                ).lower()

                body = await response.body()

                # Verify that the response is actually a PDF.
                if (
                    not body.startswith(b"%PDF")
                    and "pdf" not in content_type
                ):
                    report["failed"].append({
                        "url": url,
                        "reason": "Response was not a recognizable PDF"
                    })
                    return

                destination.write_bytes(body)

                pdfs[url] = {
                    "filename": filename,
                    "downloaded_at": datetime.now().isoformat(),
                    "bytes": len(body),
                    "academic_year": CURRENT_ACADEMIC_YEAR
                }

                print("PDF saved:", filename)

            except Exception as exc:
                report["failed"].append({
                    "url": url,
                    "reason": f"PDF download failed: {exc}"
                })

        try:
            for number, url in enumerate(urls, start=1):
                print(f"[{number}/{len(urls)}] {url}")

                if is_excluded_url(url):
                    report["skipped"].append({
                        "url": url,
                        "reason": "Examination-related URL"
                    })
                    continue

                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=TIMEOUT
                    )

                    status = response.status if response else None

                    if status in (401, 403, 406, 429):
                        report["skipped"].append({
                            "url": url,
                            "status": status,
                            "reason": "Restricted or rate-limited"
                        })
                        continue

                    if status is None or status >= 400:
                        report["failed"].append({
                            "url": url,
                            "status": status,
                            "reason": "Page request failed"
                        })
                        continue

                    content_type = (
                        response.headers.get("content-type", "")
                        if response else ""
                    ).lower()

                    if "pdf" in content_type:
                        await download_pdf(url)
                        continue

                    title = await page.title()
                    text = await page.locator("body").inner_text(
                        timeout=15000
                    )

                    if len(text.strip()) < 30:
                        report["skipped"].append({
                            "url": url,
                            "reason": "Insufficient visible text"
                        })
                        continue

                    # Save text without keeping navigation links as records.
                    saved_pages[url] = {
                        "url": url,
                        "title": title,
                        "text": text,
                        "type": "html",
                        "collected_at": datetime.now().isoformat()
                    }

                    report["successful"].append({
                        "url": url,
                        "characters": len(text)
                    })

                    # Discover only current-year PDF links.
                    links = await page.locator("a[href]").evaluate_all("""
                        elements => elements.map(a => ({
                            href: a.href,
                            text: (a.innerText || '').trim()
                        }))
                    """)

                    for link in links:
                        pdf_url = link["href"].split("#")[0]

                        if is_current_pdf(pdf_url):
                            await download_pdf(pdf_url)

                except Exception as exc:
                    report["failed"].append({
                        "url": url,
                        "reason": str(exc)
                    })

                # Persist progress regularly.
                if number % SAVE_EVERY == 0:
                    save_pages(saved_pages)
                    save_manifest(pdfs)
                    save_report(report)

                    print(
                        f"Progress saved: {number}/{len(urls)}"
                    )

        finally:
            save_pages(saved_pages)
            save_manifest(pdfs)
            report["finished_at"] = datetime.now().isoformat()
            save_report(report)
            await context.close()
            await browser.close()

    print("\nCollection finished.")
    print("Saved webpage records:", len(saved_pages))
    print("Current-year PDF records:", len(pdfs))
    print("Successful URLs:", len(report["successful"]))
    print("Failed URLs:", len(report["failed"]))
    print("Skipped URLs:", len(report["skipped"]))
    print("Report:", REPORT_FILE)


if __name__ == "__main__":
    asyncio.run(main())
