"""Perplexity chat agent — browser automation with citation extraction."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page

from ...browser.base_browser_agent import BaseBrowserAgent
from .config import PerplexityConfig
from .selectors import CITATION_SELECTORS, PPLX_SELECTORS

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A structured citation extracted from a Perplexity response."""

    text: str
    url: str | None = None
    title: str | None = None
    year: int | None = None
    citation_type: str = "unknown"  # web, academic, wiki


class PerplexityChatAgent(BaseBrowserAgent):
    """Perplexity browser agent with citation extraction.

    Usage:
        async with PerplexityChatAgent() as agent:
            response = await agent.chat("What is quantum computing?")
            print(response)
            print(agent.last_citations)
    """

    SELECTORS = PPLX_SELECTORS

    def __init__(self, config: PerplexityConfig | None = None):
        super().__init__(config or PerplexityConfig())
        self._extract_citations_enabled = self.browser_config.extract_citations  # type: ignore[attr-defined]
        self.last_citations: list[Citation] = []

    async def chat(self, message: str, **kwargs) -> str:
        """Send a message, extract response and citations."""
        response = await super().chat(message, **kwargs)
        if self._extract_citations_enabled:
            page = await self.browser_mgr.ensure_page()
            self.last_citations = await self._extract_citations(page)
        return response

    async def _extract_citations(self, page: Page) -> list[Citation]:
        """Extract citations from the current page."""
        citations: list[Citation] = []
        for selector in CITATION_SELECTORS:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                if count == 0:
                    continue
                for i in range(count):
                    el = elements.nth(i)
                    text = (await el.text_content() or "").strip()
                    if not text or not self._is_citation_text(text):
                        continue
                    citation = self._parse_citation(text)

                    # Try to extract URL from anchor element
                    link = el.locator("a").first
                    if await link.count() > 0:
                        href = await link.get_attribute("href")
                        if href:
                            citation.url = href
                        if not citation.title:
                            citation.title = (await link.text_content() or "").strip()

                    citations.append(citation)
                if citations:
                    break  # Found citations with this selector
            except Exception:
                continue
        logger.debug("Extracted %d citations", len(citations))
        return citations

    @staticmethod
    def _is_citation_text(text: str) -> bool:
        """Check if text appears to be a citation."""
        indicators = [
            r"\d+\.\s",
            r"\[\d+\]",
            r"https?://",
            r"\.com|\.org|\.edu|\.gov",
            "Source:",
            "Reference:",
        ]
        return any(re.search(p, text, re.IGNORECASE) for p in indicators)

    @staticmethod
    def _parse_citation(text: str) -> Citation:
        """Parse citation text into a structured Citation."""
        url = None
        title = None
        year = None
        citation_type = "unknown"

        url_match = re.search(r"https?://[^\s]+", text)
        if url_match:
            url = url_match.group(0).rstrip(".,;")

        title_match = re.search(r'"([^"]+)"', text)
        if title_match:
            title = title_match.group(1).strip()

        year_match = re.search(r"\b(19|20)\d{2}\b", text)
        if year_match:
            year = int(year_match.group(0))

        if url:
            domain = urlparse(url).netloc.lower()
            if "wikipedia" in domain:
                citation_type = "wiki"
            elif "arxiv" in domain or any(
                ext in domain for ext in ("edu", "ac.uk", "ac.jp")
            ):
                citation_type = "academic"
            else:
                citation_type = "web"

        return Citation(
            text=text, url=url, title=title, year=year, citation_type=citation_type
        )
