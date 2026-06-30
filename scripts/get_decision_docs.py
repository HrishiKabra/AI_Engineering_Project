"""Scrape FIA Formula 1 decision documents for a given season + Grand Prix.

Writes PDFs into ``<out>/<season>_<slug>/`` (e.g. ``data/decision_docs/2025_qatar``),
matching the corpus layout the ingester expects. Existing files are skipped, so it
is safe to re-run after a race to pull only newly published documents.

Runs in the official Playwright image (browsers preinstalled); downloads use only
the standard library, so no extra pip installs are needed:

    python scripts/get_decision_docs.py --season 2025 --gp qatar --out data/decision_docs
    python scripts/get_decision_docs.py --gp all          # whole season

For seasons other than 2025, pass the FIA documents page URL explicitly:
    --page-url https://www.fia.com/documents/championships/.../season/season-2024-XXXX
"""

from __future__ import annotations

import argparse
import asyncio
import time
import unicodedata
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

BASE_URL = "https://www.fia.com"
DEFAULT_PAGE_URL = (
    "https://www.fia.com/documents/championships/"
    "fia-formula-one-world-championship-14/season/season-2025-2071"
)
DELAY_BETWEEN_DOWNLOADS = 1.5
_UA = "Mozilla/5.0 (compatible; f1-rule-interpreter/2.0; +https://github.com)"


def slugify(gp_text: str) -> str:
    """'Las Vegas Grand Prix' -> 'lasvegas'; 'São Paulo Grand Prix' -> 'saopaulo'.

    Matches the existing ``<season>_<slug>`` folder convention (accent-stripped,
    lowercase, no spaces, 'grand prix' removed)."""
    text = unicodedata.normalize("NFKD", gp_text).encode("ascii", "ignore").decode()
    text = text.lower().replace("grand prix", "")
    return "".join(ch for ch in text if ch.isalnum())


async def _collect_pdf_links(page) -> list[dict]:
    header = await page.query_selector(".decision-document-list h2, .decision-document-list h3")
    if header:
        await header.scroll_into_view_if_needed()
        await header.click()
        await asyncio.sleep(1)

    last_height = 0
    while True:  # lazy-loaded list: scroll until the page stops growing
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(0.3)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    links = await page.eval_on_selector_all(
        "a", "els => els.map(el => ({ href: el.href, text: el.textContent.trim() }))"
    )
    seen, unique = set(), []
    for link in links:
        if ".pdf" in link["href"].lower() and link["href"] not in seen:
            seen.add(link["href"])
            unique.append(link)
    return unique


async def _resolve_season_url(page, season: int) -> str | None:
    """Find the documents URL for a season from the season dropdown."""
    opts = await page.eval_on_selector_all(
        "#facetapi_select_facet_form_3 option",
        "els => els.map(o => ({ v: o.value, t: o.textContent.trim() }))",
    )
    for o in opts:
        if o["t"].strip().lower() == f"season {season}":
            return o["v"] if o["v"].startswith("http") else urljoin(BASE_URL, o["v"])
    return None


async def _scrape(season: int, gp_filter: str, page_url: str | None = None) -> dict[str, list[dict]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        start = page_url or DEFAULT_PAGE_URL
        print(f"Loading {start} ...")
        await page.goto(start, wait_until="networkidle", timeout=60000)

        # Auto-resolve the requested season from the dropdown (unless an explicit URL given).
        if not page_url and f"season-{season}-" not in start:
            season_url = await _resolve_season_url(page, season)
            if not season_url:
                print(f"Could not find SEASON {season} in the FIA dropdown.")
                await browser.close()
                return {}
            print(f"Season {season} -> {season_url}")
            await page.goto(season_url, wait_until="networkidle", timeout=60000)

        options = await page.eval_on_selector_all(
            "#facetapi_select_facet_form_2 option",
            "els => els.map(el => ({ value: el.value, text: el.textContent.trim() }))",
        )
        gps = [
            o for o in options
            if o["value"] and o["value"] != "0" and "grand prix" in o["text"].lower()
        ]
        print(f"Found {len(gps)} Grand Prix in the season.")

        if gp_filter == "all":
            chosen = gps
        else:
            chosen = [o for o in gps if slugify(o["text"]) == gp_filter]
            if not chosen:  # fall back to substring match for convenience
                chosen = [o for o in gps if gp_filter in slugify(o["text"])]

        if not chosen:
            print(f"No Grand Prix matched '{gp_filter}'. Available slugs:")
            for o in gps:
                print(f"  {slugify(o['text'])}  ({o['text']})")
            await browser.close()
            return {}

        result: dict[str, list[dict]] = {}
        for gp in chosen:
            url = gp["value"]
            if not url.startswith("http"):
                url = urljoin(BASE_URL, url)
            print(f"\n{gp['text']} -> {slugify(gp['text'])}")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(1)
            links = await _collect_pdf_links(page)
            print(f"  {len(links)} PDFs")
            result[gp["text"]] = links

        await browser.close()
        return result


def _download(links: list[dict], folder: Path, delay: float) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, link in enumerate(links, 1):
        url = link["href"]
        if not url.startswith("http"):
            url = urljoin(BASE_URL, url)
        name = (link["text"].strip().replace("/", "-").replace("\\", "-")) or f"document_{i}"
        name = "".join(c for c in name if c.isalnum() or c in " ._-")[:100]
        dest = folder / f"{i:03d}_{name}.pdf"
        if dest.exists():
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                dest.write_bytes(resp.read())
            print(f"  saved {dest.name}")
            n += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {url}: {e}")
        time.sleep(delay)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--gp", required=True, help="GP slug (e.g. qatar, saopaulo) or 'all'")
    ap.add_argument("--out", type=Path, default=Path("data/decision_docs"))
    ap.add_argument("--page-url", default=None, help="FIA documents page URL (required for non-2025)")
    ap.add_argument("--delay", type=float, default=DELAY_BETWEEN_DOWNLOADS)
    args = ap.parse_args()

    gp_filter = args.gp.strip().lower()
    by_gp = asyncio.run(_scrape(args.season, gp_filter, page_url=args.page_url))

    total = 0
    for gp_text, links in by_gp.items():
        folder = args.out / f"{args.season}_{slugify(gp_text)}"
        total += _download(links, folder, args.delay)
    print(f"\nDone. {total} new PDF(s) downloaded under {args.out}/")


if __name__ == "__main__":
    main()
