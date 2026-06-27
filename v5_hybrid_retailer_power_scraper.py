#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


OUTPUT_DIR = Path("output") / "retailer_championship_output"
PROFILE_BASE_DIR = Path("./retailer_parallel_profiles")

PRICE_RE = re.compile(r"\$\s?\d+(?:,\d{3})*(?:\.\d{2})?")
NUMERIC_PRICE_RE = re.compile(r"^\s*\d+(?:,\d{3})*(?:\.\d{1,2})?\s*$")

MAX_WORKERS = 2
DEFAULT_LOAD_MORE = 2
DELAY_BETWEEN_RETAILERS = 3
HEADLESS = False
MANUAL_CHALLENGE_MODE = True


RETAILERS = [
    {"name": "CVS", "group": "pharmacy", "risk": "medium", "strategy": "cvs_h2", "base_url": "https://www.cvs.com", "search_url": "https://www.cvs.com/search?searchTerm={query_plus}", "max_load_more": 3, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Walgreens", "group": "pharmacy", "risk": "medium", "strategy": "generic", "base_url": "https://www.walgreens.com", "search_url": "https://www.walgreens.com/search/results.jsp?Ntt={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "RiteAid", "group": "pharmacy", "risk": "low", "strategy": "generic", "base_url": "https://www.riteaid.com", "search_url": "https://www.riteaid.com/shop/catalogsearch/result/?q={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Walmart", "group": "bigbox", "risk": "high", "strategy": "manual_or_blocked", "base_url": "https://www.walmart.com", "search_url": "https://www.walmart.com/search?q={query_plus}", "max_load_more": 0, "parallel_ok": False, "manual_challenge_ok": True},
    {"name": "Target", "group": "bigbox", "risk": "high", "strategy": "generic", "base_url": "https://www.target.com", "search_url": "https://www.target.com/s?searchTerm={query_plus}", "max_load_more": 1, "parallel_ok": False, "manual_challenge_ok": False},
    {"name": "Best Buy", "group": "electronics", "risk": "medium", "strategy": "bestbuy", "base_url": "https://www.bestbuy.com", "search_url": "https://www.bestbuy.com/site/searchpage.jsp?st={query_plus}&intl=nosplash", "max_load_more": 1, "parallel_ok": True, "manual_challenge_ok": False, "country_gate": "us"},
    {"name": "Macys", "group": "clothing", "risk": "high", "strategy": "generic", "base_url": "https://www.macys.com", "search_url": "https://www.macys.com/shop/featured/{query_dash}", "max_load_more": 0, "parallel_ok": False, "manual_challenge_ok": False},
    {"name": "Kohls", "group": "clothing", "risk": "high", "strategy": "generic", "base_url": "https://www.kohls.com", "search_url": "https://www.kohls.com/search.jsp?search={query_plus}", "max_load_more": 0, "parallel_ok": False, "manual_challenge_ok": False},
    {"name": "Old Navy", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://oldnavy.gap.com", "search_url": "https://oldnavy.gap.com/browse/search.do?searchText={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Gap", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://www.gap.com", "search_url": "https://www.gap.com/browse/search.do?searchText={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Banana Republic", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://bananarepublic.gap.com", "search_url": "https://bananarepublic.gap.com/browse/search.do?searchText={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "HM", "group": "clothing", "risk": "low", "strategy": "generic", "base_url": "https://www2.hm.com", "search_url": "https://www2.hm.com/en_us/search-results.html?q={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Uniqlo", "group": "clothing", "risk": "low", "strategy": "generic", "base_url": "https://www.uniqlo.com", "search_url": "https://www.uniqlo.com/us/en/search?q={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "JCPenney", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://www.jcpenney.com", "search_url": "https://www.jcpenney.com/s?searchTerm={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Nordstrom", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://www.nordstrom.com", "search_url": "https://www.nordstrom.com/sr?origin=keywordsearch&keyword={query_plus}", "max_load_more": 1, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Nordstrom Rack", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://www.nordstromrack.com", "search_url": "https://www.nordstromrack.com/sr?origin=keywordsearch&keyword={query_plus}", "max_load_more": 1, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "DSW", "group": "clothing", "risk": "low", "strategy": "generic", "base_url": "https://www.dsw.com", "search_url": "https://www.dsw.com/browse?Ntt={query_plus}", "max_load_more": 2, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "Foot Locker", "group": "clothing", "risk": "medium", "strategy": "generic", "base_url": "https://www.footlocker.com", "search_url": "https://www.footlocker.com/search?query={query_plus}", "max_load_more": 1, "parallel_ok": True, "manual_challenge_ok": False},
    {"name": "American Eagle", "group": "clothing", "risk": "low", "strategy": "generic", "base_url": "https://www.ae.com", "search_url": "https://www.ae.com/us/en/s/{query_plus}", "max_load_more": 1, "parallel_ok": True, "manual_challenge_ok": False},
]


def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def safe_filename(text: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return safe or "file"


def normalize_price(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and value > 0:
        return f"${float(value):.2f}"
    text = clean_text(value)
    if not text:
        return ""
    match = PRICE_RE.search(text)
    if match:
        return match.group(0).replace(" ", "")
    if NUMERIC_PRICE_RE.match(text):
        try:
            number = float(text.replace(",", ""))
            if number > 0:
                return f"${number:.2f}"
        except Exception:
            return ""
    return ""


def format_url(retailer: dict, keyword: str) -> str:
    query_plus = quote_plus(keyword)
    query_encoded = quote(keyword)
    query_dash = re.sub(r"[^a-zA-Z0-9]+", "-", keyword).strip("-").lower()
    return retailer["search_url"].format(query_plus=query_plus, query_encoded=query_encoded, query_dash=query_dash)


def ask_retry() -> bool:
    while True:
        ans = input("Retry? y/n: ").strip().lower()
        if ans in {"y", "yes"}:
            return True
        if ans in {"n", "no"}:
            return False
        print("Please type y or n.")


def visible_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def count_visible_prices(page) -> int:
    try:
        return page.evaluate("""
        () => {
            const re = /\$\s?\d+(?:,\d{3})*(?:\.\d{2})?/;
            let count = 0;
            function visible(el) {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 2 && r.height > 2;
            }
            for (const el of document.querySelectorAll('*')) {
                if (!visible(el)) continue;
                const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!t || t.length > 500) continue;
                if (re.test(t)) count++;
            }
            return count;
        }
        """)
    except Exception:
        return 0


def detect_block_reason(title: str, text: str, price_count: int) -> str:
    if price_count > 0:
        return ""
    combined = f"{clean_text(title).lower()}\n{clean_text(text).lower()[:7000]}"
    checks = [
        ("blocked_press_and_hold", ["press and hold", "press & hold", "continue holding"]),
        ("blocked_captcha", ["captcha"]),
        ("blocked_human_verification", ["verify you are human", "verify that you are human", "robot or human", "are you a robot"]),
        ("blocked_access_denied", ["access denied", "you don't have permission", "request blocked", "unusual traffic", "pardon the interruption"]),
    ]
    for reason, terms in checks:
        if any(term in combined for term in terms):
            return reason
    return ""


def manual_challenge_pause(page, retailer_name: str) -> bool:
    if not MANUAL_CHALLENGE_MODE:
        return False
    reason = detect_block_reason(page.title(), visible_text(page), count_visible_prices(page))
    if reason not in {"blocked_press_and_hold", "blocked_captcha", "blocked_human_verification"}:
        return False
    print("\n" + "=" * 90)
    print(f"[WARN] {retailer_name}: human verification detected ({reason}).")
    print("[ACTION] Complete the verification manually in the opened Chrome window.")
    print("[ACTION] Do not close Chrome.")
    input("[ACTION] After the normal product/search page loads, press Enter here to continue...")
    print("[INFO] Continuing after manual verification...")
    print("=" * 90)
    time.sleep(3)
    return True


def handle_best_buy_country_gate(page, search_url: str) -> None:
    time.sleep(2)
    text = visible_text(page).lower()
    url = page.url.lower()
    gate = "bestbuy.com" in url and (
        "choose a country" in text
        or "select your country" in text
        or ("united states" in text and "canada" in text)
        or "intl" in url
    )
    if not gate:
        return
    print("[INFO] Best Buy country page detected. Choosing United States...")
    clicked = False
    for getter in (
        lambda: page.get_by_role("link", name=re.compile(r"united states", re.I)),
        lambda: page.get_by_role("button", name=re.compile(r"united states", re.I)),
        lambda: page.get_by_text(re.compile(r"united states", re.I)),
    ):
        if clicked:
            break
        try:
            getter().click(timeout=6000)
            clicked = True
        except Exception:
            pass
    if not clicked:
        try:
            clicked = page.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll('a, button, div[role="button"]'));
                for (const el of els) {
                    const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    if (t.includes('united states')) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return true;
                    }
                }
                return false;
            }
            """)
        except Exception:
            clicked = False
    if clicked:
        time.sleep(4)
        print("[INFO] United States selected. Reloading Best Buy search...")
    else:
        print("[WARN] Could not click United States automatically. Retrying search URL.")
    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
    time.sleep(5)


def wait_for_products_or_prices(page, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            result = page.evaluate("""
            () => {
                const priceRe = /\$\s?\d+(?:,\d{3})*(?:\.\d{2})?/;
                function textOf(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); }
                function visible(el) {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 2 && r.height > 2;
                }
                const bad = ['sign in', 'account', 'cart', 'menu', 'customer service', 'privacy policy', 'terms of use'];
                const headings = Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"],a')).filter(el => {
                    if (!visible(el)) return false;
                    const t = textOf(el);
                    if (!t || t.length < 3 || t.length > 240) return false;
                    if (/^\$/.test(t)) return false;
                    return !bad.some(x => t.toLowerCase().includes(x));
                });
                let priceCount = 0;
                for (const el of document.querySelectorAll('*')) {
                    if (!visible(el)) continue;
                    const t = textOf(el);
                    if (!t || t.length > 500) continue;
                    if (priceRe.test(t)) priceCount++;
                }
                return {headingCount: headings.length, priceCount};
            }
            """)
            print(f"[INFO] Product heading count: {result.get('headingCount', 0)}; visible price count: {result.get('priceCount', 0)}")
            if result.get("headingCount", 0) > 0 or result.get("priceCount", 0) > 0:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def click_load_more(page, max_clicks: int) -> None:
    if max_clicks <= 0:
        print("[INFO] Load-more skipped for this retailer.")
        return
    labels = re.compile(r"load more|show more|see more|more results|view more|show all", re.I)
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


def product_rows(raw_products: list[dict], keyword: str, retailer: dict, status: str, method: str, source_url: str) -> list[dict[str, str]]:
    rows = []
    seen = set()
    for item in raw_products:
        name = clean_text(item.get("name") or item.get("product_name") or item.get("title") or item.get("display_name"))
        price = normalize_price(item.get("price") or item.get("sale_price") or item.get("current_price") or item.get("regular_price") or item.get("low_price"))
        product_url = clean_text(item.get("url") or item.get("product_url") or item.get("href"))
        image_url = clean_text(item.get("image") or item.get("image_url") or item.get("thumbnail"))
        if not name or len(name) < 3 or len(name) > 240 or not price:
            continue
        product_url = urljoin(retailer["base_url"], product_url) if product_url else ""
        image_url = urljoin(retailer["base_url"], image_url) if image_url else ""
        key = (retailer["name"].lower(), name.lower(), price, product_url)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "retailer": retailer["name"],
            "group": retailer["group"],
            "risk": retailer.get("risk", ""),
            "strategy": retailer.get("strategy", ""),
            "keyword": keyword,
            "product_name": name,
            "price": price,
            "all_prices_found": clean_text(item.get("all_prices_found") or price),
            "product_url": product_url,
            "image_url": image_url,
            "source_url": source_url,
            "status": status,
            "method": method,
        })
    return rows


def extract_json_ld(page, keyword: str, retailer: dict) -> tuple[list[dict[str, str]], dict]:
    data = page.evaluate("""
    () => {
        function arr(x){ return !x ? [] : Array.isArray(x) ? x : [x]; }
        function clean(x){
            if (x === null || x === undefined) return '';
            if (Array.isArray(x)) return clean(x[0]);
            if (typeof x === 'object') return clean(x.url || x['@id'] || x.name || '');
            return String(x).replace(/\s+/g,' ').trim();
        }
        function image(x){
            if (!x) return '';
            if (Array.isArray(x)) return image(x[0]);
            if (typeof x === 'object') return clean(x.url || x.contentUrl || x.src || x.image || '');
            return clean(x);
        }
        function types(obj){
            const t = obj && (obj['@type'] || obj.type);
            if (!t) return [];
            return Array.isArray(t) ? t.map(String) : [String(t)];
        }
        function offerPrice(offers){
            for (const offer of arr(offers)) {
                if (!offer || typeof offer !== 'object') continue;
                const direct = offer.price || offer.lowPrice || offer.highPrice;
                if (direct) return clean(direct);
                for (const spec of arr(offer.priceSpecification)) {
                    if (spec && spec.price) return clean(spec.price);
                }
                if (offer.offers) {
                    const nested = offerPrice(offer.offers);
                    if (nested) return nested;
                }
            }
            return '';
        }
        function walk(node, out, depth=0){
            if (!node || depth > 10 || out.length > 300) return;
            if (Array.isArray(node)) { for (const x of node) walk(x,out,depth+1); return; }
            if (typeof node !== 'object') return;
            if (types(node).map(x=>x.toLowerCase()).includes('product')) {
                const name = clean(node.name || node.title);
                const price = offerPrice(node.offers) || clean(node.price || node.lowPrice);
                if (name && price) out.push({name, price, url: clean(node.url || node['@id']), image: image(node.image || node.thumbnailUrl)});
            }
            if (node['@graph']) walk(node['@graph'], out, depth+1);
            for (const value of Object.values(node)) if (value && typeof value === 'object') walk(value,out,depth+1);
        }
        const products = [];
        for (const script of Array.from(document.querySelectorAll('script[type*="ld+json"]'))) {
            try { walk(JSON.parse(script.textContent || ''), products); } catch(e) {}
        }
        return {url: location.href, title: document.title, count: products.length, products: products.slice(0,250)};
    }
    """)
    return product_rows(data.get("products", []), keyword, retailer, "ok_json_ld", "v5_json_ld", data.get("url", page.url)), data


def extract_embedded_json(page, keyword: str, retailer: dict) -> tuple[list[dict[str, str]], dict]:
    data = page.evaluate("""
    () => {
        function clean(x){
            if (x === null || x === undefined) return '';
            if (Array.isArray(x)) return clean(x[0]);
            if (typeof x === 'object') return clean(x.value || x.amount || x.price || x.url || '');
            return String(x).replace(/\s+/g,' ').trim();
        }
        function field(obj, names){
            for (const name of names) if (obj && Object.prototype.hasOwnProperty.call(obj,name)) { const v = clean(obj[name]); if (v) return v; }
            return '';
        }
        function price(obj){
            const direct = field(obj, ['price','currentPrice','salePrice','regularPrice','finalPrice','offerPrice','priceValue','lowPrice','highPrice','minPrice','maxPrice']);
            if (direct) return direct;
            for (const k of Object.keys(obj || {})) if (k.toLowerCase().includes('price')) { const v = clean(obj[k]); if (v) return v; }
            return '';
        }
        function img(x){
            if (!x) return '';
            if (Array.isArray(x)) return img(x[0]);
            if (typeof x === 'object') return clean(x.url || x.src || x.imageUrl || x.thumbnailUrl || x.href || '');
            return clean(x);
        }
        function candidate(obj){
            if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
            const name = field(obj, ['name','title','productName','displayName','shortDescription']);
            const p = price(obj);
            if (!name || !p || name.length < 3 || name.length > 240) return null;
            return {
                name,
                price: p,
                url: field(obj, ['url','href','productUrl','canonicalUrl','pdpUrl','link','seoUrl']),
                image: img(obj.image || obj.images || obj.imageUrl || obj.thumbnail || obj.thumbnailUrl || obj.primaryImage)
            };
        }
        function walk(node, out, depth=0, seen=new WeakSet()){
            if (!node || depth > 9 || out.length > 350) return;
            if (typeof node === 'object') { if (seen.has(node)) return; seen.add(node); }
            if (Array.isArray(node)) { for (const x of node) walk(x,out,depth+1,seen); return; }
            if (typeof node !== 'object') return;
            const product = candidate(node);
            if (product) out.push(product);
            for (const value of Object.values(node)) if (value && typeof value === 'object') walk(value,out,depth+1,seen);
        }
        const roots = [];
        for (const sel of ['#__NEXT_DATA__','#__NUXT_DATA__']) {
            const el = document.querySelector(sel);
            if (el && el.textContent) { try { roots.push(JSON.parse(el.textContent)); } catch(e) {} }
        }
        for (const script of Array.from(document.querySelectorAll('script[type="application/json"]'))) {
            const raw = (script.textContent || '').trim();
            if (!raw.startsWith('{') && !raw.startsWith('[')) continue;
            try { roots.push(JSON.parse(raw)); } catch(e) {}
        }
        const products = [];
        for (const root of roots) walk(root, products);
        return {url: location.href, title: document.title, rootCount: roots.length, count: products.length, products: products.slice(0,250)};
    }
    """)
    return product_rows(data.get("products", []), keyword, retailer, "ok_embedded_json", "v5_embedded_json", data.get("url", page.url)), data


def extract_dom(page, keyword: str, retailer: dict) -> tuple[list[dict[str, str]], dict]:
    data = page.evaluate("""
    () => {
        const priceRe = /\$\s?\d+(?:,\d{3})*(?:\.\d{2})?/g;
        function textOf(el){ return (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim(); }
        function visible(el){ const s=getComputedStyle(el); const r=el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 2 && r.height > 2; }
        function badText(t){
            const bad = ['sign in','account','cart','menu','privacy policy','terms of use','customer service','track order','skip to content','store locator','weekly ad','accessibility','footer','newsletter','email address'];
            const lower = t.toLowerCase();
            return bad.some(x => lower.includes(x));
        }
        function score(card, depth){
            const text = textOf(card);
            const prices = text.match(priceRe) || [];
            const links = card.querySelectorAll ? card.querySelectorAll('a[href]').length : 0;
            const imgs = card.querySelectorAll ? card.querySelectorAll('img').length : 0;
            const buttons = card.querySelectorAll ? card.querySelectorAll('button').length : 0;
            const reviews = /review|rating|stars?/i.test(text) ? 1 : 0;
            const add = /add to cart|add to bag|pickup|delivery|shipping/i.test(text) ? 1 : 0;
            if (text.length < 20 || text.length > 5000) return -999;
            let s = 0;
            s += prices.length ? 70 : 0;
            s += links ? 20 : 0;
            s += imgs ? 15 : 0;
            s += buttons ? 10 : 0;
            s += reviews ? 6 : 0;
            s += add ? 8 : 0;
            s += text.length < 1500 ? 12 : 0;
            s -= text.length > 3000 ? 20 : 0;
            s -= badText(text) ? 30 : 0;
            s -= depth;
            return s;
        }
        function bestCard(el){
            let best = null;
            let cur = el;
            for (let depth=0; cur && depth<15; depth++) {
                const s = score(cur, depth);
                if (!best || s > best.score) best = {el: cur, score: s};
                cur = cur.parentElement;
            }
            return best && best.score > 0 ? best.el : el;
        }
        function getUrl(card, el){
            let cur = el;
            while (cur && cur !== card) { if (cur.tagName === 'A' && cur.href) return cur.href; cur = cur.parentElement; }
            const links = Array.from(card.querySelectorAll('a[href]'));
            for (const a of links) {
                const href = a.href || '';
                const text = textOf(a).toLowerCase();
                if (href.includes('/shop/') || href.includes('/p/') || href.includes('/ip/') || href.includes('/product') || href.includes('/site/') || href.includes('prodid') || href.includes('skuId') || href.includes('sku') || text.length > 4) return href;
            }
            return '';
        }
        function getImg(card){ const img = card.querySelector('img'); return img ? (img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('src') || '') : ''; }
        const selectors = ['[data-testid*="product"]','[data-test*="product"]','[class*="product"]','[class*="Product"]','[class*="sku"]','[class*="Sku"]','article','li','h1','h2','h3','[role="heading"]','a'];
        const candidates = Array.from(document.querySelectorAll(selectors.join(','))).filter(el => {
            if (!visible(el)) return false;
            const name = textOf(el);
            if (!name || name.length < 3 || name.length > 240) return false;
            if (/^\$/.test(name)) return false;
            if (badText(name)) return false;
            return true;
        });
        const products = [];
        for (const el of candidates) {
            const name = textOf(el);
            const card = bestCard(el);
            const cardText = textOf(card);
            const prices = [...new Set((cardText.match(priceRe) || []).map(p => p.replace(/\s+/g,'')))];
            if (!prices.length) continue;
            const url = getUrl(card, el);
            const image = getImg(card);
            if (!url && !image && cardText.length > 1800) continue;
            products.push({name, price: prices[0], all_prices_found: prices.join('; '), url, image, score: score(card, 0)});
        }
        return {url: location.href, title: document.title, candidateCount: candidates.length, count: products.length, products: products.slice(0,250)};
    }
    """)
    return product_rows(data.get("products", []), keyword, retailer, "ok_dom", "v5_visible_dom", data.get("url", page.url)), data


def extract_cvs_h2(page, keyword: str, retailer: dict) -> tuple[list[dict[str, str]], dict]:
    data = page.evaluate("""
    () => {
        const priceRe = /\$\s?\d+(?:,\d{3})*(?:\.\d{2})?/g;
        function textOf(el){ return (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim(); }
        function visible(el){ const s=getComputedStyle(el); const r=el.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 2 && r.height > 2; }
        function bestCard(h){
            let best = null;
            let cur = h;
            for (let depth=0; cur && depth<13; depth++) {
                const text = textOf(cur);
                const prices = text.match(priceRe) || [];
                const links = cur.querySelectorAll ? cur.querySelectorAll('a[href]').length : 0;
                const imgs = cur.querySelectorAll ? cur.querySelectorAll('img').length : 0;
                const buttons = cur.querySelectorAll ? cur.querySelectorAll('button').length : 0;
                if (text.length >= 20 && text.length <= 3500) {
                    let score = 0;
                    score += prices.length ? 70 : 0;
                    score += links ? 20 : 0;
                    score += imgs ? 10 : 0;
                    score += buttons ? 10 : 0;
                    score += text.length < 1200 ? 10 : 0;
                    score -= depth;
                    if (!best || score > best.score) best = {el: cur, score};
                }
                cur = cur.parentElement;
            }
            return best ? best.el : h.parentElement;
        }
        function productUrl(card, h){
            let cur = h;
            while (cur && cur !== card) { if (cur.tagName === 'A' && cur.href) return cur.href; cur = cur.parentElement; }
            const links = Array.from(card.querySelectorAll('a[href]'));
            for (const a of links) {
                const href = a.href || '';
                if (href.includes('/shop/') || href.includes('prodid') || href.includes('skuId')) return href;
            }
            return links.length ? links[0].href : '';
        }
        function imageUrl(card){ const img = card.querySelector('img'); return img ? (img.currentSrc || img.src || img.getAttribute('data-src') || '') : ''; }
        const bad = ['shop','categories','sign in','extracare','weekly ad','find a store','cart','menu'];
        const headings = Array.from(document.querySelectorAll('h2[role="heading"], h2[aria-level="2"], [role="heading"][aria-level="2"]')).filter(h => {
            const t = textOf(h);
            if (!t || !visible(h)) return false;
            if (t.length < 3 || t.length > 240) return false;
            return !bad.some(x => t.toLowerCase().includes(x));
        });
        const products = [];
        for (const h of headings) {
            const card = bestCard(h);
            const cardText = textOf(card);
            const prices = [...new Set((cardText.match(priceRe) || []).map(p => p.replace(/\s+/g,'')))];
            if (!prices.length) continue;
            products.push({name: textOf(h), price: prices[0], all_prices_found: prices.join('; '), url: productUrl(card,h), image: imageUrl(card)});
        }
        return {url: location.href, title: document.title, headingCount: headings.length, count: products.length, products: products.slice(0,250)};
    }
    """)
    return product_rows(data.get("products", []), keyword, retailer, "ok_cvs_h2", "v5_cvs_h2", data.get("url", page.url)), data


def extract_hybrid(page, keyword: str, retailer: dict) -> tuple[list[dict[str, str]], dict]:
    strategy = retailer.get("strategy", "generic")
    attempts = []
    if strategy == "cvs_h2":
        methods = [("json_ld", extract_json_ld), ("embedded_json", extract_embedded_json), ("cvs_h2", extract_cvs_h2), ("visible_dom", extract_dom)]
    else:
        methods = [("json_ld", extract_json_ld), ("embedded_json", extract_embedded_json), ("visible_dom", extract_dom)]
    debug = {"retailer": retailer["name"], "keyword": keyword, "strategy": strategy, "attempts": attempts, "selected_method": ""}
    for name, func in methods:
        try:
            rows, data = func(page, keyword, retailer)
            attempts.append({"method": name, "row_count": len(rows), "raw_count": data.get("count", 0), "url": data.get("url", page.url), "title": data.get("title", "")})
            print(f"[INFO] {retailer['name']}: {name} rows={len(rows)}")
            if rows:
                debug["selected_method"] = name
                debug["selected_debug"] = data
                return rows, debug
        except Exception as e:
            attempts.append({"method": name, "row_count": 0, "error": str(e)})
            print(f"[WARN] {retailer['name']}: {name} failed: {e}")
    return [], debug


def save_csv(rows: list[dict[str, str]], output_file: Path) -> None:
    fields = ["retailer", "group", "risk", "strategy", "keyword", "product_name", "price", "all_prices_found", "product_url", "image_url", "source_url", "status", "method"]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def status_row(retailer: dict, keyword: str, source_url: str, status: str, method: str) -> list[dict[str, str]]:
    return [{
        "retailer": retailer["name"], "group": retailer["group"], "risk": retailer.get("risk", ""), "strategy": retailer.get("strategy", ""),
        "keyword": keyword, "product_name": "", "price": "", "all_prices_found": "", "product_url": "", "image_url": "", "source_url": source_url,
        "status": status, "method": method,
    }]


def save_debug(page, prefix: Path, data: dict | None = None) -> None:
    try:
        prefix.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        prefix.with_suffix(".txt").write_text(visible_text(page), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(prefix.with_suffix(".png")), full_page=True)
    except Exception:
        pass
    if data is not None:
        try:
            prefix.with_suffix(".json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


def scrape_retailer_with_context(context, retailer: dict, keyword: str) -> list[dict[str, str]]:
    name = retailer["name"]
    url = format_url(retailer, keyword)
    print("\n" + "=" * 90)
    print(f"[INFO] Retailer: {name}")
    print(f"[INFO] Keyword: {keyword}")
    print(f"[INFO] Strategy: {retailer.get('strategy', 'generic')}")
    print(f"[INFO] URL: {url}")
    print("=" * 90)
    page = context.new_page()
    debug_prefix = OUTPUT_DIR / f"debug_{safe_filename(name)}_{safe_filename(keyword)}_v5"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        if retailer.get("country_gate") == "us" or name.lower() == "best buy":
            handle_best_buy_country_gate(page, url)
        if retailer.get("manual_challenge_ok", False):
            manual_challenge_pause(page, name)
        reason = detect_block_reason(page.title(), visible_text(page), count_visible_prices(page))
        if reason:
            save_debug(page, debug_prefix, {"retailer": name, "keyword": keyword, "block_reason": reason, "stage": "early", "url": page.url})
            print(f"[WARN] {name}: blocked/access-control page detected: {reason}")
            return status_row(retailer, keyword, page.url, reason, "v5_blocked_early")
        wait_for_products_or_prices(page, timeout_seconds=30)
        click_load_more(page, retailer.get("max_load_more", DEFAULT_LOAD_MORE))
        for _ in range(2):
            page.mouse.wheel(0, 1000)
            time.sleep(0.7)
        reason = detect_block_reason(page.title(), visible_text(page), count_visible_prices(page))
        if reason:
            save_debug(page, debug_prefix, {"retailer": name, "keyword": keyword, "block_reason": reason, "stage": "post_scroll", "url": page.url})
            print(f"[WARN] {name}: blocked/access-control page detected: {reason}")
            return status_row(retailer, keyword, page.url, reason, "v5_blocked_post_scroll")
        rows, debug_data = extract_hybrid(page, keyword, retailer)
        save_debug(page, debug_prefix, debug_data)
        if not rows:
            return status_row(retailer, keyword, page.url, "no_rows_extracted", "v5_hybrid")
        return rows
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        try:
            save_debug(page, debug_prefix, {"retailer": name, "keyword": keyword, "error": str(e), "url": page.url if page else url})
        except Exception:
            pass
        return status_row(retailer, keyword, url, f"error: {e}", "v5_exception")
    finally:
        page.close()


def scrape_retailer_worker(retailer: dict, keyword: str) -> list[dict[str, str]]:
    name = retailer["name"]
    profile_dir = PROFILE_BASE_DIR / safe_filename(name)
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"[WORKER] Starting {name} with profile: {profile_dir}")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=HEADLESS,
            slow_mo=120,
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )
        try:
            return scrape_retailer_with_context(context, retailer, keyword)
        finally:
            context.close()
            print(f"[WORKER] Finished {name}")


def show_retailers() -> None:
    print("\nAvailable retailers:")
    for i, retailer in enumerate(RETAILERS, start=1):
        mode = "parallel" if retailer.get("parallel_ok", True) else "sequential"
        manual = ", manual-check" if retailer.get("manual_challenge_ok", False) else ""
        print(f"{i:2d}. {retailer['name']} [{retailer['group']}, {retailer.get('risk')}, {retailer.get('strategy')}, {mode}{manual}]")
    print("\nYou can type: all, clothing, pharmacy, bigbox, electronics, low, medium, high, or numbers like 1,2,6,7")


def choose_retailers() -> list[dict]:
    show_retailers()
    choice = input("Choose retailers: ").strip().lower()
    if not choice or choice == "all":
        return RETAILERS
    groups = {r["group"] for r in RETAILERS}
    risks = {r.get("risk", "") for r in RETAILERS}
    if choice in groups:
        return [r for r in RETAILERS if r["group"] == choice]
    if choice in risks:
        return [r for r in RETAILERS if r.get("risk", "") == choice]
    selected = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit():
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
    print("\nKeyword mode:")
    print("1. Same keyword for all selected retailers")
    print("2. Different keyword for each retailer")
    print("3. Load from CSV")
    mode = input("Choose 1/2/3: ").strip()
    if mode == "1":
        keyword = input("Keyword for all retailers: ").strip()
        if not keyword:
            raise ValueError("Keyword cannot be empty.")
        return {r["name"]: keyword for r in selected}
    if mode == "3":
        path = input("CSV path: ").strip()
        if not path:
            raise ValueError("CSV path cannot be empty.")
        return load_keyword_csv(path, selected)
    print("\nEnter one keyword per retailer. Leave blank to skip.")
    keyword_map = {}
    for retailer in selected:
        keyword = input(f"{retailer['name']} keyword: ").strip()
        if keyword:
            keyword_map[retailer["name"]] = keyword
    if not keyword_map:
        raise ValueError("No keywords entered.")
    return keyword_map


def run_parallel_pairs(pairs: list[tuple[dict, str]], all_rows: list[dict[str, str]], output_csv: Path) -> None:
    if not pairs:
        return
    print(f"\n[INFO] Running {len(pairs)} parallel-safe retailers with MAX_WORKERS={MAX_WORKERS}")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(scrape_retailer_worker, retailer, keyword): (retailer, keyword) for retailer, keyword in pairs}
        for future in as_completed(future_map):
            retailer, keyword = future_map[future]
            try:
                rows = future.result()
            except Exception as e:
                rows = status_row(retailer, keyword, format_url(retailer, keyword), f"worker_error: {e}", "v5_worker_exception")
            all_rows.extend(rows)
            save_csv(all_rows, output_csv)
            print(f"[INFO] Saved progress after {retailer['name']}. Total rows: {len(all_rows)}")


def run_sequential_pairs(pairs: list[tuple[dict, str]], all_rows: list[dict[str, str]], output_csv: Path) -> None:
    if not pairs:
        return
    print(f"\n[INFO] Running {len(pairs)} sensitive/manual retailers sequentially")
    for retailer, keyword in pairs:
        rows = scrape_retailer_worker(retailer, keyword)
        all_rows.extend(rows)
        save_csv(all_rows, output_csv)
        print(f"[INFO] Saved progress after {retailer['name']}. Total rows: {len(all_rows)}")
        time.sleep(DELAY_BETWEEN_RETAILERS)


def build_summary(rows: list[dict[str, str]]) -> dict:
    statuses = {}
    for row in rows:
        status = row.get("status", "")
        statuses[status] = statuses.get(status, 0) + 1
    ok_retailers = sorted({row.get("retailer", "") for row in rows if row.get("status", "").startswith("ok_")})
    issue_retailers = sorted({row.get("retailer", "") for row in rows if not row.get("status", "").startswith("ok_")})
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": len(rows),
        "retailer_count": len({row.get("retailer", "") for row in rows if row.get("retailer")}),
        "statuses": statuses,
        "ok_retailers": ok_retailers,
        "issue_retailers": issue_retailers,
    }


def run_once() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    selected = choose_retailers()
    keyword_map = get_keyword_map(selected)
    pairs = [(retailer, keyword_map[retailer["name"]]) for retailer in selected if retailer["name"] in keyword_map]
    if not pairs:
        raise ValueError("No retailer-keyword pairs selected.")
    parallel_pairs = [(r, k) for r, k in pairs if r.get("parallel_ok", True)]
    sequential_pairs = [(r, k) for r, k in pairs if not r.get("parallel_ok", True)]
    output_csv = OUTPUT_DIR / "retailer_championship_prices_v5.csv"
    summary_json = OUTPUT_DIR / "run_summary_v5.json"
    all_rows = []
    print("\n[INFO] V5 hybrid power run starting")
    print(f"[INFO] Total retailer-keyword pairs: {len(pairs)}")
    print(f"[INFO] Parallel pairs: {len(parallel_pairs)}")
    print(f"[INFO] Sequential/manual pairs: {len(sequential_pairs)}")
    print(f"[INFO] MAX_WORKERS: {MAX_WORKERS}")
    print(f"[INFO] Manual challenge mode: {MANUAL_CHALLENGE_MODE}")
    print(f"[INFO] Output CSV: {output_csv}")
    run_parallel_pairs(parallel_pairs, all_rows, output_csv)
    run_sequential_pairs(sequential_pairs, all_rows, output_csv)
    save_csv(all_rows, output_csv)
    summary = build_summary(all_rows)
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n[DONE] V5 hybrid power run finished")
    print(f"[DONE] Rows saved: {len(all_rows)}")
    print(f"[DONE] CSV saved: {output_csv}")
    print(f"[DONE] Summary saved: {summary_json}")
    print("\n[DONE] Status counts:")
    for status, count in sorted(summary["statuses"].items()):
        print(f"  {status}: {count}")
    print(f"\n[DONE] Retailers with product rows: {len(summary['ok_retailers'])}")
    for name in summary["ok_retailers"]:
        print(f"  OK: {name}")
    print(f"\n[DONE] Retailers with warnings/errors: {len(summary['issue_retailers'])}")
    for name in summary["issue_retailers"]:
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
