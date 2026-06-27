# Retail Price Scraper Versions

Research-style Playwright scripts for collecting product-price snapshots from public retailer search pages that are normally accessible in a regular browser.

The repository keeps each version as a standalone script so the development path is easy to follow.

## Important note

This project does **not** bypass CAPTCHA, press-and-hold, anti-bot gates, or access-control pages.

When a retailer displays a verification or access-control page, the scripts either:

- record the status as blocked, or
- pause so a real human can complete verification manually, then continue.

That makes the project safer and more defensible for GitHub and research use.

## Install

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chrome
```

Direct install:

```bash
python3 -m pip install playwright beautifulsoup4 lxml
python3 -m playwright install chrome
```

## Repository structure

```text
retail-price-scraper/
  README.md
  LICENSE
  requirements.txt
  .gitignore

  examples/
    retailer_keywords.csv

  scripts/
    v0_cvs_basic_bs4.py
    v1_cvs_real_chrome_working.py
    v2_cvs_h2_extractor.py
    v3_multi_retailer_championship.py
    v4_parallel_retailer_championship.py
    v5_hybrid_retailer_power_scraper.py
```

## Versions

### V0 — Basic CVS parser

File:

```text
scripts/v0_cvs_basic_bs4.py
```

Baseline CVS scraper using Playwright and BeautifulSoup.

Run:

```bash
python3 scripts/v0_cvs_basic_bs4.py
```

Output:

```text
~/Desktop/cvs_output_v0
```

---

### V1 — First working CVS Chrome version

File:

```text
scripts/v1_cvs_real_chrome_working.py
```

Uses installed Google Chrome with a persistent profile.

Main improvement:

```python
channel="chrome"
headless=False
```

Run:

```bash
python3 scripts/v1_cvs_real_chrome_working.py
```

Output:

```text
~/Desktop/cvs_output_v1
```

---

### V2 — CVS H2 product extractor

File:

```text
scripts/v2_cvs_h2_extractor.py
```

CVS-specific extractor. It starts from visible product headings like:

```html
<h2 role="heading" aria-level="2">Whole Milk, 1 Gallon</h2>
```

Then it climbs to the parent product card and extracts:

- product name
- price
- all visible prices in the card
- product URL
- image URL
- source URL

Run:

```bash
python3 scripts/v2_cvs_h2_extractor.py
```

Output:

```text
~/Desktop/cvs_output_v2
```

---

### V3 — Multi-retailer championship version

File:

```text
scripts/v3_multi_retailer_championship.py
```

First multi-retailer version.

Main features:

- multiple retailer configs
- pharmacy, big-box, clothing, and electronics groups
- same keyword, different keyword, or CSV keyword mode
- Best Buy support
- Best Buy United States country selection
- blocked-page logging
- progress saved after each retailer

Run:

```bash
python3 scripts/v3_multi_retailer_championship.py
```

Example:

```text
Choose retailers: electronics
Choose 1/2/3: 1
Keyword for all retailers: laptop
```

Output:

```text
output/retailer_championship_output/retailer_championship_prices.csv
```

---

### V4 — Parallel retailer championship version

File:

```text
scripts/v4_parallel_retailer_championship.py
```

V4 adds controlled parallel workers.

Main features:

- `MAX_WORKERS = 2`
- separate Chrome profile per retailer
- parallel-safe retailers run in parallel
- sensitive retailers run sequentially
- Walmart can pause for manual human verification
- Best Buy auto-selects United States
- output saved after each retailer finishes

Run:

```bash
python3 scripts/v4_parallel_retailer_championship.py
```

Example, only Best Buy:

```text
Choose retailers: electronics
Choose 1/2/3: 1
Keyword for all retailers: laptop
```

Example, Walmart manual verification:

```text
Choose retailers: 4
Choose 1/2/3: 1
Keyword for all retailers: water
```

If Walmart shows press-and-hold, complete it manually in Chrome, then return to Terminal and press Enter.

Output:

```text
output/retailer_championship_output/retailer_championship_prices_v4.csv
```

---

### V5 — Hybrid retailer power scraper

File:

```text
scripts/v5_hybrid_retailer_power_scraper.py
```

V5 combines the V3/V4 flow with a stronger extraction engine.

Main features:

- V4 parallel worker engine
- separate Chrome profile per retailer
- Best Buy United States country gate
- Walmart manual verification pause
- risk-based scheduling
- retailer strategy labels
- stronger blocked-page status reasons
- JSON-LD product extraction
- embedded app JSON extraction
- visible DOM product-card extraction
- CVS H2 fallback strategy
- run summary JSON

V5 extraction order:

```text
1. JSON-LD Product schema
2. Embedded application JSON
3. Retailer-specific extractor, if available
4. Visible DOM/card extractor
```

Run:

```bash
python3 scripts/v5_hybrid_retailer_power_scraper.py
```

Try Best Buy:

```text
Choose retailers: electronics
Choose 1/2/3: 1
Keyword for all retailers: laptop
```

Try low-risk retailers:

```text
Choose retailers: low
Choose 1/2/3: 1
Keyword for all retailers: jeans
```

Try all retailers:

```text
Choose retailers: all
Choose 1/2/3: 2
```

Output:

```text
output/retailer_championship_output/retailer_championship_prices_v5.csv
output/retailer_championship_output/run_summary_v5.json
```

## Keyword CSV mode

Use:

```text
examples/retailer_keywords.csv
```

Format:

```csv
retailer,keyword
CVS,milk
Walgreens,toothpaste
Walmart,water
Target,cereal
Best Buy,laptop
Macys,dress shirt
Old Navy,jeans
Gap,polo shirt
Kohls,hoodie
Nordstrom,sneakers
DSW,sandals
```

In the script, choose:

```text
Choose 1/2/3: 3
CSV path: examples/retailer_keywords.csv
```

## Outputs

Newer versions save inside the project:

```text
output/retailer_championship_output/
```

Typical files:

```text
retailer_championship_prices_v4.csv
retailer_championship_prices_v5.csv
run_summary_v5.json
debug_best_buy_laptop_v5.html
debug_best_buy_laptop_v5.txt
debug_best_buy_laptop_v5.png
debug_best_buy_laptop_v5.json
```

## Status values

V5 can return status values such as:

```text
ok_json_ld
ok_embedded_json
ok_dom
ok_cvs_h2
blocked_press_and_hold
blocked_captcha
blocked_human_verification
blocked_access_denied
no_rows_extracted
error: ...
```

These are useful for both price extraction and retailer accessibility analysis.

## Recommended `.gitignore`

Do not commit browser profiles or generated outputs.

```text
retailer_championship_profile/
retailer_parallel_profiles/
cvs_chrome_profile/
output/
__pycache__/
*.pyc
.DS_Store
```

## License

MIT License.
