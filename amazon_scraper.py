import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin
from browser_utils import get_browser_context
from config import SELECTORS, TABLE_RULES, DATA_FILE, VISION_ENABLED, IMAGE_DIR
from downloader import download_product_images
from extractor import extract_label_from_images

SEARCH_URL = (
    "https://www.amazon.in/s?k=ac&me=A3K8GDUW67973J"
)


async def scrape_listings(page):
    """Scrape product cards from all search results pages."""
    products = []
    page_count = 1

    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    
    while page_count <= 3:
        print(f"\n--- Scraping Page {page_count} ---")
        try:
            await page.wait_for_selector(SELECTORS["search_result"], timeout=15000)
        except Exception:
            print("No results found or timeout.")
            break

        results = await page.query_selector_all(SELECTORS["search_result"])
        print(f"Found {len(results)} items on page {page_count}")

        for result in results:
            try:
                asin = await result.get_attribute("data-asin")
                if not asin:
                    continue

                title_el = await result.query_selector("h2 span, h2")
                title = await title_el.inner_text() if title_el else "N/A"

                link_el = await result.query_selector("h2 a, .a-link-normal.s-no-outline")
                href = await link_el.get_attribute("href") if link_el else None
                url = urljoin("https://www.amazon.in", href.split("?")[0]) if href else "N/A"

                price_el = await result.query_selector(".a-price-whole")
                price = await price_el.inner_text() if price_el else "N/A"

                rating_el = await result.query_selector("[data-cy='reviews-block'] span")
                rating = await rating_el.inner_text() if rating_el else "N/A"
                if rating and "out of" in rating:
                    rating = rating.split(" ")[0]

                reviews_el = await result.query_selector("span.s-underline-text, .a-size-base.s-underline-text")
                reviews = await reviews_el.inner_text() if reviews_el else "0"
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
                print(f"  Error processing item: {e}")

        next_button = await page.query_selector(SELECTORS["next_page"])
        if next_button:
            print("Navigating to next page...")
            await next_button.click()
            page_count += 1
            await asyncio.sleep(3)
        else:
            print("Last page reached.")
            break

    unique = list({p["asin"]: p for p in products}.values())
    print(f"\nTotal: {len(unique)} unique products from search results.")
    return unique


async def extract_specs(page, product, index, total):
    """Hybrid extractor: Combines HTML table scraping with Vision-AI analysis."""
    asin = product["asin"]
    url = product["url"]
    specs = {}

    try:
        # Step 1: Download Images (if vision enabled)
        product_image_dir = IMAGE_DIR / asin
        if VISION_ENABLED:
            print(f"  [{asin}] Downloading images...", end="", flush=True)
            await download_product_images(page, url, max_images=5, image_dir=product_image_dir)
            print(" Done.", flush=True)
        else:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(1)

        # Step 2: HTML Table Extraction
        for rule in TABLE_RULES:
            rows = await page.query_selector_all(rule["rows"])
            for row in rows:
                k_el = await row.query_selector(rule["key"])
                v_el = await row.query_selector(rule["val"])
                if k_el and v_el:
                    key = (await k_el.inner_text()).strip().rstrip(" \u200f:").replace("\u200e", "").strip()
                    val = (await v_el.inner_text()).strip().replace("\u200e", "").strip()
                    if key and val and key != val and key not in specs:
                        specs[key] = val

        # Step 3: Feature Bullets
        bullets = await page.query_selector_all("#feature-bullets li span, .a-list-item")
        feature_list = []
        seen_bullets = set()
        for b in bullets:
            text = (await b.inner_text()).strip().replace("\u200e", "").strip()
            if text and text not in seen_bullets and len(text) > 5 and "›" not in text:
                seen_bullets.add(text)
                feature_list.append(text)
        if feature_list:
            specs["_features"] = feature_list

        # Step 4: Vision Extraction
        if VISION_ENABLED:
            print(f"  [{asin}] AI Analysis...", end="", flush=True)
            vision_data, _, _ = await extract_label_from_images(image_dir=product_image_dir, verbose=False)
            if vision_data and "error" not in vision_data:
                # Merge vision data into specs
                for k, v in vision_data.items():
                    if k not in ["clarity_score", "info_bbox"] and k not in specs:
                        specs[f"Vision_{k}"] = v
            print(" Done.", flush=True)

        product["specs"] = specs
        status = "✓" if (len(specs) > 2) else "✗"
        print(f"  [{index}/{total}] [{asin}] {status} {len(specs)} fields", flush=True)

    except Exception as e:
        print(f"  [{index}/{total}] [{asin}] ✗ Error: {e}", flush=True)
        product["specs"] = {}

    return product


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    if mode == "specs-only" and DATA_FILE.exists():
        # Skip listing scrape, just load existing and extract specs
        with open(DATA_FILE, "r") as f:
            products = json.load(f)
        # Filter to those missing specs
        to_scrape = [p for p in products if not p.get("specs")]
        print(f"Loaded {len(products)} products, {len(to_scrape)} missing specs.")
        
        if not to_scrape:
            print("All products already have specs!")
            return
        
        async with await get_browser_context() as context:
            page = await context.new_page()
            total = len(to_scrape)
            for i, product in enumerate(to_scrape):
                print(f"[{i+1}/{total}]", end="", flush=True)
                await extract_specs(page, product, i + 1, total)
                await asyncio.sleep(1)
            
            # Save back
            with open(DATA_FILE, "w") as f:
                json.dump(products, f, indent=4, ensure_ascii=False)
            print(f"\n✅ Updated {DATA_FILE.name}")
        return

    # Full mode: scrape listings + specs
    async with await get_browser_context() as context:
        page = await context.new_page()

        # Step 1: Scrape listings
        products = await scrape_listings(page)

        # Step 2: Extract specs one by one
        total = len(products)
        print(f"\n{'='*50}")
        print(f"Extracting specs from {total} product pages (sequential)...")
        print(f"{'='*50}\n")

        for i, product in enumerate(products):
            print(f"[{i+1}/{total}]", end="", flush=True)
            await extract_specs(page, product, i + 1, total)
            # Save progress every 20 products
            if (i + 1) % 20 == 0:
                with open(DATA_FILE, "w") as f:
                    json.dump(products, f, indent=4, ensure_ascii=False)
                print(f"  💾 Progress saved ({i+1}/{total})")
            await asyncio.sleep(1)

        # Final save
        with open(DATA_FILE, "w") as f:
            json.dump(products, f, indent=4, ensure_ascii=False)

        print(f"\n✅ Saved {len(products)} products to {DATA_FILE.name}")


if __name__ == "__main__":
    asyncio.run(main())
