"""Response stabilization logic — detects when a new response is complete."""

import logging
import subprocess
import sys
import time

from playwright.async_api import Page

from ..core.config import BrowserConfig
from ..core.exceptions import ResponseTimeoutError

logger = logging.getLogger(__name__)


class ResponseDetector:
    """Waits for a new response to appear and stabilize in the DOM."""

    def __init__(self, config: BrowserConfig):
        self.timeout = config.timeout
        self.check_interval = config.response_check_interval
        self.required_stable_checks = config.required_stable_checks

    async def wait_for_new_response(
        self,
        page: Page,
        response_selectors: list[str],
        count_before: int,
        selector_hint: str | None = None,
    ) -> str:
        """Wait for a new response element to appear and its content to stabilize.

        Args:
            page: Playwright page.
            response_selectors: CSS selectors for response elements (tried in order).
            count_before: Number of response elements before submitting the query.
            selector_hint: If provided, use this selector (for consistency with
                count_responses). Otherwise auto-detect.

        Returns:
            The stabilized text content of the new response.

        Raises:
            ResponseTimeoutError: If no new response appears or content doesn't stabilize.
        """
        start = time.monotonic()
        deadline = start + self.timeout

        # Use hint from count_responses (ensures consistent selector),
        # otherwise fall back to the preferred selector.
        selector = selector_hint or response_selectors[0]

        # Phase 1: Wait for element count to increase
        while time.monotonic() < deadline:
            count_now = await page.locator(selector).count()
            if count_now > count_before:
                break
            await page.wait_for_timeout(int(self.check_interval * 1000))
        else:
            raise ResponseTimeoutError(
                f"No new response appeared within {self.timeout}s "
                f"(count stayed at {count_before})"
            )

        # Phase 2: Wait for content to stabilize
        previous_text = ""
        stable_count = 0

        while time.monotonic() < deadline:
            current_text = await self._get_last_response_text(page, selector)

            if current_text and current_text == previous_text:
                stable_count += 1
                if stable_count >= self.required_stable_checks:
                    elapsed = (time.monotonic() - start) * 1000
                    logger.info(
                        "Response stabilized after %.0fms (%d chars)",
                        elapsed,
                        len(current_text),
                    )
                    # Try to get properly formatted text via copy button
                    formatted = await self._copy_response_via_button(page, selector)
                    if formatted:
                        logger.info(
                            "Got formatted response via copy button (%d chars)",
                            len(formatted),
                        )
                        return formatted
                    return current_text
            else:
                stable_count = 0

            previous_text = current_text
            await page.wait_for_timeout(int(self.check_interval * 1000))

        # Return whatever we have if timeout while stabilizing
        if previous_text:
            logger.warning("Response did not fully stabilize, returning partial content")
            return previous_text

        raise ResponseTimeoutError(
            f"Response content did not stabilize within {self.timeout}s"
        )

    async def count_responses(
        self, page: Page, response_selectors: list[str]
    ) -> tuple[int, str]:
        """Count current response elements using the first working selector.

        Returns:
            Tuple of (count, selector_used).
        """
        selector = await self._find_working_selector(page, response_selectors)
        count = await page.locator(selector).count()
        return count, selector

    async def _find_working_selector(self, page: Page, selectors: list[str]) -> str:
        """Return the first selector that matches at least one element."""
        for selector in selectors:
            count = await page.locator(selector).count()
            if count > 0:
                return selector
        # Fallback: return the first selector and let it potentially match later
        return selectors[0]

    async def _get_last_response_text(self, page: Page, selector: str) -> str:
        """Get the text content of the last element matching the selector.

        Uses ``inner_text()`` (JS ``innerText``) instead of ``text_content()``
        (JS ``textContent``) so that block-element boundaries (``<p>``, ``<br>``,
        ``<div>``, etc.) produce newlines.  ``text_content()`` concatenates all
        text nodes without any whitespace insertion, producing a single flat
        line — which is the root cause of the "no newlines" bug on pages where
        the Copy-button extraction fails.
        """
        locator = page.locator(selector).last
        try:
            return (await locator.inner_text()) or ""
        except Exception:
            return ""

    @staticmethod
    def _read_clipboard() -> str:
        """Read current system clipboard contents."""
        try:
            if sys.platform == "darwin":
                r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
                return r.stdout if r.returncode == 0 else ""
            elif sys.platform.startswith("linux"):
                r = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.stdout if r.returncode == 0 else ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _clear_clipboard() -> None:
        """Write a known sentinel value to the clipboard so we can detect changes."""
        sentinel = "__CLIPBOARD_CLEARED__"
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["pbcopy"], input=sentinel.encode("utf-8"),
                    check=True, timeout=5,
                )
            elif sys.platform.startswith("linux"):
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=sentinel.encode("utf-8"),
                    check=True, timeout=5,
                )
        except Exception:
            pass

    async def _copy_response_via_button(self, page: Page, selector: str) -> str | None:
        """Click the copy button on the last response to get formatted markdown.

        Gemini shows a copy button on each response. Clicking it copies the
        properly formatted markdown (with newlines, headers, etc.) to the
        browser clipboard.

        Extraction strategy (tried in order):
        1. **JS writeText hook** — monkey-patch ``navigator.clipboard.writeText``
           before clicking Copy, then read the captured text.
        2. **navigator.clipboard.readText()** — read from the browser clipboard
           directly (works if Gemini uses ``document.execCommand('copy')`` or
           another path that bypasses our hook).
        3. **System clipboard with sentinel** — clear system clipboard to a
           known sentinel via ``pbcopy``, click Copy, read via ``pbpaste``;
           only return if the value changed from the sentinel (guards against
           stale prompt text left by ``_paste_to_input``).

        Returns the clipboard text, or None if no method succeeded.
        """
        try:
            # Look for copy button in the parent model-response container
            copy_selectors = [
                'button[aria-label="Copy"]',
                'button[aria-label="Copy response"]',
                'button[aria-label*="copy" i]',
                'button[data-test-id="copy-button"]',
                '.copy-button',
            ]

            parent = page.locator("model-response").last
            copy_btn = None
            for sel in copy_selectors:
                btn = parent.locator(sel).first
                try:
                    if await btn.count() > 0 and await btn.is_visible(timeout=1000):
                        copy_btn = btn
                        break
                except Exception:
                    continue

            if not copy_btn:
                # Fallback: look for copy button anywhere in the last response
                response = page.locator(selector).last
                for sel in copy_selectors:
                    btn = response.locator(sel).first
                    try:
                        if await btn.count() > 0 and await btn.is_visible(timeout=1000):
                            copy_btn = btn
                            break
                    except Exception:
                        continue

            if not copy_btn:
                logger.debug("No copy button found for response")
                return None

            # Strategy 1: JS hook to intercept navigator.clipboard.writeText()
            await page.evaluate("""() => {
                window.__copiedResponseText = null;
                if (!navigator.clipboard.__hooked) {
                    const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
                    navigator.clipboard.writeText = async function(text) {
                        window.__copiedResponseText = text;
                        return orig(text);
                    };
                    navigator.clipboard.__hooked = true;
                } else {
                    // Hook already installed — just reset the capture variable
                    window.__copiedResponseText = null;
                }
            }""")

            # Clear system clipboard sentinel BEFORE clicking (for strategy 3)
            self._clear_clipboard()

            # Click the copy button
            await copy_btn.click()
            await page.wait_for_timeout(500)

            # Strategy 1 result: read intercepted text
            text = await page.evaluate("() => window.__copiedResponseText")
            if text:
                logger.debug("Copy captured via writeText hook (%d chars)", len(text))
                return text

            # Strategy 2: try navigator.clipboard.readText() in browser context
            try:
                text = await page.evaluate(
                    "async () => await navigator.clipboard.readText()"
                )
                if text:
                    logger.debug(
                        "Copy captured via clipboard.readText (%d chars)", len(text)
                    )
                    return text
            except Exception:
                pass

            # Strategy 3: system clipboard with sentinel verification
            sys_text = self._read_clipboard()
            if sys_text and sys_text != "__CLIPBOARD_CLEARED__":
                logger.debug(
                    "Copy captured via system clipboard (%d chars)", len(sys_text)
                )
                return sys_text

            logger.debug("Copy button clicked but no text captured by any method")
            return None
        except Exception as e:
            logger.debug("Copy button response extraction failed: %s", e)
            return None
