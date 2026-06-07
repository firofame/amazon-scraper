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
| `browser_utils.py` | Custom Chrome DevTools Protocol (CDP) client connecting to your browser on port 9222. |
| `amazon_products.json` | The resulting product database. |

---

## Setup

1. **Install dependencies**:
   Set up the virtual environment and install packages:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start Microsoft Edge / Chrome with Remote Debugging**:
   The scraper connects to an existing browser session on port `9222`. Open a browser with remote debugging enabled:
   
   * **Headed Mode** (Recommended for anti-bot bypass):
     ```bash
     flatpak run com.microsoft.Edge --remote-debugging-port=9222
     ```
     *(Or if installed natively: `microsoft-edge-stable --remote-debugging-port=9222`)*

   * **Headless Mode** (To run fully in the background):
     ```bash
     flatpak run com.microsoft.Edge --headless --remote-debugging-port=9222
     ```
     *(Or if installed natively: `microsoft-edge-stable --headless --remote-debugging-port=9222`)*

3. **Set API Key**:
   ```bash
   export GEMINI_API_KEY="your_gemini_api_key"
   ```

4. **Configure Search**:
   Update the `SEARCH_URL` in `amazon_scraper.py` to your target category.

---

## Usage

```bash
# Activate virtual environment
source venv/bin/activate

# Run the full hybrid scrape
python3 amazon_scraper.py

# Run for existing products that are missing specs
python3 amazon_scraper.py specs-only
```

---

## Configuration (`config.py`)

- **`VISION_ENABLED`**: Set to `True` to perform AI image analysis.
- **`TABLE_RULES`**: A list of CSS selectors and parsing rules to extract specifications from various Amazon table layouts.
