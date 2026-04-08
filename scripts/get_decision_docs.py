import asyncio
import os
import httpx
from playwright.async_api import async_playwright
from urllib.parse import urljoin

BASE_URL = "https://www.fia.com"
PAGE_URL = "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2025-2071"
OUTPUT_DIR = "fia_f1_2025_pdfs"

DELAY_BETWEEN_DOWNLOADS = 1.5

# ── Set which Grand Prix to download ──────────────────────────────────────────
GRAND_PRIX_FILTER = "ALL"   # or "ALL"
# ──────────────────────────────────────────────────────────────────────────────

async def get_pdfs_for_current_page(page):
    header = await page.query_selector(".decision-document-list h2, .decision-document-list h3")
    if header:
        await header.scroll_into_view_if_needed()
        await header.click()
        await asyncio.sleep(1)

    last_height = 0
    while True:
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(0.3)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    all_links = await page.eval_on_selector_all(
        "a",
        "els => els.map(el => ({ href: el.href, text: el.textContent.trim() }))"
    )
    return [l for l in all_links if ".pdf" in l["href"].lower()]


async def scrape_and_download():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Loading page...")
        await page.goto(PAGE_URL, wait_until="networkidle", timeout=60000)

        gp_options = await page.eval_on_selector_all(
            "#facetapi_select_facet_form_2 option",
            "els => els.map(el => ({ value: el.value, text: el.textContent.trim() }))"
        )
        gp_options = [o for o in gp_options if o["value"] and o["value"] != "0" and "grand prix" in o["text"].lower()]

        print(f"Found {len(gp_options)} GP options:")
        for o in gp_options:
            print(f"  - {o['text']}")

        if GRAND_PRIX_FILTER == "ALL":
            to_process = gp_options
        else:
            to_process = [o for o in gp_options if GRAND_PRIX_FILTER.lower() in o["text"].lower()]

        if not to_process:
            print(f"\nNo match for '{GRAND_PRIX_FILTER}'. Check the names above.")
            await browser.close()
            return

        # Store links grouped by GP name
        gp_pdf_map = {}

        for gp in to_process:
            print(f"\nNavigating to: {gp['text']}...")
            url = gp["value"]
            if not url.startswith("http"):
                url = urljoin(BASE_URL, url)

            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(1)

            links = await get_pdfs_for_current_page(page)
            print(f"  Found {len(links)} PDFs")

            # Deduplicate within this GP
            seen = set()
            unique = []
            for l in links:
                if l["href"] not in seen:
                    seen.add(l["href"])
                    unique.append(l)

            gp_pdf_map[gp["text"]] = unique

        await browser.close()

    # Download into per-GP subfolders
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        for gp_name, pdf_links in gp_pdf_map.items():
            # e.g. "fia_f1_2025_pdfs/Qatar Grand Prix/"
            gp_folder = os.path.join(OUTPUT_DIR, gp_name)
            os.makedirs(gp_folder, exist_ok=True)
            print(f"\n── {gp_name} ({len(pdf_links)} PDFs) ──")

            for i, link in enumerate(pdf_links):
                url = link["href"]
                if not url.startswith("http"):
                    url = urljoin(BASE_URL, url)

                name = link["text"].strip().replace("/", "-").replace("\\", "-") or f"document_{i+1}"
                name = "".join(c for c in name if c.isalnum() or c in " ._-")[:100]
                filename = os.path.join(gp_folder, f"{i+1:03d}_{name}.pdf")

                if os.path.exists(filename):
                    print(f"  [skip] {filename}")
                    continue

                try:
                    print(f"  Downloading ({i+1}/{len(pdf_links)}): {name[:60]}...")
                    r = await client.get(url)
                    r.raise_for_status()
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    print(f"    Saved → {filename}")
                except Exception as e:
                    print(f"    ERROR: {e}")

                await asyncio.sleep(DELAY_BETWEEN_DOWNLOADS)

    print(f"\nDone! PDFs saved to ./{OUTPUT_DIR}/")

asyncio.run(scrape_and_download())