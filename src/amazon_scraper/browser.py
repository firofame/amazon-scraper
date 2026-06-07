import logging
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright
from amazon_scraper.config import HEADLESS, CDP_URL

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_browser_context():
    """
    Gets a browser context.
    If HEADLESS is True (default), launches a local headless Chromium instance.
    If HEADLESS is False, connects to a running browser via CDP (e.g. Edge on port 9222).
    """
    async with async_playwright() as p:
        if HEADLESS:
            logger.info("Launching local headless Chromium browser...")
            try:
                browser = await p.chromium.launch(headless=True)
                # Set a standard desktop User-Agent to avoid issues
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                yield context
                await browser.close()
            except Exception as e:
                logger.critical(f"Failed to launch headless browser: {e}", exc_info=True)
                raise e
        else:
            logger.info(f"Connecting to browser via CDP at {CDP_URL}...")
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                yield context
            except Exception as e:
                logger.error(
                    f"Failed to connect to browser via CDP at {CDP_URL}. "
                    "Ensure Microsoft Edge/Chrome is running with --remote-debugging-port=9222"
                )
                raise e
