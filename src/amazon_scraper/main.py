import argparse
import asyncio
import json
import logging
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.async_api import Page

from amazon_scraper.browser import get_browser_context
from amazon_scraper.config import SELECTORS, TABLE_RULES, BASE_DIR, SAVE_INTERVAL, MAX_PAGES

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("amazon_scraper")

SEARCH_URL = (
    "https://www.amazon.in/s?k=ac&me=A3K8GDUW67973J"
)

def get_data_file(url: str) -> Path:
    """Derive a unique JSON filename from the search URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    parts = []
    keyword = params.get("k", [""])[0]
    if keyword:
        parts.append(re.sub(r'[^\w\-]', '_', keyword).strip('_'))
    seller = params.get("me", [""])[0]
    if seller:
        parts.append(seller)
    suffix = "_".join(parts) if parts else "default"
    return BASE_DIR / f"amazon_products_{suffix}.json"

def save_json_atomically(data_path: Path, data: list):
    """Saves data to a JSON file atomically using a temporary file."""
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=data_path.parent, delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=4, ensure_ascii=False)
        temp_name = tf.name
    Path(temp_name).replace(data_path)

async def scrape_listings(page: Page, search_url: str, max_pages: int = 999) -> list[dict]:
    """Scrape product cards from all search results pages."""
    products = []
    page_count = 1

    logger.info(f"Navigating to search URL: {search_url}")
    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

    while page_count <= max_pages:
        logger.info(f"--- Scraping Page {page_count} ---")
        try:
            await page.wait_for_selector(SELECTORS["search_result"], timeout=15000)
        except Exception:
            logger.warning("No search results found or timeout reached.")
            break

        results = await page.locator(SELECTORS["search_result"]).all()
        logger.info(f"Found {len(results)} items on page {page_count}")

        for result in results:
            try:
                asin = await result.get_attribute("data-asin")
                if not asin:
                    continue

                # Title extraction
                title_el = result.locator("h2 span, h2").first
                title = await title_el.inner_text() if await title_el.count() > 0 else "N/A"

                # Canonical URL construction
                url = f"https://www.amazon.in/dp/{asin}"

                # Price extraction
                price_el = result.locator(".a-price-whole").first
                price = await price_el.inner_text() if await price_el.count() > 0 else "N/A"

                # Rating extraction
                rating_el = result.locator("[data-cy='reviews-block'] span").first
                rating = await rating_el.inner_text() if await rating_el.count() > 0 else "N/A"
                if rating and "out of" in rating:
                    rating = rating.split(" ")[0]

                # Reviews extraction
                reviews_el = result.locator("span.s-underline-text, .a-size-base.s-underline-text").first
                reviews = await reviews_el.inner_text() if await reviews_el.count() > 0 else "0"
                reviews = re.sub(r'[^0-9]', '', reviews)
                if not reviews:
                    reviews = "0"

                if price != "N/A":
                    products.append({
                        "asin": asin,
                        "title": title.strip(),
                        "price": price.replace(",", "").strip(),
                        "rating": rating,
                        "reviews": reviews,
                        "url": url,
                    })
            except Exception as e:
                logger.error(f"Error processing item: {e}")

        # Check for next page button
        next_button = page.locator(SELECTORS["next_page"]).first
        if await next_button.count() > 0 and await next_button.is_visible():
            logger.info("Navigating to next page...")
            await next_button.click()
            page_count += 1
            await asyncio.sleep(3)
        else:
            logger.info("Last page reached or next button not found.")
            break

    unique = list({p["asin"]: p for p in products}.values())
    logger.info(f"Total products found in search: {len(unique)}")
    return unique

async def extract_specs(page: Page, product: dict, index: int, total: int) -> dict:
    """Extract specification tables and bullet points from the product page."""
    asin = product["asin"]
    url = f"https://www.amazon.in/dp/{asin}"
    product["url"] = url
    specs = {}

    try:
        logger.info(f"  [{index}/{total}] [{asin}] Navigating to product page...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(1)

        # Step 1: HTML Table Extraction
        for rule in TABLE_RULES:
            rows = await page.locator(rule["rows"]).all()
            for row in rows:
                k_el = row.locator(rule["key"]).first
                v_el = row.locator(rule["val"]).first
                if await k_el.count() > 0 and await v_el.count() > 0:
                    key = (await k_el.inner_text()).strip().rstrip(" \u200f:").replace("\u200e", "").strip()
                    val = (await v_el.inner_text()).strip().replace("\u200e", "").strip()
                    if (
                        key 
                        and val 
                        and key != val 
                        and key not in specs
                        and key.lower() != "customer reviews"
                        and not any(js_sig in val for js_sig in ["P.when", "function(", "var ", "const ", "let "])
                    ):
                        specs[key] = val

        # Step 2: Feature Bullets
        bullets = await page.locator(SELECTORS["feature_bullets"]).all()
        feature_list = []
        seen_bullets = set()
        for b in bullets:
            text = (await b.inner_text()).strip().replace("\u200e", "").strip()
            if text and text not in seen_bullets and len(text) > 5 and "›" not in text:
                seen_bullets.add(text)
                feature_list.append(text)
        if feature_list:
            specs["_features"] = feature_list

        product["specs"] = specs
        status = "✓" if len(specs) > 2 else "✗"
        logger.info(f"  [{index}/{total}] [{asin}] {status} {len(specs)} fields extracted")

    except Exception as e:
        logger.error(f"  [{index}/{total}] [{asin}] ✗ Error: {e}")
        product["specs"] = {}

    return product

async def run_scraper(mode: str = "full", search_url: str = SEARCH_URL, max_pages: int = 999):
    data_file = get_data_file(search_url)

    # Load existing database
    existing_products = []
    if data_file.exists():
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                existing_products = json.load(f)
            logger.info(f"Loaded {len(existing_products)} existing products from {data_file.name}")
        except Exception as e:
            logger.error(f"Failed to load existing data from {data_file.name}: {e}")

    existing_map = {p["asin"]: p for p in existing_products}

    async with get_browser_context() as context:
        page = await context.new_page()

        if mode == "specs-only":
            to_scrape = [p for p in existing_products if not p.get("specs")]
            total = len(to_scrape)
            logger.info(f"{total} products missing specs.")

            if not to_scrape:
                logger.info("All products already have specs!")
                return

            for i, product in enumerate(to_scrape):
                await extract_specs(page, product, i + 1, total)
                if (i + 1) % SAVE_INTERVAL == 0:
                    save_json_atomically(data_file, existing_products)
                    logger.info(f"Progress saved ({i+1}/{total})")
                await asyncio.sleep(1)

            save_json_atomically(data_file, existing_products)
            logger.info(f"✅ Updated {data_file.name}")
            return

        # Full mode
        active_products = await scrape_listings(page, search_url, max_pages)
        
        # Merge basic details from current scrape with existing specs
        all_products = []
        for p in active_products:
            asin = p["asin"]
            if asin in existing_map:
                existing_p = existing_map[asin]
                p["specs"] = existing_p.get("specs", {})
            all_products.append(p)

        # Log which products were removed
        active_asins = {p["asin"] for p in active_products}
        removed_asins = [asin for asin in existing_map if asin not in active_asins]
        if removed_asins:
            logger.info(f"Removing {len(removed_asins)} products that are no longer in search results: {', '.join(removed_asins)}")

        to_scrape = [p for p in all_products if not p.get("specs")]
        total = len(to_scrape)

        if total > 0:
            logger.info(f"Extracting specs from {total} products...")
            for i, product in enumerate(to_scrape):
                await extract_specs(page, product, i + 1, total)
                if (i + 1) % SAVE_INTERVAL == 0:
                    save_json_atomically(data_file, all_products)
                    logger.info(f"Progress saved ({i+1}/{total})")
                await asyncio.sleep(1)
        else:
            logger.info("All products already have specs!")

        save_json_atomically(data_file, all_products)
        logger.info(f"✅ Saved {len(all_products)} products to {data_file.name}")

def main():
    parser = argparse.ArgumentParser(description="Amazon Search and Product Spec Scraper")
    parser.add_argument("mode", nargs="?", default="full", choices=["full", "specs-only"], help="Scraping mode")
    parser.add_argument("--url", type=str, default=SEARCH_URL, help="Amazon search results URL to scrape")
    parser.add_argument("--pages", type=int, default=None, help="Number of pages to scrape")
    args = parser.parse_args()

    max_pages = args.pages if args.pages is not None else (MAX_PAGES or 999)

    try:
        asyncio.run(run_scraper(mode=args.mode, search_url=args.url, max_pages=max_pages))
    except KeyboardInterrupt:
        logger.info("Scraper interrupted by user.")
    except Exception as e:
        logger.critical(f"Unhandled crash: {e}", exc_info=True)

if __name__ == "__main__":
    main()
