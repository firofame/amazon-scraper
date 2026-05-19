import asyncio
import re
from pathlib import Path
from browser_utils import human_wiggle, wait_for_network_settle, get_browser_context
from config import SELECTORS, IMAGE_DIR

MAX_CONCURRENT_DOWNLOADS = 5
AMAZON_IMAGE_RE = re.compile(
    r'https?://m\.media-amazon\.com/images/I/[^"\'\s)]+?\.(?:jpe?g|png|webp)(?:\?[^"\'\s)]*)?',
    re.IGNORECASE,
)

def to_high_res_image_url(img_url):
    """Convert Amazon thumbnail/display URLs to full side-length image URLs."""
    sl_match = re.search(r'\._SL(\d+)_\.', img_url)
    if sl_match and int(sl_match.group(1)) >= 1000:
        return img_url

    return re.sub(
        r'(?:\._[^.]+_)?\.(jpe?g|png|webp)(\?.*)?$',
        lambda match: f"._SL1500_.{match.group(1)}{match.group(2) or ''}",
        img_url,
        flags=re.IGNORECASE,
    )

def amazon_image_key(img_url):
    """Return a stable key for one Amazon image regardless of size suffix."""
    clean_url = img_url.split("?", 1)[0]
    return re.sub(
        r'(?:\._[^.]+_)?\.(jpe?g|png|webp)$',
        lambda match: f".{match.group(1).lower()}",
        clean_url,
        flags=re.IGNORECASE,
    )

def image_url_quality(raw_url, high_res_url):
    """Prefer explicit high-res URLs found on the page over generated thumbnail upgrades."""
    raw_sl_match = re.search(r'\._SL(\d+)_\.', raw_url)
    high_res_sl_match = re.search(r'\._SL(\d+)_\.', high_res_url)
    raw_sl_size = int(raw_sl_match.group(1)) if raw_sl_match else 0
    high_res_sl_size = int(high_res_sl_match.group(1)) if high_res_sl_match else 0
    explicit_high_res = raw_sl_size >= 1000
    return (explicit_high_res, max(raw_sl_size, high_res_sl_size))

async def collect_displayed_image_urls(page):
    """Collect URLs from the currently displayed large gallery image."""
    return await page.evaluate(
        """
        () => {
            const imageRe = /https?:\\/\\/m\\.media-amazon\\.com\\/images\\/I\\/[^"'\\s)]+?\\.(?:jpe?g|png|webp)(?:\\?[^"'\\s)]*)?/gi;
            const selectors = [
                '#ivLargeImage img',
                '#ivStage img',
                '#ivStage .ivImage img',
                '#ivContainer img.a-dynamic-image',
                '#main-image'
            ];
            const urls = new Set();
            const add = (value) => {
                if (!value) return;
                for (const match of String(value).matchAll(imageRe)) {
                    urls.add(match[0]);
                }
            };

            for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                    const rect = el.getBoundingClientRect();
                    const visible = rect.width >= 100 && rect.height >= 100;
                    if (!visible) continue;

                    add(el.currentSrc);
                    for (const attr of ['src', 'data-src', 'data-old-hires', 'data-a-dynamic-image', 'srcset', 'style']) {
                        add(el.getAttribute(attr));
                    }
                }
            }

            return [...urls];
        }
        """
    )

async def collect_image_urls(page, thumb_selector):
    """Click each gallery thumbnail and collect the displayed large image URL."""
    best_urls = {}
    loc = page.locator(thumb_selector)
    total = await loc.count()

    async def add_displayed_urls():
        for raw_url in await collect_displayed_image_urls(page):
            if AMAZON_IMAGE_RE.search(raw_url):
                high_res_url = to_high_res_image_url(raw_url)
                key = amazon_image_key(high_res_url)
                quality = image_url_quality(raw_url, high_res_url)
                if key not in best_urls or quality > best_urls[key][0]:
                    best_urls[key] = (quality, high_res_url)

    await add_displayed_urls()

    for i in range(total):
        try:
            thumb = loc.nth(i)
            if await thumb.evaluate("el => el.classList.contains('placeholder')"):
                continue
            await thumb.scroll_into_view_if_needed(timeout=1000)
            await thumb.click(timeout=2500)
            await page.wait_for_timeout(300)
            await add_displayed_urls()
        except Exception:
            continue

    return [url for _, url in best_urls.values()]

async def download_single_image(page, img_url, index, image_dir):
    """Download a single image and save to disk."""
    try:
        img_url_clean = to_high_res_image_url(img_url)
        
        is_junk = any(x in img_url_clean.lower() for x in ["logo", "marketing", "prime", "badge", "sprite", ".gif"])
        if is_junk:
            return None

        img_response = await page.request.get(img_url_clean)
        if img_response.status == 200:
            ext = Path(img_url_clean).suffix.split('?')[0] or ".jpg"
            file_path = image_dir / f"product_image_{index}{ext}"
            file_path.write_bytes(await img_response.body())

            # Check image resolution
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    print(f"    ✅ Saved {file_path.name} ({img.size[0]}x{img.size[1]})", flush=True)
            except Exception:
                print(f"    ✅ Saved {file_path.name}", flush=True)
            return file_path
    except Exception as e:
        print(f"    ❌ Error downloading {img_url}: {e}", flush=True)
    return None

async def download_product_images(page, url, max_images=None, image_dir=None):
    """
    Downloads high-resolution images from an Amazon product page using an existing browser page.
    Uses parallel downloads after collecting URLs from thumbnail attributes.
    """
    if image_dir is None:
        image_dir = IMAGE_DIR
    print(f"Target URL: {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_for_network_settle(page)

    # Wait for product image
    image_selector = SELECTORS["product_image"]
    print(f"Waiting for product image ({image_selector})...", flush=True)
    img_element = await page.wait_for_selector(image_selector, timeout=20000)

    # Wiggle mouse for human-like behavior
    print("Wiggling mouse over image...", flush=True)
    await human_wiggle(page, img_element)

    gallery_opened = False

    # Try clicking the main image first
    try:
        print("Clicking product image...", flush=True)
        await page.click(image_selector)
        await asyncio.sleep(2)
        if await page.is_visible("#imageBlock") or await page.is_visible("#ivContainer"):
            gallery_opened = True
    except Exception:
        pass

    # Fallbacks for opening gallery
    if not gallery_opened:
        caption_selector = "#canvasCaption a"
        try:
            if await page.is_visible(caption_selector):
                await page.click(caption_selector)
                gallery_opened = True
        except Exception: pass

    if not gallery_opened:
        try:
            await page.click("#imgTagWrapperId img")
            gallery_opened = True
        except Exception: pass

    if not gallery_opened:
        print("All gallery triggers failed.", flush=True)
        return False

    print("Gallery opened. Collecting image URLs...", flush=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    # Find gallery container
    found_selector = None
    for selector in SELECTORS["gallery_container"]:
        try:
            await page.wait_for_selector(selector, timeout=5000)
            found_selector = selector
            break
        except Exception: continue

    # Thumbnails
    thumb_selector = None
    for t_selector in SELECTORS["thumbnails"]:
        try:
            await page.wait_for_selector(t_selector, timeout=3000)
            elements = await page.query_selector_all(t_selector)
            valid_elements = []
            for el in elements:
                if not await el.evaluate("el => el.classList.contains('placeholder')"):
                    valid_elements.append(el)
            if valid_elements:
                thumb_selector = t_selector
                break
        except Exception: continue

    if not thumb_selector:
        thumb_selector = f"{found_selector or 'body'} img"

    # Collect URLs by clicking each thumbnail and reading the displayed large image
    url_list = await collect_image_urls(page, thumb_selector)

    if not url_list:
        print("No image URLs found in gallery data.", flush=True)
        return False

    # Deduplicate and limit.
    seen = set()
    unique_urls = []
    for url in url_list:
        url_for_dedup = amazon_image_key(url)
        if url_for_dedup not in seen and not any(x in url.lower() for x in ["logo", "marketing", "prime", "badge", "sprite", ".gif"]):
            seen.add(url_for_dedup)
            unique_urls.append(url)
            if max_images is not None and len(unique_urls) >= max_images:
                break

    print(f"Downloading {len(unique_urls)} images concurrently...", flush=True)

    # Download concurrently with semaphore
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    async def download_with_semaphore(url, idx):
        async with semaphore:
            return await download_single_image(page, url, idx + 1, image_dir)

    tasks = [download_with_semaphore(url, i) for i, url in enumerate(unique_urls)]
    results = await asyncio.gather(*tasks)

    downloaded = [r for r in results if r is not None]
    print(f"Downloaded {len(downloaded)} images.", flush=True)

    return len(downloaded) > 0

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="The Amazon product URL")
    args = parser.parse_args()

    async with get_browser_context() as context:
        page = await context.new_page()
        await download_product_images(page, args.url)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess stopped.")
