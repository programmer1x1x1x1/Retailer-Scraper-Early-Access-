#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CVS_BASE = "https://www.cvs.com"
OUTPUT_DIR = Path.home() / "Desktop" / "cvs_output_v0"

PRICE_RE = re.compile(r"\$\s?\d+(?:\.\d{2})?")


def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def safe_filename(text: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return safe or "keyword"


def normalize_price(value) -> str:
    text = clean_text(value)
    match = PRICE_RE.search(text)
    return match.group(0).replace(" ", "") if match else ""


def make_search_url(keyword: str) -> str:
    return f"https://www.cvs.com/search?searchTerm={quote_plus(keyword)}"


def extract_products_bs4(html: str, keyword: str, source_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    seen = set()

    cards = soup.select(
        """
        [data-testid*='product'],
        [class*='product'],
        [class*='Product'],
        article,
        li,
        div
        """
    )

    for card in cards:
        text = clean_text(card.get_text(" ", strip=True))
        if not text:
            continue

        price = normalize_price(text)
        if not price:
            continue

        name = ""

        for selector in [
            "[data-testid*='product-name']",
            "[class*='product-name']",
            "[class*='ProductName']",
            "h1",
            "h2",
            "h3",
            "a",
        ]:
            el = card.select_one(selector)
            if not el:
                continue

            candidate = clean_text(el.get_text(" ", strip=True))
            if candidate and "$" not in candidate and len(candidate) > 3:
                name = candidate
                break

        if not name:
            name = clean_text(text.replace(price, ""))[:180]

        product_url = ""
        link = card.select_one("a[href]")
        if link:
            product_url = urljoin(CVS_BASE, link.get("href", ""))

        key = (name.lower(), price, product_url)
        if key in seen:
            continue
        seen.add(key)

        rows.append(
            {
                "retailer": "CVS",
                "keyword": keyword,
                "product_name": name,
                "price": price,
                "product_url": product_url,
                "source_url": source_url,
                "method": "bs4_card_parser",
            }
        )

    return rows


def save_csv(rows: list[dict[str, str]], output_file: Path) -> None:
    fieldnames = [
        "retailer",
        "keyword",
        "product_name",
        "price",
        "product_url",
        "source_url",
        "method",
    ]

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def main() -> None:
    keyword = input("Enter CVS keyword: ").strip()
    if not keyword:
        print("[ERROR] Keyword cannot be empty.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    safe_keyword = safe_filename(keyword)
    output_csv = OUTPUT_DIR / f"cvs_{safe_keyword}_prices.csv"
    debug_html = OUTPUT_DIR / f"debug_cvs_{safe_keyword}.html"
    debug_png = OUTPUT_DIR / f"debug_cvs_{safe_keyword}.png"

    url = make_search_url(keyword)

    print(f"[INFO] Opening: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=150)
        context = browser.new_context(
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)

            for _ in range(5):
                page.mouse.wheel(0, 1200)
                time.sleep(1)

            html = page.content()
            debug_html.write_text(html, encoding="utf-8")
            page.screenshot(path=str(debug_png), full_page=True)

            rows = extract_products_bs4(html, keyword, page.url)
            save_csv(rows, output_csv)

            print(f"[DONE] Rows extracted: {len(rows)}")
            print(f"[DONE] CSV saved: {output_csv}")
            print(f"[DONE] Debug HTML: {debug_html}")
            print(f"[DONE] Debug screenshot: {debug_png}")

        except PlaywrightTimeoutError as e:
            print(f"[ERROR] Timeout: {e}")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
