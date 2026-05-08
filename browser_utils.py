import asyncio
import random
from camoufox.async_api import AsyncCamoufox
from config import PROFILE_DIR, WINDOW_SIZE, HEADLESS

async def get_browser_context():
    """
    Returns an AsyncCamoufox context manager with standard settings.
    """
    return AsyncCamoufox(
        headless=HEADLESS,
        persistent_context=True,
        user_data_dir=str(PROFILE_DIR),
        window=WINDOW_SIZE,
        firefox_user_prefs={'media.volume_scale': '0.0'}
    )

async def human_wiggle(page, element):
    """
    Simulates human-like mouse movement over an element.
    """
    box = await element.bounding_box()
    if box:
        for _ in range(3):
            x = box['x'] + random.randint(10, int(box['width'] - 10))
            y = box['y'] + random.randint(10, int(box['height'] - 10))
            await page.mouse.move(x, y, steps=5)
            await asyncio.sleep(0.2)

async def wait_for_network_settle(page, timeout=3000):
    """
    Wait for network to settle with a short timeout.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
