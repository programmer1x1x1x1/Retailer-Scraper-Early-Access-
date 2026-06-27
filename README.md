# Retail Price Scraper Versions

This repository contains four scraper versions developed iteratively for product-price extraction from retail search pages.

The scripts use Playwright. Later versions use installed Google Chrome in headed mode with a persistent profile.

## Versions

### V0 — Basic CVS parser

File:

```text
scripts/v0_cvs_basic_bs4.py
```

Simple CVS keyword scraper using Playwright and BeautifulSoup.

This version is useful as a baseline, but it may miss dynamically rendered products.

### V1 — First working CVS Chrome version

File:

```text
scripts/v1_cvs_real_chrome_working.py
```

Uses installed Google Chrome through Playwright:

```python
channel="chrome"
headless=False
```

It also uses a persistent profile folder so cookies/session data can persist across runs.

### V2 — CVS H2 product extractor

File:

```text
scripts/v2_cvs_h2_extractor.py
```

CVS-specific extractor that starts from product headings such as:

```html
<h2 role="heading" aria-level="2">Whole Milk, 1 Gallon</h2>
```

Then it climbs to the parent product card and extracts price, product URL, image URL, and source URL.

### V3 — Multi-retailer championship version

File:

```text
scripts/v3_multi_retailer_championship.py
```

Supports multiple retailers and different keywords per retailer. It records blocked/error status and saves progress after every retailer.

Included retailer groups:

- pharmacy
- bigbox
- clothing

## Install

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium chrome
```

## Run V0

```bash
python3 scripts/v0_cvs_basic_bs4.py
```

## Run V1

```bash
python3 scripts/v1_cvs_real_chrome_working.py
```

## Run V2

```bash
python3 scripts/v2_cvs_h2_extractor.py
```

## Run V3

```bash
python3 scripts/v3_multi_retailer_championship.py
```

For V3, you can choose:

```text
all
clothing
pharmacy
bigbox
1,2,6,7
```

Then choose keyword mode:

```text
1 = same keyword for all retailers
2 = different keyword for each retailer
3 = load keywords from CSV
```

## CSV keyword mode

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
Macys,dress shirt
Old Navy,jeans
Gap,polo shirt
Kohls,hoodie
Nordstrom,sneakers
DSW,sandals
```

## Output locations

V0 output:

```text
~/Desktop/cvs_output_v0
```

V1 output:

```text
~/Desktop/cvs_output_v1
```

V2 output:

```text
~/Desktop/cvs_output_v2
```

V3 output:

```text
~/Desktop/retailer_championship_output
```

## Notes

Some retailers block automated browser sessions or limit repeated loading. The scripts do not bypass access controls. They record blocked/error status and continue where possible.

For sensitive retailers, V3 uses low or zero "load more" clicks.

## License

MIT License.
