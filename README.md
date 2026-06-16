# Amazon HTML Scraper

A generic, configuration-driven HTML scraper designed to extract technical specifications and feature bullets from Amazon product pages into a structured JSON database. It launches a Chromium browser using Playwright with custom desktop user-agent settings to browse pages and seamlessly extract data.

---

## How it works

```
uv run amazon-scraper    → Scrapes Amazon search results
  └─ src/
      └─ amazon_scraper/
          ├─ main.py     → Orchestrates the search and extraction loop
          ├─ browser.py  → Launches Playwright Chromium with custom headers/User-Agent
          └─ config.py   → Selectors, table rules, and search page config
```

---

## Key Features

- **Generic Extraction**: No hardcoded product spec fields. It parses data using `TABLE_RULES` in [config.py](src/amazon_scraper/config.py) to extract all key-value specifications found on target pages.
- **Dynamic Output Filenames**: Automatically extracts the search query (`k`) and seller ID (`me`) from the search URL to save results in distinct JSON files (e.g., `amazon_products_ac_A3K8GDUW67973J.json`).
- **Atomic File Saving**: Progress is saved atomically during the run, eliminating the risk of database corruption if the scraper is interrupted.
- **Resilient Navigation & Extraction**: Uses customizable table extraction rules to parse specifications from various Amazon product layouts.
- **Modern Python Standards**: Built as an installable package using `pyproject.toml` and managed with `uv`.

---

## Setup & Installation

1. **Install `uv`** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Playwright Browsers**:
   The scraper utilizes Playwright. Install the required Chromium browser using:
   ```bash
   uv run playwright install chromium
   ```

3. **Configure Environment Variables (Optional)**:
   Create a `.env` file in the root directory:
   ```env
   # Set to False to view the browser window while scraping
   HEADLESS=True

   # Default maximum search result pages to scan
   MAX_PAGES=5
   ```

---

## Usage

You do not need to activate any virtual environments manually; `uv` handles everything transparently:

### Scrape a Search URL

```bash
# Run the full scraper (listings scan + spec extraction)
uv run amazon-scraper --url "https://www.amazon.in/s?k=ac&me=A3K8GDUW67973J"

# Limit the number of pages to scrape
uv run amazon-scraper --url "https://www.amazon.in/s?k=aa+battery" --pages 2

# Run with the default search URL (configured in main.py)
uv run amazon-scraper
```

### Resume/Extract Missing Specs Only

If you already have a product database but some products are missing technical specifications, you can fetch only the specs:

```bash
# Fetch missing specs for the default database
uv run amazon-scraper specs-only

# Fetch missing specs for a custom search database
uv run amazon-scraper specs-only --url "https://www.amazon.in/s?k=aa+battery"
```

---

## Configuration (`src/amazon_scraper/config.py`)

- **`HEADLESS`**: Set via `HEADLESS` environment variable (defaults to `True`). Controls whether Chromium runs headlessly or headfully.
- **`MAX_PAGES`**: Default maximum pages to scan. Set via `MAX_PAGES` environment variable (defaults to `None`/no limit if not set).
- **`SAVE_INTERVAL`**: How often progress is saved to the JSON file (defaults to `1` product).
- **`TABLE_RULES`**: List of target CSS selectors and rules used to extract tabular technical details from Amazon's different layout styles.
- **`SELECTORS`**: Base selectors for finding search result items, next page links, and product feature bullet points.

