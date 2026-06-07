import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_FILE = BASE_DIR / "amazon_products.json"

# Browser Settings
# Set HEADLESS=False in your environment or here to connect to your Edge browser on port 9222
HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"
CDP_URL = os.getenv("CDP_URL", "http://127.0.0.1:9222")

# Scraper Configurations
SAVE_INTERVAL = 1
MAX_PAGES = 3

# Amazon Selectors
SELECTORS = {
    "search_result": "[data-component-type='s-search-result']",
    "next_page": ".s-pagination-next:not(.s-pagination-disabled)",
    "feature_bullets": "#feature-bullets li span, .a-list-item"
}

# Extraction Strategies (Table layouts for technical details)
TABLE_RULES = [
    {"rows": "tr.a-spacing-small", "key": "td.a-span3 span", "val": "td.a-span9 span"},
    {"rows": ".prodDetTable tr, #productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr", "key": "th", "val": "td"},
    {"rows": "table.a-keyvalue tr, #prodDetails tr, .a-normal.a-spacing-micro tr", "key": "th, .a-text-bold", "val": "td, span:not(.a-text-bold)"}
]
