"""Abstract base class for all browser-automated agents."""

import logging
import time
from datetime import datetime
from typing import Optional

from ..core.base_agent import BaseChatAgent
from ..core.config import BrowserConfig
from ..core.exceptions import BrowserError
from ..core.retry import retry
from ..core.types import Message
from .browser_manager import BrowserManager
from .dom import click_submit, find_element, type_text
from .response_detector import ResponseDetector
from .selectors import ProviderSelectors

logger = logging.getLogger(__name__)


class BaseBrowserAgent(BaseChatAgent):
    """Shared logic for all browser-automated chat agents.

    Subclasses must set SELECTORS and can override:
      - _extract_thinking()  for providers that expose thinking (Claude, Gemini)
      - _pre_chat_hook()     for custom setup before sending a message
      - _post_navigate()     for post-navigation setup (e.g. inject JS)
    """

    SELECTORS: ProviderSelectors  # Set by each provider subclass

    def __init__(self, config: BrowserConfig):
        super().__init__(config)
        self.browser_config = config
        self.browser_mgr = BrowserManager(config)
        self.detector = ResponseDetector(config)
        self._navigated = False

    # Threshold for uploading message as file instead of typing
    LONG_MESSAGE_WORD_THRESHOLD = 100

    async def chat(self, message: str, **kwargs) -> str:
        """Send a message and return the assistant's response."""
        start = time.monotonic()
        page = await self._ensure_ready()

        # Pre-chat hook (e.g. clear captured data)
        await self._pre_chat_hook(page)

        # 1. Send message (upload as file if long, or type)
        await self._send_message(page, message)

        # 2. Count existing responses before submitting
        count_before, selector_hint = await self.detector.count_responses(
            page, self.SELECTORS.response
        )

        # 3. Submit
        await click_submit(page, self.SELECTORS.submit)

        # 4. Wait for new response to appear and stabilize
        response_text = await self.detector.wait_for_new_response(
            page, self.SELECTORS.response, count_before,
            selector_hint=selector_hint,
        )

        # 5. Extract thinking (provider-specific)
        thinking, thinking_source = await self._extract_thinking(page)

        # 6. Snapshot raw API responses captured during this turn
        raw_api_responses = self.browser_mgr.get_captured_responses()

        # 7. Record turn in history
        elapsed_ms = (time.monotonic() - start) * 1000
        now = datetime.now()
        user_msg = Message(role="user", content=message, timestamp=now)
        assistant_msg = Message(role="assistant", content=response_text, timestamp=now)
        self.history.add_turn(
            user_message=user_msg,
            assistant_message=assistant_msg,
            thinking=thinking,
            processing_time_ms=elapsed_ms,
            raw_api_responses=raw_api_responses,
            thinking_source=thinking_source,
        )

        logger.info(
            "Turn %d completed in %.0fms (%d chars)",
            self.history.turn_count,
            elapsed_ms,
            len(response_text),
        )
        return response_text

    async def _ensure_ready(self):
        """Ensure browser is launched and navigated to the provider URL."""
        page = await self.browser_mgr.ensure_page()
        if not self._navigated:
            await self.browser_mgr.navigate(self.browser_config.base_url)
            await self._post_navigate(page)
            self._navigated = True
        return page

    async def _pre_chat_hook(self, page) -> None:
        """Called before each chat turn. Override for provider-specific setup."""
        # Clear captured API responses before new turn
        self.browser_mgr.clear_captured_responses()

    async def _send_message(self, page, message: str) -> None:
        """Send a message by typing into the input element.

        Override in subclasses to upload long messages as files.
        """
        input_el = await find_element(page, self.SELECTORS.input)
        await type_text(input_el, message)

    async def _post_navigate(self, page) -> None:
        """Called after navigating to the provider URL. Override to inject JS, etc."""

    async def _extract_thinking(self, page) -> tuple[Optional[str], Optional[str]]:
        """Extract thinking/reasoning content. Override in providers that support it.

        Returns:
            Tuple of (thinking_text, source_name). Both None if no thinking found.
        """
        return None, None

    async def close(self) -> None:
        """Close browser and cleanup."""
        await self.browser_mgr.close()
