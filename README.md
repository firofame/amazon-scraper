# Amazon HTML Scraper

A generic, configuration-driven HTML scraper designed to extract technical specifications and feature bullets from Amazon product pages into a structured JSON database. It connects to your active browser session on port `9222` to seamlessly bypass anti-bot systems.

---

## How it works

```
uv run amazon-scraper    → Scrapes Amazon search results
  └─ src/
      └─ amazon_scraper/
          ├─ main.py     → Orchestrates the search and extraction loop
          ├─ browser.py  → Connects to Edge/Chrome via native Playwright CDP
          └─ config.py   → Selectors, table rules, and search page config
```

---

## Key Features

- **Generic Extraction**: No hardcoded product spec fields. It parses data using `TABLE_RULES` in `src/amazon_scraper/config.py` to extract all key-value specifications found on target pages.
- **Anti-Bot Bypass**: Connects to an existing, authenticated browser instance on port `9222` using native Playwright Chromium CDP.
- **Modern Python Standards**: Built as an installable package using `pyproject.toml` and managed with `uv`.
- **Atomic File Saving**: Progress is saved atomically during the run, eliminating the risk of database corruption if the scraper is interrupted.

---

## Setup & Installation

1. **Install `uv`** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Start Microsoft Edge / Chrome with Remote Debugging Enabled**:
   The scraper connects to your running browser session on port `9222`. Open the browser via terminal:
   
   * **Microsoft Edge (Flatpak)**:
     ```bash
     flatpak run com.microsoft.Edge --remote-debugging-port=9222
     ```
   * **Microsoft Edge (Native)**:
     ```bash
     microsoft-edge-stable --remote-debugging-port=9222
     ```
   * **Chrome**:
     ```bash
     google-chrome --remote-debugging-port=9222
     ```

---

## Usage

You do not need to activate any virtual environments manually; `uv` handles everything transparently:

```bash
# Run the full scraper (listings scan + spec extraction)
uv run amazon-scraper

# Extract missing specs for products already in your JSON database
uv run amazon-scraper specs-only
```

---

## Configuration (`src/amazon_scraper/config.py`)

- **`MAX_PAGES`**: Maximum search result pages to scan.
- **`SAVE_INTERVAL`**: Save progress to the JSON file after every $N$ scraped products.
- **`TABLE_RULES`**: List of target CSS selectors and rules used to extract tabular technical details from Amazon's different layout styles.
