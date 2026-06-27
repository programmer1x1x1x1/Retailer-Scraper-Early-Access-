#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


OUTPUT_DIR = Path.home() / "Desktop" / "retailer_championship_output"
PROFILE_DIR = "./retailer_championship_profile"

PRICE_RE = re.compile(r"\$\s?\d+(?:,\d{3})*(?:\.\d{2})?")

DEFAULT_LOAD_MORE = 2
DELAY_BETWEEN_RETAILERS = 4


RETAILERS = [
    {
        "name": "CVS",
        "group": "pharmacy",
        "base_url": "https://www.cvs.com",
        "search_url": "https://www.cvs.com/search?searchTerm={query_plus}",
        "max_load_more": 3,
    },
    {
        "name": "Walgreens",
        "group": "pharmacy",
        "base_url": "https://www.walgreens.com",
        "search_url": "https://www.walgreens.com/search/results.jsp?Ntt={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "RiteAid",
        "group": "pharmacy",
        "base_url": "https://www.riteaid.com",
        "search_url": "https://www.riteaid.com/shop/catalogsearch/result/?q={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Walmart",
        "group": "bigbox",
        "base_url": "https://www.walmart.com",
        "search_url": "https://www.walmart.com/search?q={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Target",
        "group": "bigbox",
        "base_url": "https://www.target.com",
        "search_url": "https://www.target.com/s?searchTerm={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Best Buy",
        "group": "electronics",
        "base_url": "https://www.bestbuy.com",
        "search_url": "https://www.bestbuy.com/site/searchpage.jsp?id=pcat17071&st={query_plus}",
        "max_load_more": 1,
    },
    {
        "name": "Macys",
        "group": "clothing",
        "base_url": "https://www.macys.com",
        "search_url": "https://www.macys.com/shop/featured/{query_dash}",
        "max_load_more": 0,
    },
    {
        "name": "Kohls",
        "group": "clothing",
        "base_url": "https://www.kohls.com",
        "search_url": "https://www.kohls.com/search.jsp?search={query_plus}",
        "max_load_more": 0,
    },
    {
        "name": "Old Navy",
        "group": "clothing",
        "base_url": "https://oldnavy.gap.com",
        "search_url": "https://oldnavy.gap.com/browse/search.do?searchText={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Gap",
        "group": "clothing",
        "base_url": "https://www.gap.com",
        "search_url": "https://www.gap.com/browse/search.do?searchText={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Banana Republic",
        "group": "clothing",
        "base_url": "https://bananarepublic.gap.com",
        "search_url": "https://bananarepublic.gap.com/browse/search.do?searchText={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "HM",
        "group": "clothing",
        "base_url": "https://www2.hm.com",
        "search_url": "https://www2.hm.com/en_us/search-results.html?q={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Uniqlo",
        "group": "clothing",
        "base_url": "https://www.uniqlo.com",
        "search_url": "https://www.uniqlo.com/us/en/search?q={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "JCPenney",
        "group": "clothing",
        "base_url": "https://www.jcpenney.com",
        "search_url": "https://www.jcpenney.com/s?searchTerm={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Nordstrom",
        "group": "clothing",
        "base_url": "https://www.nordstrom.com",
        "search_url": "https://www.nordstrom.com/sr?origin=keywordsearch&keyword={query_plus}",
        "max_load_more": 1,
    },
    {
        "name": "Nordstrom Rack",
        "group": "clothing",
        "base_url": "https://www.nordstromrack.com",
        "search_url": "https://www.nordstromrack.com/sr?origin=keywordsearch&keyword={query_plus}",
        "max_load_more": 1,
    },
    {
        "name": "DSW",
        "group": "clothing",
        "base_url": "https://www.dsw.com",
        "search_url": "https://www.dsw.com/browse?Ntt={query_plus}",
        "max_load_more": 2,
    },
    {
        "name": "Foot Locker",
        "group": "clothing",
        "base_url": "https://www.footlocker.com",
        "search_url": "https://www.footlocker.com/search?query={query_plus}",
        "max_load_more": 1,
    },
    {
        "name": "American Eagle",
        "group": "clothing",
        "base_url": "https://www.ae.com",
        "search_url": "https://www.ae.com/us/en/s/{query_plus}",
        "max_load_more": 1,
    },
]


def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def safe_filename(text: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return safe or "file"


def normalize_price(value) -> str:
    text = clean_text(value)
    match = PRICE_RE.search(text)
    return match.group(0).replace(" ", "") if match else ""


def format_url(retailer: dict, keyword: str) -> str:
    query_plus = quote_plus(keyword)
    query_encoded = quote(keyword)
    query_dash = re.sub(r"[^a-zA-Z0-9]+", "-", keyword).strip("-").lower()

    return retailer["search_url"].format(
        query_plus=query_plus,
        query_encoded=query_encoded,
        query_dash=query_dash,
    )


def ask_retry() -> bool:
    while True:
        ans = input("Retry? y/n: ").strip().lower()

        if ans in {"y", "yes"}:
            return True

        if ans in {"n", "no"}:
            return False

        print("Please type y or n.")


def count_visible_prices(page) -> int:
    try:
        return page.evaluate(
            """
            () => {
                const re = /\\$\\s?\\d+(?:,\\d{3})*(?:\\.\\d{2})?/;
                let count = 0;

                function visible(el) {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();

                    return (
                        s.display !== "none" &&
                        s.visibility !== "hidden" &&
                        r.width > 2 &&
                        r.height > 2
                    );
                }

                for (const el of document.querySelectorAll("*")) {
                    if (!visible(el)) continue;

                    const t = (el.innerText || el.textContent || "")
                        .replace(/\\s+/g, " ")
                        .trim();

                    if (!t || t.length > 500) continue;

                    if (re.test(t)) count++;
                }

                return count;
            }
            """
        )
    except Exception:
        return 0


def visible_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def blocked_check(title: str, text: str, price_count: int) -> bool:
    # Prices visible means the page is usable enough to parse.
    if price_count > 0:
        return False

    combined = f"{clean_text(title).lower()}\n{clean_text(text).lower()[:5000]}"

    patterns = [
        "access denied",
        "you don't have permission",
        "request blocked",
        "verify you are human",
        "press and hold",
        "captcha",
        "are you a robot",
        "unusual traffic",
        "pardon the interruption",
    ]

    return any(p in combined for p in patterns)


def wait_for_products_or_prices(page, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            result = page.evaluate(
                """
                () => {
                    const priceRe = /\\$\\s?\\d+(?:,\\d{3})*(?:\\.\\d{2})?/;

                    function textOf(el) {
                        return (el.innerText || el.textContent || "")
                            .replace(/\\s+/g, " ")
                            .trim();
                    }

                    function visible(el) {
                        const s = getComputedStyle(el);
                        const r = el.getBoundingClientRect();

                        return (
                            s.display !== "none" &&
                            s.visibility !== "hidden" &&
                            r.width > 2 &&
                            r.height > 2
                        );
                    }

                    const bad = [
                        "sign in",
                        "account",
                        "cart",
                        "menu",
                        "customer service",
                        "privacy policy",
                        "terms of use"
                    ];

                    const headings = Array.from(
                        document.querySelectorAll("h1,h2,h3,[role='heading'],a")
                    ).filter(el => {
                        if (!visible(el)) return false;

                        const t = textOf(el);

                        if (!t || t.length < 3 || t.length > 240) return false;
                        if (/^\\$/.test(t)) return false;

                        return !bad.some(x => t.toLowerCase().includes(x));
                    });

                    let priceCount = 0;

                    for (const el of document.querySelectorAll("*")) {
                        if (!visible(el)) continue;

                        const t = textOf(el);

                        if (!t || t.length > 500) continue;

                        if (priceRe.test(t)) priceCount++;
                    }

                    return {
                        headingCount: headings.length,
                        priceCount
                    };
                }
                """
            )

            heading_count = result.get("headingCount", 0)
            price_count = result.get("priceCount", 0)

            print(
                f"[INFO] Product heading count: {heading_count}; "
                f"visible price count: {price_count}"
            )

            if heading_count > 0 or price_count > 0:
                return True

        except Exception:
            pass

        time.sleep(2)

    return False


def click_load_more(page, max_clicks: int) -> None:
    if max_clicks <= 0:
        print("[INFO] Load-more skipped for this retailer.")
        return

    labels = re.compile(
        r"load more|show more|see more|more results|view more|show all",
        re.I,
    )

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


def extract_products(page, keyword: str, retailer: dict) -> tuple[list[dict[str, str]], dict]:
    data = page.evaluate(
        """
        () => {
            const priceRe = /\\$\\s?\\d+(?:,\\d{3})*(?:\\.\\d{2})?/g;

            function textOf(el) {
                return (el.innerText || el.textContent || "")
                    .replace(/\\s+/g, " ")
                    .trim();
            }

            function visible(el) {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();

                return (
                    s.display !== "none" &&
                    s.visibility !== "hidden" &&
                    r.width > 2 &&
                    r.height > 2
                );
            }

            function bestCard(el) {
                let best = null;
                let cur = el;

                for (let depth = 0; cur && depth < 14; depth++) {
                    const text = textOf(cur);
                    const prices = text.match(priceRe) || [];

                    const links = cur.querySelectorAll
                        ? cur.querySelectorAll("a[href]").length
                        : 0;

                    const imgs = cur.querySelectorAll
                        ? cur.querySelectorAll("img").length
                        : 0;

                    const buttons = cur.querySelectorAll
                        ? cur.querySelectorAll("button").length
                        : 0;

                    if (text.length >= 20 && text.length <= 4500) {
                        let score = 0;

                        score += prices.length ? 60 : 0;
                        score += links ? 20 : 0;
                        score += imgs ? 10 : 0;
                        score += buttons ? 10 : 0;
                        score += text.length < 1500 ? 10 : 0;
                        score -= depth;

                        if (!best || score > best.score) {
                            best = {
                                el: cur,
                                score
                            };
                        }
                    }

                    cur = cur.parentElement;
                }

                return best ? best.el : el;
            }

            function getUrl(card, el) {
                let cur = el;

                while (cur && cur !== card) {
                    if (cur.tagName === "A" && cur.href) {
                        return cur.href;
                    }

                    cur = cur.parentElement;
                }

                const links = Array.from(card.querySelectorAll("a[href]"));

                for (const a of links) {
                    const href = a.href || "";
                    const text = textOf(a).toLowerCase();

                    if (
                        href.includes("/shop/") ||
                        href.includes("/p/") ||
                        href.includes("/ip/") ||
                        href.includes("/product") ||
                        href.includes("/site/") ||
                        href.includes("prodid") ||
                        href.includes("skuId") ||
                        href.includes("sku") ||
                        text.length > 4
                    ) {
                        return href;
                    }
                }

                return "";
            }

            function getImg(card) {
                const img = card.querySelector("img");

                if (!img) return "";

                return (
                    img.currentSrc ||
                    img.src ||
                    img.getAttribute("data-src") ||
                    img.getAttribute("src") ||
                    ""
                );
            }

            const bad = [
                "sign in",
                "account",
                "cart",
                "menu",
                "privacy policy",
                "terms of use",
                "customer service",
                "track order",
                "skip to content",
                "store locator",
                "weekly ad"
            ];

            const candidates = Array.from(
                document.querySelectorAll("h1,h2,h3,[role='heading'],a")
            ).filter(el => {
                if (!visible(el)) return false;

                const name = textOf(el);

                if (!name || name.length < 3 || name.length > 240) return false;
                if (/^\\$/.test(name)) return false;

                return !bad.some(x => name.toLowerCase().includes(x));
            });

            const products = [];

            for (const el of candidates) {
                const name = textOf(el);
                const card = bestCard(el);
                const cardText = textOf(card);

                const prices = [
                    ...new Set(
                        (cardText.match(priceRe) || []).map(p =>
                            p.replace(/\\s+/g, "")
                        )
                    )
                ];

                if (!prices.length) continue;

                products.push({
                    product_name: name,
                    prices,
                    product_url: getUrl(card, el),
                    image_url: getImg(card),
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

    retailer_name = retailer["name"]
    base_url = retailer["base_url"]

    for item in data.get("products", []):
        name = clean_text(item.get("product_name", ""))
        prices = item.get("prices", [])
        price = normalize_price(prices[0]) if prices else ""
        product_url = clean_text(item.get("product_url", ""))
        image_url = clean_text(item.get("image_url", ""))

        if not name or not price:
            continue

        product_url = urljoin(base_url, product_url) if product_url else ""
        image_url = urljoin(base_url, image_url) if image_url else ""

        key = (retailer_name.lower(), name.lower(), price, product_url)

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "retailer": retailer_name,
                "group": retailer["group"],
                "keyword": keyword,
                "product_name": name,
                "price": price,
                "all_prices_found": "; ".join(
                    dict.fromkeys(
                        [normalize_price(p) for p in prices if normalize_price(p)]
                    )
                ),
                "product_url": product_url,
                "image_url": image_url,
                "source_url": data.get("url", ""),
                "status": "ok",
                "method": "championship_visible_dom",
            }
        )

    return rows, data


def save_csv(rows: list[dict[str, str]], output_file: Path) -> None:
    fieldnames = [
        "retailer",
        "group",
        "keyword",
        "product_name",
        "price",
        "all_prices_found",
        "product_url",
        "image_url",
        "source_url",
        "status",
        "method",
    ]

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def scrape_retailer(context, retailer: dict, keyword: str) -> list[dict[str, str]]:
    name = retailer["name"]
    url = format_url(retailer, keyword)

    print("")
    print("=" * 90)
    print(f"[INFO] Retailer: {name}")
    print(f"[INFO] Keyword: {keyword}")
    print(f"[INFO] URL: {url}")
    print("=" * 90)

    page = context.new_page()

    safe_retailer = safe_filename(name)
    safe_keyword = safe_filename(keyword)

    debug_html = OUTPUT_DIR / f"debug_{safe_retailer}_{safe_keyword}.html"
    debug_json = OUTPUT_DIR / f"debug_{safe_retailer}_{safe_keyword}.json"
    debug_png = OUTPUT_DIR / f"debug_{safe_retailer}_{safe_keyword}.png"
    debug_text = OUTPUT_DIR / f"debug_{safe_retailer}_{safe_keyword}.txt"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)

        wait_for_products_or_prices(page, timeout_seconds=30)

        max_load_more = retailer.get("max_load_more", DEFAULT_LOAD_MORE)
        click_load_more(page, max_clicks=max_load_more)

        for _ in range(2):
            page.mouse.wheel(0, 1000)
            time.sleep(0.7)

        html = page.content()
        text = visible_text(page)
        title = page.title()
        prices = count_visible_prices(page)

        debug_html.write_text(html, encoding="utf-8")
        debug_text.write_text(text, encoding="utf-8")
        page.screenshot(path=str(debug_png), full_page=True)

        blocked = blocked_check(title, text, prices)

        print(f"[INFO] {name}: blocked={blocked}; visible_price_count={prices}")

        if blocked:
            return [
                {
                    "retailer": name,
                    "group": retailer["group"],
                    "keyword": keyword,
                    "product_name": "",
                    "price": "",
                    "all_prices_found": "",
                    "product_url": "",
                    "image_url": "",
                    "source_url": page.url,
                    "status": "blocked_or_access_denied",
                    "method": "visible_text_status",
                }
            ]

        rows, debug_data = extract_products(page, keyword, retailer)
        debug_json.write_text(json.dumps(debug_data, indent=2), encoding="utf-8")

        if not rows:
            return [
                {
                    "retailer": name,
                    "group": retailer["group"],
                    "keyword": keyword,
                    "product_name": "",
                    "price": "",
                    "all_prices_found": "",
                    "product_url": "",
                    "image_url": "",
                    "source_url": page.url,
                    "status": "no_rows_extracted",
                    "method": "championship_visible_dom",
                }
            ]

        return rows

    except Exception as e:
        print(f"[ERROR] {name}: {e}")

        return [
            {
                "retailer": name,
                "group": retailer["group"],
                "keyword": keyword,
                "product_name": "",
                "price": "",
                "all_prices_found": "",
                "product_url": "",
                "image_url": "",
                "source_url": url,
                "status": f"error: {e}",
                "method": "exception",
            }
        ]

    finally:
        page.close()


def show_retailers() -> None:
    print("")
    print("Available retailers:")

    for i, retailer in enumerate(RETAILERS, start=1):
        print(f"{i:2d}. {retailer['name']} [{retailer['group']}]")

    print("")
    print("You can type:")
    print("  all")
    print("  clothing")
    print("  pharmacy")
    print("  bigbox")
    print("  electronics")
    print("  or numbers like 1,2,6,7")


def choose_retailers() -> list[dict]:
    show_retailers()

    choice = input("Choose retailers: ").strip().lower()

    if not choice or choice == "all":
        return RETAILERS

    if choice in {"clothing", "pharmacy", "bigbox", "electronics"}:
        return [r for r in RETAILERS if r["group"] == choice]

    selected = []

    for part in choice.split(","):
        part = part.strip()

        if not part.isdigit():
            continue

        idx = int(part)

        if 1 <= idx <= len(RETAILERS):
            selected.append(RETAILERS[idx - 1])

    return selected or [r for r in RETAILERS if r["group"] == "clothing"]


def load_keyword_csv(path: str, selected: list[dict]) -> dict[str, str]:
    names = {r["name"].lower(): r["name"] for r in selected}
    keyword_map = {}

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if "retailer" not in reader.fieldnames or "keyword" not in reader.fieldnames:
            raise ValueError("CSV must have retailer and keyword columns.")

        for row in reader:
            retailer = clean_text(row.get("retailer", "")).lower()
            keyword = clean_text(row.get("keyword", ""))

            if retailer in names and keyword:
                keyword_map[names[retailer]] = keyword

    return keyword_map


def get_keyword_map(selected: list[dict]) -> dict[str, str]:
    print("")
    print("Keyword mode:")
    print("1. Same keyword for all selected retailers")
    print("2. Different keyword for each retailer")
    print("3. Load from CSV")

    mode = input("Choose 1/2/3: ").strip()

    keyword_map = {}

    if mode == "1":
        keyword = input("Keyword for all retailers: ").strip()

        if not keyword:
            raise ValueError("Keyword cannot be empty.")

        for retailer in selected:
            keyword_map[retailer["name"]] = keyword

        return keyword_map

    if mode == "3":
        path = input("CSV path: ").strip()

        if not path:
            raise ValueError("CSV path cannot be empty.")

        return load_keyword_csv(path, selected)

    print("")
    print("Enter one keyword per retailer. Leave blank to skip.")

    for retailer in selected:
        keyword = input(f"{retailer['name']} keyword: ").strip()

        if keyword:
            keyword_map[retailer["name"]] = keyword

    if not keyword_map:
        raise ValueError("No keywords entered.")

    return keyword_map


def run_once() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(PROFILE_DIR).mkdir(exist_ok=True)

    selected = choose_retailers()
    keyword_map = get_keyword_map(selected)

    pairs = [
        (retailer, keyword_map[retailer["name"]])
        for retailer in selected
        if retailer["name"] in keyword_map
    ]

    if not pairs:
        raise ValueError("No retailer-keyword pairs selected.")

    output_csv = OUTPUT_DIR / "retailer_championship_prices.csv"
    all_rows = []

    print("")
    print("[INFO] Championship run starting")
    print(f"[INFO] Retailer-keyword pairs: {len(pairs)}")
    print(f"[INFO] Output CSV: {output_csv}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            channel="chrome",
            headless=False,
            slow_mo=120,
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )

        try:
            for retailer, keyword in pairs:
                rows = scrape_retailer(context, retailer, keyword)
                all_rows.extend(rows)

                # Save after each retailer so progress is not lost.
                save_csv(all_rows, output_csv)

                time.sleep(DELAY_BETWEEN_RETAILERS)

        finally:
            context.close()

    save_csv(all_rows, output_csv)

    ok = sorted({r["retailer"] for r in all_rows if r.get("status") == "ok"})
    bad = sorted({r["retailer"] for r in all_rows if r.get("status") != "ok"})

    print("")
    print("[DONE] Championship run finished")
    print(f"[DONE] Rows saved: {len(all_rows)}")
    print(f"[DONE] CSV saved: {output_csv}")

    print("")
    print(f"[DONE] Retailers with rows: {len(ok)}")

    for name in ok:
        print(f"  OK: {name}")

    print("")
    print(f"[DONE] Retailers with warnings/errors: {len(bad)}")

    for name in bad:
        print(f"  CHECK: {name}")


def main() -> None:
    while True:
        try:
            run_once()
            break

        except PlaywrightTimeoutError as e:
            print(f"[ERROR] Timeout: {e}")

            if ask_retry():
                continue

            break

        except KeyboardInterrupt:
            print("\n[STOPPED]")
            break

        except Exception as e:
            print(f"[ERROR] {e}")

            if ask_retry():
                continue

            break


if __name__ == "__main__":
    main()
