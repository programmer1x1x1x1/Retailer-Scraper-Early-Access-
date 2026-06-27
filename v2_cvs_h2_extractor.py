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
OUTPUT_DIR = Path.home() / "Desktop" / "cvs_output_v2"

MAX_LOAD_MORE_CLICKS = 10
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


def count_visible_prices(page) -> int:
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
                    const text = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
                    if (!text || text.length > 500) continue;
                    if (re.test(text)) count++;
                }

                return count;
            }
            """
        )
    except Exception:
        return 0


def wait_for_product_h2s(page, timeout_seconds: int = 35) -> int:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        count = page.evaluate(
            """
            () => {
                function textOf(el) {
                    return (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
                }

                function visible(el) {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== "none" && s.visibility !== "hidden" && r.width > 2 && r.height > 2;
                }

                const bad = ["shop", "categories", "sign in", "extracare", "weekly ad", "find a store", "cart", "menu"];

                return Array.from(document.querySelectorAll(
                    "h2[role='heading'], h2[aria-level='2'], [role='heading'][aria-level='2']"
                )).filter(h => {
                    const t = textOf(h);
                    if (!t || !visible(h)) return false;
                    if (t.length < 3 || t.length > 240) return false;
                    return !bad.some(x => t.toLowerCase().includes(x));
                }).length;
            }
            """
        )

        print(f"[INFO] Product h2 count: {count}")

        if count > 0:
            return count

        time.sleep(2)

    raise RuntimeError("No CVS product h2 headings appeared.")


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

                before = count_visible_prices(page)
                print(f"[INFO] Load more {i}: {text}")

                btn.scroll_into_view_if_needed(timeout=5000)
                time.sleep(0.4)
                btn.click(timeout=10000)
                time.sleep(4)

                after = count_visible_prices(page)
                print(f"[INFO] Price count before={before}, after={after}")

                clicked = True
                break

            except Exception:
                continue

        if not clicked:
            print("[INFO] No load-more button found.")
            break


def extract_h2_products(page, keyword: str) -> tuple[list[dict[str, str]], dict]:
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

            function bestCard(heading) {
                let best = null;
                let cur = heading;

                for (let depth = 0; cur && depth < 13; depth++) {
                    const text = textOf(cur);
                    const prices = text.match(priceRe) || [];
                    const links = cur.querySelectorAll ? cur.querySelectorAll("a[href]").length : 0;
                    const imgs = cur.querySelectorAll ? cur.querySelectorAll("img").length : 0;
                    const buttons = cur.querySelectorAll ? cur.querySelectorAll("button").length : 0;

                    if (text.length >= 20 && text.length <= 3500) {
                        let score = 0;
                        score += prices.length ? 60 : 0;
                        score += links ? 20 : 0;
                        score += imgs ? 10 : 0;
                        score += buttons ? 10 : 0;
                        score += text.length < 1200 ? 10 : 0;
                        score -= depth;

                        if (!best || score > best.score) best = { el: cur, score };
                    }

                    cur = cur.parentElement;
                }

                return best ? best.el : heading.parentElement;
            }

            function productUrl(card, heading) {
                let cur = heading;

                while (cur && cur !== card) {
                    if (cur.tagName === "A" && cur.href) return cur.href;
                    cur = cur.parentElement;
                }

                const links = Array.from(card.querySelectorAll("a[href]"));

                for (const a of links) {
                    const href = a.href || "";
                    if (href.includes("/shop/") || href.includes("prodid") || href.includes("skuId")) {
                        return href;
                    }
                }

                return links.length ? links[0].href : "";
            }

            function imageUrl(card) {
                const img = card.querySelector("img");
                return img ? (img.currentSrc || img.src || img.getAttribute("data-src") || "") : "";
            }

            const bad = ["shop", "categories", "sign in", "extracare", "weekly ad", "find a store", "cart", "menu"];

            const headings = Array.from(document.querySelectorAll(
                "h2[role='heading'], h2[aria-level='2'], [role='heading'][aria-level='2']"
            )).filter(h => {
                const t = textOf(h);
                if (!t || !visible(h)) return false;
                if (t.length < 3 || t.length > 240) return false;
                return !bad.some(x => t.toLowerCase().includes(x));
            });

            const products = [];

            for (const h of headings) {
                const card = bestCard(h);
                const cardText = textOf(card);
                const prices = [...new Set((cardText.match(priceRe) || []).map(p => p.replace(/\\s+/g, "")))];

                products.push({
                    product_name: textOf(h),
                    prices,
                    product_url: productUrl(card, h),
                    image_url: imageUrl(card),
                    card_text: cardText
                });
            }

            return {
                url: location.href,
                title: document.title,
                heading_count: headings.length,
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

        if not name:
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
                "method": "cvs_h2_card_extractor",
            }
        )

    return rows, data


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
    debug_json = OUTPUT_DIR / f"debug_cvs_h2_{safe_keyword}.json"
    debug_png = OUTPUT_DIR / f"debug_cvs_h2_{safe_keyword}.png"

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

            wait_for_product_h2s(page, timeout_seconds=35)
            click_load_more(page, max_clicks=MAX_LOAD_MORE_CLICKS)

            rows, debug_data = extract_h2_products(page, keyword)

            save_csv(rows, output_csv)
            debug_json.write_text(json.dumps(debug_data, indent=2), encoding="utf-8")
            page.screenshot(path=str(debug_png), full_page=True)

            print(f"[DONE] H2 products found: {debug_data.get('heading_count', 0)}")
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
