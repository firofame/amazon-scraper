from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.resolve()
IMAGE_DIR = BASE_DIR / "images"
STICKER_DIR = BASE_DIR / "verified_labels"
DATA_FILE = BASE_DIR / "amazon_products.json"
PROFILE_DIR = Path.home() / ".cloakbrowser-profile"

# Browser Settings
WINDOW_SIZE = (1100, 700)
HEADLESS = True
PARALLEL_PAGES = 2  # Concurrent browser pages for bulk verification

# Extraction Settings
MODEL_ID = "gemini-3.1-flash-lite" 
VISION_ENABLED = False  # Set to False to skip image analysis and save time/cost
MAX_IMAGES_PER_PRODUCT = None # Set to None to download all available images
SAVE_INTERVAL = 1 # Save progress to JSON after this many products

# Amazon Selectors (Commonly reused)
SELECTORS = {
    "product_image": "#landingImage",
    "gallery_container": ["#ivContainer", ".a-popover-content", "#unified-gallery", "#imageBlock"],
    "thumbnails": [
        "#ivThumbs .ivThumb", 
        ".ivThumbs .ivThumb",
        "#ivThumbs .ivRow .ivThumb",
        ".ivThumb", 
        "#altImages .a-button-thumbnail", 
    ],
    "high_res_image": ["#ivLargeImage img", ".a-stretch-vertical", ".a-dynamic-image", "#main-image"],
    "search_result": "[data-component-type='s-search-result']",
    "next_page": ".s-pagination-next:not(.s-pagination-disabled)"
}

# Extraction Strategies
TABLE_RULES = [
    {"rows": "tr.a-spacing-small", "key": "td.a-span3 span", "val": "td.a-span9 span"},
    {"rows": ".prodDetTable tr, #productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr", "key": "th", "val": "td"},
    {"rows": "table.a-keyvalue tr, #prodDetails tr, .a-normal.a-spacing-micro tr", "key": "th, .a-text-bold", "val": "td, span:not(.a-text-bold)"}
]
