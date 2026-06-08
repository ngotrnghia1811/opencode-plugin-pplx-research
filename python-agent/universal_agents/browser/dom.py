"""DOM interaction helpers — find elements, type text, click buttons."""

import asyncio
import logging
import random

from playwright.async_api import Locator, Page

from ..core.exceptions import ElementNotFoundError

logger = logging.getLogger(__name__)


async def find_element(page: Page, selectors: list[str]) -> Locator:
    """Find the first visible element matching any of the selectors.

    Args:
        page: Playwright page.
        selectors: CSS selectors to try in priority order.

    Returns:
        Locator for the first matched element.

    Raises:
        ElementNotFoundError: If no selector matches a visible element.
    """
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible(timeout=500):
                return locator
        except Exception:
            continue

    raise ElementNotFoundError(
        f"None of {len(selectors)} selectors matched a visible element"
    )


def _has_non_ascii(s: str) -> bool:
    """Return True if *s* contains any character outside basic ASCII."""
    return any(ord(c) > 127 for c in s)


async def type_text(locator: Locator, text: str, human_like: bool = True) -> None:
    """Type text into an element with optional human-like delays.

    For ProseMirror editors, clears existing content first.
    For regular inputs/textareas, uses fill() for speed.

    Handles newlines (Shift+Enter in ProseMirror) and non-ASCII text
    (uses keyboard.insert_text for reliable CJK input).
    """
    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    is_contenteditable = await locator.evaluate(
        "el => el.getAttribute('contenteditable') === 'true' || el.classList.contains('ProseMirror')"
    )

    if is_contenteditable:
        # ProseMirror / contenteditable: focus, then type
        await locator.click()
        await asyncio.sleep(0.1)
        page = locator.page

        if human_like:
            # Split into lines and handle newlines as Shift+Enter
            lines = text.split("\n")
            for li, line in enumerate(lines):
                if line:
                    if _has_non_ascii(line):
                        # CJK / Unicode: insert_text dispatches a proper input
                        # event that ProseMirror handles reliably.
                        await page.keyboard.insert_text(line)
                    else:
                        # ASCII: type word-by-word for human-like feel
                        words = line.split(" ")
                        for wi, word in enumerate(words):
                            await locator.press_sequentially(
                                word, delay=random.randint(30, 80)
                            )
                            if wi < len(words) - 1:
                                await locator.press(" ")
                                await asyncio.sleep(random.uniform(0.03, 0.08))
                if li < len(lines) - 1:
                    await page.keyboard.press("Shift+Enter")
                    await asyncio.sleep(random.uniform(0.03, 0.08))
        else:
            await page.keyboard.insert_text(text)
    else:
        # Regular input/textarea: fill is faster and more reliable
        await locator.fill(text)


async def click_submit(page: Page, selectors: list[str]) -> None:
    """Click the submit/send button, falling back to Enter key.

    Args:
        page: Playwright page.
        selectors: CSS selectors for the submit button.
    """
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible(timeout=500):
                await locator.click()
                logger.debug("Clicked submit via: %s", selector)
                return
        except Exception:
            continue

    # Fallback: press Enter on the focused element
    logger.debug("No submit button found, pressing Enter")
    await page.keyboard.press("Enter")
