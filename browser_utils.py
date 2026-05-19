import asyncio
import random
from contextlib import asynccontextmanager
from cloakbrowser import launch_persistent_context_async
from config import PROFILE_DIR, WINDOW_SIZE, HEADLESS

@asynccontextmanager
async def get_browser_context():
    """
    Returns a CloakBrowser context manager with standard settings.
    """
    context = await launch_persistent_context_async(
        headless=HEADLESS,
        user_data_dir=str(PROFILE_DIR),
        viewport={'width': WINDOW_SIZE[0], 'height': WINDOW_SIZE[1]},
        args=['--mute-audio']
    )
    try:
        yield context
    finally:
        await context.close()

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
