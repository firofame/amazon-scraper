# Amazon Hybrid Scraper

A generic, configuration-driven hybrid scraper that combines HTML table extraction with Vision-AI analysis of product images. Designed to "dump everything" from Amazon product pages into a structured JSON database.

---

## How it works

```
amazon_scraper.py    → Crawls Amazon search & product pages
  ├─ downloader.py   → Automated gallery interaction & high-res image downloads
  └─ extractor.py    → Generic Vision-AI (Gemini) extraction from labels/stickers
    ↓
amazon_products.json → The final dataset (Hybrid: HTML + Vision data)
```

---

## Key Features

- **Generic Extraction**: No hardcoded fields. It uses `TABLE_RULES` in `config.py` to find any table-like data on the page.
- **Vision-AI Integration**: If enabled, it downloads high-res product photos and uses Gemini to "see" technical details (prefixed with `Vision_` in the JSON).
- **Rule-Based Config**: Easily adapt to new Amazon layouts or different product categories by editing `config.py`.
- **Human-Like Behavior**: Uses `browser_utils.py` for persistent profiles, human-like mouse wiggling, and network settling.

---

## Files

| File | Role |
|:---|:---|
| `amazon_scraper.py` | The main entry point. Orchestrates the search, download, and extraction loop. |
| `config.py` | Centralized settings: Selectors, `TABLE_RULES`, and `VISION_ENABLED` toggle. |
| `downloader.py` | "Modal-First" gallery strategy. Clicks thumbnails to capture `_SL1500_` URLs. |
| `extractor.py` | Generic Vision-AI module. Sends images to Gemini to read labels/spec sheets. |
| `browser_utils.py` | Playwright/Camoufox wrapper for stealth and reliability. |
| `amazon_products.json` | The resulting product database. |

---

## Setup

1. **Install dependencies**:
   ```bash
   pip install google-genai camoufox playwright Pillow
   python -m camoufox fetch
   ```

2. **Set API Key**:
   ```bash
   export GOOGLE_API_KEY="your_gemini_api_key"
   ```

3. **Configure Search**:
   Update the `SEARCH_URL` in `amazon_scraper.py` to your target category.

---

## Usage

```bash
# Run the full hybrid scrape
python3 amazon_scraper.py

# Run for existing products that are missing specs
python3 amazon_scraper.py specs-only
```

---

## Configuration (`config.py`)

- **`VISION_ENABLED`**: Set to `True` to perform AI image analysis.
- **`TABLE_RULES`**: A list of CSS selectors and parsing rules to extract specifications from various Amazon table layouts.
- **`HEADLESS`**: Set to `False` to watch the browser in action.
