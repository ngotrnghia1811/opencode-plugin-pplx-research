"""Playwright browser lifecycle manager with stealth and persistent login."""

import json
import logging
import platform
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from ..core.config import BrowserConfig
from ..core.exceptions import AuthenticationError, BrowserError, CloudflareChallengeError

logger = logging.getLogger(__name__)

_JS_DIR = Path(__file__).parent / "js"


def _get_user_agent() -> str:
    """Return a realistic user agent matching the host OS."""
    system = platform.system()
    if system == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
    elif system == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )


class BrowserManager:
    """Manages Playwright browser lifecycle with stealth and persistent login."""

    def __init__(self, config: BrowserConfig):
        self.config = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._camoufox: Optional[Any] = None
        self._captured_responses: list[dict[str, Any]] = []

    async def ensure_page(self) -> Page:
        """Return the active page, launching browser if needed."""
        if self._page and not self._page.is_closed():
            return self._page
        return await self._launch()

    async def _launch(self) -> Page:
        """Launch browser with anti-detection.

        Uses Camoufox (Firefox with C++-level anti-detect patches) as the
        default engine.  Falls back to Chromium + playwright-stealth if
        Camoufox is not installed.
        """
        try:
            page = await self._launch_camoufox()
        except ImportError:
            logger.info("Camoufox not installed, falling back to Chromium + stealth")
            page = await self._launch_chromium()

        # Set up response interception for API capture
        self._page.on("response", self._on_response)
        return page

    async def _launch_camoufox(self) -> Page:
        """Launch Camoufox (anti-detect Firefox)."""
        from camoufox.async_api import AsyncCamoufox  # type: ignore[import-untyped]

        self._camoufox = AsyncCamoufox(
            headless=self.config.headless,
            humanize=True,
            window=(self.config.viewport_width, self.config.viewport_height),
        )
        self._browser = await self._camoufox.__aenter__()

        # Build context options
        context_opts: dict[str, Any] = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "locale": "en-US",
            "java_script_enabled": True,
        }

        self._context = await self._browser.new_context(**context_opts)

        # Inject cookies from storage state (Camoufox contexts don't
        # accept storage_state kwarg directly)
        if self.config.storage_state and Path(self.config.storage_state).exists():
            state = json.loads(Path(self.config.storage_state).read_text())
            if state.get("cookies"):
                await self._context.add_cookies(state["cookies"])
            logger.info("Using storage state: %s", self.config.storage_state)

        self._page = await self._context.new_page()
        logger.info("Camoufox browser launched (headless=%s)", self.config.headless)
        return self._page

    async def _launch_chromium(self) -> Page:
        """Launch Chromium with playwright-stealth."""
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            args=launch_args,
        )

        # Build context options
        context_opts: dict[str, Any] = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "user_agent": _get_user_agent(),
            "locale": "en-US",
            "java_script_enabled": True,
        }

        # Reuse persistent login if storage state exists
        if self.config.storage_state and Path(self.config.storage_state).exists():
            context_opts["storage_state"] = self.config.storage_state
            logger.info("Using storage state: %s", self.config.storage_state)

        self._context = await self._browser.new_context(**context_opts)

        # Apply playwright-stealth v2.x (context-level, comprehensive evasion)
        try:
            from playwright_stealth import Stealth  # type: ignore[import-untyped]

            stealth = Stealth()
            await stealth.apply_stealth_async(self._context)
            logger.info("playwright-stealth v2.x applied (context-level)")
        except ImportError:
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                if (!window.chrome) { window.chrome = { runtime: {} }; }
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)
            logger.debug("playwright-stealth not installed, using basic anti-detection only")

        self._page = await self._context.new_page()
        logger.info("Chromium browser launched (headless=%s)", self.config.headless)
        return self._page

    async def _on_response(self, response) -> None:
        """Capture relevant API responses for thinking extraction."""
        try:
            url = response.url
            # Claude: /api/organizations/.../chat_conversations
            # Gemini: BardFrontendService/StreamGenerate or batchexecute
            is_claude = "/api/organizations/" in url and "/chat_conversations" in url
            is_gemini = "StreamGenerate" in url or "batchexecute" in url
            if is_claude or is_gemini:
                data = await response.json()
                self._captured_responses.append({
                    "url": url,
                    "data": data,
                })
                logger.debug("Captured API response: %s", url)
        except Exception:
            pass  # Not JSON or reading failed

    def get_captured_responses(self) -> list[dict[str, Any]]:
        """Return captured API responses (for thinking extraction)."""
        return list(self._captured_responses)

    def clear_captured_responses(self) -> None:
        """Clear captured responses (call before each new turn)."""
        self._captured_responses.clear()

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and handle Cloudflare challenges with retry."""
        page = await self.ensure_page()
        for attempt in range(3):
            await page.goto(url, wait_until="domcontentloaded",
                            timeout=self.config.page_load_timeout * 1000)
            try:
                await self._handle_cloudflare(page)
                return
            except CloudflareChallengeError:
                if attempt < 2:
                    logger.warning("Cloudflare challenge attempt %d failed, retrying...", attempt + 1)
                    await page.wait_for_timeout(5000)
                else:
                    raise

    async def _handle_cloudflare(self, page: Page) -> None:
        """Detect and wait for Cloudflare challenge resolution."""
        title = await page.title()
        body_text = await page.evaluate(
            "document.body?.innerText?.substring(0, 300) || ''"
        )
        is_challenge = (
            "Just a moment" in title
            or "Checking your browser" in title
            or "security verification" in body_text.lower()
        )
        if not is_challenge:
            return

        logger.info("Cloudflare challenge detected, waiting for resolution...")
        try:
            await page.wait_for_function(
                """() => {
                    const title = document.title;
                    const body = document.body?.innerText || '';
                    return !title.includes('Just a moment')
                        && !title.includes('Checking your browser')
                        && !body.includes('security verification')
                        && !body.includes('Performing security');
                }""",
                timeout=30_000,
            )
            # Extra safety delay after challenge clears
            await page.wait_for_timeout(2000)
            logger.info("Cloudflare challenge resolved")
        except Exception as e:
            raise CloudflareChallengeError(
                f"Cloudflare challenge did not resolve within 30s: {e}"
            ) from e

    async def inject_js(self, filename: str) -> None:
        """Inject a JavaScript file from the js/ directory into the current page."""
        page = await self.ensure_page()
        js_path = _JS_DIR / filename
        js_code = js_path.read_text()
        await page.evaluate(js_code)
        logger.debug("Injected JS: %s", filename)

    async def save_storage_state(self, path: str) -> None:
        """Save current cookies/localStorage to a JSON file for reuse."""
        if self._context:
            await self._context.storage_state(path=path)
            logger.info("Storage state saved to %s", path)

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._page and not self._page.is_closed():
            self._page.remove_listener("response", self._on_response)
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._camoufox:
            # Exit the Camoufox async context manager
            await self._camoufox.__aexit__(None, None, None)
        else:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._camoufox = None
        self._playwright = None
        logger.info("Browser closed")
