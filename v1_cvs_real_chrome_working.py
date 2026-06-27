#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CVS_BASE = "https://www.cvs.com"
PROFILE_DIR = "./cvs_chrome_profile"
OUTPUT_DIR = Path.home() / "Desktop" / "cvs_output_v1"

PRICE_RE = re.compile(r"\$\s?\d+(?:\.\d{2})?")
MAX_LOAD_MORE_CLICKS = 5


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


def visible_price_count(page) -> int:
    try:
        return page.evaluate(
            """
            () => {
                const re = /\\$\\s?\\d+(?:\\.\\d{2})?/;
                let count = 0;

                function visible(el) {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== "none" && s.visibility !== "hidden" && r.width > 2 && r.height > 2;
                }

                for (const el of document.querySelectorAll("*")) {
                    if (!visible(el)) continue;
                    const t = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
                    if (!t || t.length > 500) continue;
                    if (re.test(t)) count++;
                }

                return count;
            }
            """
        )
    except Exception:
        return 0


def wait_for_prices(page, timeout_seconds: int = 35) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        count = visible_price_count(page)
        print(f"[INFO] Visible price count: {count}")
        if count > 0:
            return True
        time.sleep(2)

    return False


def click_load_more(page, max_clicks: int = MAX_LOAD_MORE_CLICKS) -> None:
    labels = re.compile(r"load more|show more|see more|more results|view more", re.I)

    for i in range(1, max_clicks + 1):
        page.mouse.wheel(0, 2500)
        time.sleep(1.5)

        clicked = False
        buttons = page.locator("button, a, div[role='button']")

        for j in range(buttons.count()):
            try:
                btn = buttons.nth(j)
                text = clean_text(btn.inner_text(timeout=1000))

                if not text or not labels.search(text):
                    continue
                if not btn.is_visible(timeout=1000):
                    continue

                before = visible_price_count(page)
                print(f"[INFO] Load more {i}: {text}")

                btn.scroll_into_view_if_needed(timeout=5000)
                time.sleep(0.4)
                btn.click(timeout=10000)
                time.sleep(4)

                after = visible_price_count(page)
                print(f"[INFO] Price count before={before}, after={after}")

                clicked = True
                break

            except Exception:
                continue

        if not clicked:
            print("[INFO] No load-more button found.")
            break


def extract_visible_products(page, keyword: str) -> list[dict[str, str]]:
    data = page.evaluate(
        """
        () => {
            const priceRe = /\\$\\s?\\d+(?:\\.\\d{2})?/g;

            function textOf(el) {
                return (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            }

            function visible(el) {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.display !== "none" && s.visibility !== "hidden" && r.width > 2 && r.height > 2;
            }

            function cardFor(el) {
                let best = null;
                let cur = el;

                for (let depth = 0; cur && depth < 12; depth++) {
                    const text = textOf(cur);
                    const prices = text.match(priceRe) || [];
                    const links = cur.querySelectorAll ? cur.querySelectorAll("a[href]").length : 0;
                    const imgs = cur.querySelectorAll ? cur.querySelectorAll("img").length : 0;

                    if (text.length >= 20 && text.length <= 3000) {
                        let score = 0;
                        score += prices.length ? 50 : 0;
                        score += links ? 20 : 0;
                        score += imgs ? 10 : 0;
                        score += text.length < 1200 ? 10 : 0;
                        score -= depth;

                        if (!best || score > best.score) best = { el: cur, score };
                    }

                    cur = cur.parentElement;
                }

                return best ? best.el : el;
            }

            const elements = Array.from(document.querySelectorAll("h1,h2,h3,[role='heading'],a"))
                .filter(el => {
                    if (!visible(el)) return false;
                    const text = textOf(el);
                    if (!text || text.length < 3 || text.length > 220) return false;
                    if (/^\\$/.test(text)) return false;

                    const bad = ["sign in", "cart", "menu", "weekly ad", "find a store", "pharmacy", "account"];
                    return !bad.some(x => text.toLowerCase().includes(x));
                });

            const products = [];

            for (const el of elements) {
                const name = textOf(el);
                const card = cardFor(el);
                const cardText = textOf(card);
                const prices = [...new Set((cardText.match(priceRe) || []).map(p => p.replace(/\\s+/g, "")))];

                if (!prices.length) continue;

                const link = card.querySelector("a[href]");
                const img = card.querySelector("img");

                products.push({
                    product_name: name,
                    prices,
                    product_url: link ? link.href : "",
                    image_url: img ? (img.currentSrc || img.src || "") : "",
                    card_text: cardText
                });
            }

            return {
                url: location.href,
                title: document.title,
                products
            };
        }
        """
    )

    rows = []
    seen = set()

    for item in data.get("products", []):
        name = clean_text(item.get("product_name", ""))
        prices = item.get("prices", [])
        price = normalize_price(prices[0]) if prices else ""
        product_url = clean_text(item.get("product_url", ""))
        image_url = clean_text(item.get("image_url", ""))

        if not name or not price:
            continue

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
                "all_prices_found": "; ".join(dict.fromkeys([normalize_price(p) for p in prices if normalize_price(p)])),
                "product_url": urljoin(CVS_BASE, product_url) if product_url else "",
                "image_url": urljoin(CVS_BASE, image_url) if image_url else "",
                "source_url": data.get("url", ""),
                "method": "visible_dom_generic",
            }
        )

    return rows


def save_csv(rows: list[dict[str, str]], output_file: Path) -> None:
    fieldnames = [
        "retailer",
        "keyword",
        "product_name",
        "price",
        "all_prices_found",
        "product_url",
        "image_url",
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
    Path(PROFILE_DIR).mkdir(exist_ok=True)

    safe_keyword = safe_filename(keyword)
    output_csv = OUTPUT_DIR / f"cvs_{safe_keyword}_prices.csv"
    debug_json = OUTPUT_DIR / f"debug_cvs_{safe_keyword}.json"
    debug_png = OUTPUT_DIR / f"debug_cvs_{safe_keyword}.png"

    url = make_search_url(keyword)

    print(f"[INFO] Opening real Chrome profile: {Path(PROFILE_DIR).resolve()}")
    print(f"[INFO] URL: {url}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            channel="chrome",
            headless=False,
            slow_mo=120,
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)

            wait_for_prices(page, timeout_seconds=35)
            click_load_more(page, max_clicks=MAX_LOAD_MORE_CLICKS)

            rows = extract_visible_products(page, keyword)
            save_csv(rows, output_csv)

            debug_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            page.screenshot(path=str(debug_png), full_page=True)

            print(f"[DONE] Rows extracted: {len(rows)}")
            print(f"[DONE] CSV saved: {output_csv}")
            print(f"[DONE] Debug JSON: {debug_json}")
            print(f"[DONE] Screenshot: {debug_png}")

        except PlaywrightTimeoutError as e:
            print(f"[ERROR] Timeout: {e}")

        finally:
            context.close()


if __name__ == "__main__":
    main()
