import asyncio
import random
import logging
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Page, ElementHandle

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_browser_context(cdp_url: str = "http://127.0.0.1:9222"):
    """Connects to a running browser instance via CDP."""
    async with async_playwright() as p:
        logger.info(f"Connecting to browser via CDP at {cdp_url}...")
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            yield context
        except Exception as e:
            logger.error(
                f"Failed to connect to browser at {cdp_url}. "
                "Ensure Microsoft Edge/Chrome is running with --remote-debugging-port=9222"
            )
            raise e

async def human_wiggle(page: Page, element: ElementHandle):
    """Simulates a human-like mouse wiggle over a target element."""
    try:
        box = await element.bounding_box()
        if box:
            for _ in range(3):
                x = box['x'] + random.randint(5, max(6, int(box['width']) - 5))
                y = box['y'] + random.randint(5, max(6, int(box['height']) - 5))
                await page.mouse.move(x, y, steps=6)
                await asyncio.sleep(0.15)
    except Exception as e:
        logger.warning(f"Could not perform mouse wiggle: {e}")

async def wait_for_network_settle(page: Page, timeout: int = 3000):
    """Waits for network activity to quiet down."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
