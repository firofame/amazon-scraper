import itertools
import os
import sys
import json
import asyncio
import re
import threading
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types
from config import MODEL_ID, IMAGE_DIR

API_KEYS = [v for k, v in sorted(os.environ.items()) if k.startswith("GEMINI_API_KEY_")]
if not API_KEYS:
    key = os.environ.get("GEMINI_API_KEY", "")
    API_KEYS = [key] if key else []
if not API_KEYS:
    raise RuntimeError("No GEMINI_API_KEY or GEMINI_API_KEY_N environment variables found")

_clients = [genai.Client(api_key=k) for k in API_KEYS]
_client_cycle = itertools.cycle(_clients)
_client_lock = threading.Lock()

def get_client():
    with _client_lock:
        return next(_client_cycle)

MAX_CONCURRENT_ANALYSES = 2
ANALYSIS_REQUESTS_PER_MINUTE = 15

# Module-level singletons — shared across concurrent extraction tasks
_rate_limiter = None
_semaphore = None

def _get_shared_resources():
    """Lazy-init shared rate limiter and semaphore (safe for module import)."""
    global _rate_limiter, _semaphore
    if _rate_limiter is None:
        _rate_limiter = AsyncRateLimiter(ANALYSIS_REQUESTS_PER_MINUTE)
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)
    return _semaphore, _rate_limiter

class AsyncRateLimiter:
    def __init__(self, requests_per_minute):
        self.min_interval = 60 / requests_per_minute
        self._lock = asyncio.Lock()
        self._next_request_at = 0

    async def wait(self):
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if now < self._next_request_at:
                await asyncio.sleep(self._next_request_at - now)
                now = loop.time()
            self._next_request_at = now + self.min_interval

def retry_delay_seconds(error):
    match = re.search(r"retryDelay': '(\d+)s'", str(error))
    if match:
        return int(match.group(1)) + 1
    match = re.search(r"retry in ([\d.]+)s", str(error), re.IGNORECASE)
    if match:
        return float(match.group(1)) + 1
    return None

async def analyze_single_image(client, img_path, prompt, semaphore, rate_limiter, verbose=True):
    """Analyze a single image using the AI model with semaphore rate limiting."""
    async with semaphore:
        try:
            if verbose: print(f"   Analyzing {img_path.name}...", file=sys.stderr, flush=True)

            with open(img_path, "rb") as f:
                img_data = f.read()

            mime_type = "image/jpeg"
            if img_path.suffix.lower() == ".png": mime_type = "image/png"
            elif img_path.suffix.lower() == ".webp": mime_type = "image/webp"

            for attempt in range(2):
                try:
                    await rate_limiter.wait()
                    response = await client.aio.models.generate_content(
                        model=MODEL_ID,
                        contents=[prompt, types.Part.from_bytes(data=img_data, mime_type=mime_type)],
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    break
                except Exception as e:
                    delay = retry_delay_seconds(e)
                    if attempt == 0 and delay:
                        if verbose: print(f"Rate limit hit for {img_path.name}; retrying in {delay:.1f}s...", file=sys.stderr)
                        await asyncio.sleep(delay)
                        continue
                    raise

            result_data = json.loads(response.text.strip())
            if "error" not in result_data:
                result_data["_img_path"] = str(img_path)
                return result_data
        except Exception as e:
            if verbose: print(f"Error analyzing {img_path.name}: {e}", file=sys.stderr)
    return None

async def extract_label_from_images(image_dir=IMAGE_DIR, verbose=True):
    """
    Analyzes ALL images in a directory concurrently, picks the clearest BEE label,
    crops it, and extracts data.
    Returns (best_data, best_img_path, cropped_img_path)
    """
    client = get_client()

    if not image_dir.exists():
        if verbose: print(f"Error: {image_dir} not found.", file=sys.stderr)
        return None, None, None

    image_files = sorted(list(image_dir.glob("product_image_*.*")))
    if not image_files:
        if verbose: print("No images found to analyze.", file=sys.stderr)
        return None, None, None

    prompt = """
    Analyze this image and extract all visible technical specifications, numerical values, 
    and product details from any labels, stickers, or specification sheets.

    1. Extract every key-value pair found (e.g., "Wattage": "1500W", "Model": "XYZ-123").
    2. Provide a 'clarity_score' (0 to 10) based on how legible the text is.
    3. Provide an 'info_bbox' as [ymin, xmin, ymax, xmax] in normalized coordinates (0-1000) 
       for the most data-rich area (label, sticker, or spec table).

    Return ONLY a valid JSON object.
    If no technical info is visible, respond with {"error": "NO_SPECS_VISIBLE"}.
    """

    semaphore, rate_limiter = _get_shared_resources()

    if verbose:
        print(
            f"   Analyzing {len(image_files)} images "
            f"(max {ANALYSIS_REQUESTS_PER_MINUTE} AI requests/min)...",
            file=sys.stderr,
            flush=True,
        )

    tasks = [analyze_single_image(client, img_path, prompt, semaphore, rate_limiter, verbose) for img_path in image_files]
    results = await asyncio.gather(*tasks)

    valid_results = [r for r in results if r is not None and "error" not in r]

    if not valid_results:
        return {"error": "NO_SPECS_FOUND_IN_ANY_IMAGE"}, None, None

    # Pick the best result based on clarity_score
    best_result = max(valid_results, key=lambda x: x.get("clarity_score", 0))
    best_img_path = best_result.pop("_img_path")

    # Attempt cropping
    cropped_path = None
    bbox = best_result.get("info_bbox")
    if bbox and len(bbox) == 4:
        try:
            with Image.open(best_img_path) as img:
                w, h = img.size
                # Convert normalized to pixel coordinates
                ymin, xmin, ymax, xmax = bbox
                left = (xmin / 1000) * w
                top = (ymin / 1000) * h
                right = (xmax / 1000) * w
                bottom = (ymax / 1000) * h

                # Add 5% padding
                pad_w = (right - left) * 0.05
                pad_h = (bottom - top) * 0.05
                left = max(0, left - pad_w)
                top = max(0, top - pad_h)
                right = min(w, right + pad_w)
                bottom = min(h, bottom + pad_h)

                cropped_img = img.crop((left, top, right, bottom))
                cropped_path = Path(best_img_path).parent / f"cropped_{Path(best_img_path).name}"
                cropped_img.save(cropped_path)
                if verbose: print(f"   ✨ Cropped data area from {Path(best_img_path).name} (Score: {best_result.get('clarity_score')})", file=sys.stderr)
        except Exception as e:
            if verbose: print(f"   ⚠️ Cropping failed: {e}", file=sys.stderr)

    return best_result, Path(best_img_path), cropped_path

def main():
    output_json = "--json" in sys.argv
    result, img_path, cropped_path = asyncio.run(extract_label_from_images(verbose=not output_json))

    if result:
        if not output_json:
            if img_path: print(f"Best sticker found in: {img_path.name}")
            if cropped_path: print(f"Cropped version saved to: {cropped_path.name}")
        print(json.dumps(result, indent=2 if not output_json else None))
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
