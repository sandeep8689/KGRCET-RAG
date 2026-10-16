
import asyncio
from playwright.async_api import async_playwright

URL = "https://kgr.ac.in/academic-calenders/"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        try:
            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=45000
            )

            print("HTTP status:", response.status if response else None)
            print("Title:", await page.title())

            links = await page.locator("a[href]").evaluate_all("""
                elements => elements.map(a => ({
                    text: (a.innerText || "").trim(),
                    href: a.href
                })).filter(a =>
                    /2026-27|2025-26|2024-25/i.test(a.text)
                )
            """)

            print("\nAcademic-year links:", len(links))

            for link in links:
                print(link["text"], "->", link["href"])

            pdfs = await page.locator("a[href]").evaluate_all("""
                elements => elements.map(a => ({
                    text: (a.innerText || "").trim(),
                    href: a.href
                })).filter(a =>
                    a.href.toLowerCase().includes(".pdf")
                )
            """)

            print("\nPDF links:", len(pdfs))

            for pdf in pdfs:
                print(pdf["text"], "->", pdf["href"])

        except Exception as error:
            print("Test failed:", repr(error))

        finally:
            await browser.close()

asyncio.run(main())
