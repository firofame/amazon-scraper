import logging
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright
from amazon_scraper.config import HEADLESS

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_browser_context():
    """
    Gets a browser context by launching a local Chromium instance.
    If HEADLESS is True (default), launches in headless mode.
    If HEADLESS is False, launches in headful mode.
    """
    async with async_playwright() as p:
        logger.info(f"Launching local Chromium browser (headless={HEADLESS})...")
        try:
            browser = await p.chromium.launch(headless=HEADLESS)
            # Set a standard desktop User-Agent to avoid issues
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            yield context
            await browser.close()
        except Exception as e:
            logger.critical(f"Failed to launch browser: {e}", exc_info=True)
            raise e
