"""Perplexity deep research agent — browser automation with Deep Research mode."""

import logging
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from ...browser.base_browser_agent import BaseBrowserAgent
from ...browser.dom import find_element, type_text, click_submit
from .chat import Citation, PerplexityChatAgent
from .config import PerplexityResearchConfig
from .selectors import (
    CITATION_SELECTORS,
    DEEP_RESEARCH_ACTIVE_INDICATORS,
    DEEP_RESEARCH_MENU_ITEM_SELECTORS,
    DEEP_RESEARCH_MODE_TRIGGER_SELECTORS,
    DEEP_RESEARCH_PROGRESS_SELECTORS,
    LOGIN_INDICATOR_NEGATIVE,
    LOGIN_INDICATOR_POSITIVE,
    PPLX_SELECTORS,
    SOURCES_BUTTON_SELECTORS,
    SOURCES_PANEL_LINK_SELECTORS,
)

logger = logging.getLogger(__name__)


@dataclass
class ResearchReport:
    """Structured output of a Perplexity deep research task."""

    query: str
    content: str
    citations: list[Citation] = field(default_factory=list)
    mode_used: str = "standard"  # "deep" or "standard"
    elapsed_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        """Render the report as a Markdown string."""
        lines = [
            f"# Research Report",
            f"",
            f"**Query:** {self.query}",
            f"**Mode:** {self.mode_used}",
            f"**Generated:** {self.timestamp}",
            f"**Duration:** {self.elapsed_seconds:.1f}s",
            f"",
            f"---",
            f"",
            self.content,
        ]

        if self.citations:
            lines.append("")
            lines.append("## Sources")
            lines.append("")
            for i, c in enumerate(self.citations, 1):
                title = c.title or c.text
                url_str = f" — [{c.url}]({c.url})" if c.url else ""
                lines.append(f"{i}. **{title}**{url_str}")

        return "\n".join(lines)

    def save(self, output_dir: Path, filename: str | None = None) -> Path:
        """Save the report to *output_dir* as a Markdown file.

        Returns the path to the saved file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            safe_query = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in self.query
            )[:60].strip()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{safe_query}.md"

        path = output_dir / filename
        path.write_text(self.to_markdown(), encoding="utf-8")
        logger.info("Report saved: %s", path)
        return path


def _parse_source_link(full_text: str, url: str) -> Citation:
    """Parse a sources-panel link into a Citation.

    The link text is '{source_name}{title}' concatenated without separator.
    Example: "bunBun — A fast all-in-one JavaScript runtime..." → name="bun", title="Bun — A fast..."
    Example: "wikipediaBun (software)Bun is a JavaScript runtime..." → name="wikipedia", title="Bun (software)..."

    Heuristic: find the split point by looking for a capital letter after lowercase,
    a delimiter like " — " or ":", or the start of a sentence.
    """
    import re
    from urllib.parse import urlparse

    title = full_text.strip()
    source_name = ""

    # Strategy 1: Look for common domain endings in the text
    # Perplexity prefixes like "bun", "wikipedia", "githuboven-sh/bun"
    # We split at the first occurrence of " — ", ":", " | ", or capital-after-lowercase
    common_delimiters = [" — ", ": ", " – ", " | "]
    for delim in common_delimiters:
        idx = full_text.find(delim)
        if idx > 0:
            source_name = full_text[:idx].strip()
            title = full_text[idx + len(delim):].strip()
            break
    else:
        # Strategy 2: Split at capital letter following lowercase (word boundary)
        m = re.search(r'([a-z])([A-Z])', full_text)
        if m:
            split_at = m.start(1) + 1
            source_name = full_text[:split_at].strip()
            title = full_text[split_at:].strip()
        # Strategy 3: Use domain from URL as fallback
        if not source_name and url:
            try:
                domain = urlparse(url).netloc
                # Remove www. prefix
                if domain.startswith("www."):
                    domain = domain[4:]
                source_name = domain.split(".")[0]
            except Exception:
                source_name = ""

    # If source_name is very long relative to title, it might be wrong — use domain instead
    if len(source_name) > 40 and url:
        try:
            domain = urlparse(url).netloc.replace("www.", "")
            source_name = domain.split(".")[0]
        except Exception:
            source_name = source_name[:30]

    # Determine citation type from URL
    citation_type = "unknown"
    if url:
        domain = urlparse(url).netloc.lower()
        if "wikipedia" in domain:
            citation_type = "wiki"
        elif "arxiv" in domain or domain.endswith((".edu", ".ac.uk", ".ac.jp")):
            citation_type = "academic"
        else:
            citation_type = "web"

    # Extract year from title if present
    year = None
    year_match = re.search(r"\b(19|20)\d{2}\b", title)
    if year_match:
        year = int(year_match.group(0))

    return Citation(
        text=full_text,
        url=url,
        title=title if title else source_name,
        year=year,
        citation_type=citation_type,
    )


class PerplexityResearchAgent(BaseBrowserAgent):
    """Perplexity browser agent for deep research tasks.

    Attempts to enable Perplexity's "Deep Research" mode before submitting
    a query.  When ``research_mode="auto"`` (the default), it gracefully falls
    back to a standard Perplexity search if the Deep Research toggle cannot be
    found or activated.

    Usage::

        config = PerplexityResearchConfig(
            storage_state="storage/pplx_storage_state.json",
            research_mode="auto",
            output_dir="reports/",
        )
        async with PerplexityResearchAgent(config) as agent:
            report = await agent.research("What are the latest advances in fusion energy?")
            report.save(Path("reports/"))
            print(report.content)
    """

    SELECTORS = PPLX_SELECTORS

    def __init__(self, config: PerplexityResearchConfig | None = None):
        super().__init__(config or PerplexityResearchConfig())
        self._research_config: PerplexityResearchConfig = self.browser_config  # type: ignore[assignment]
        self.last_report: ResearchReport | None = None

    # ------------------------------------------------------------------
    # Login state detection
    # ------------------------------------------------------------------

    async def check_logged_in(self, strict: bool = False) -> bool:
        """Check whether the user is logged in to Perplexity.

        Uses NEGATIVE DETECTION: looks for login/signup buttons or links.
        If any are present and visible, the user is NOT logged in.
        If none are found AND a positive indicator (avatar/account) is found,
        the user IS logged in.

        When *strict* is ``True``, the fallback when neither positive nor
        negative indicators are found is to return ``False`` (require POSITIVE
        proof of login).  This prevents a fresh visible page from being
        mis-classified as "already logged in" before the DOM has fully rendered.

        Returns ``True`` if logged in, ``False`` otherwise.
        Errors during check are treated as "not logged in" (fail-safe).
        """
        page = await self.browser_mgr.ensure_page()

        # 1. Check for negative indicators (login/signup buttons)
        for selector in LOGIN_INDICATOR_NEGATIVE:
            try:
                for el in await page.locator(selector).all():
                    if not await el.is_visible():
                        continue
                    text = (await el.inner_text()).strip().lower()
                    matched = next(
                        (p for p in ("log in", "sign up", "sign in") if p in text),
                        None,
                    )
                    if matched is not None:
                        logger.info(
                            "Not logged in — %r element found: %r", matched, selector
                        )
                        return False
            except Exception:
                continue

        # 2. No login buttons found — verify with a positive indicator
        for selector in LOGIN_INDICATOR_POSITIVE:
            try:
                el = page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    logger.info("Login verified — positive indicator: %s", selector)
                    return True
            except Exception:
                continue

        # 3. No login buttons AND no positive indicators
        if strict:
            # Require POSITIVE proof of login — don't assume.
            # (Fresh visible page may not have rendered either indicator yet.)
            logger.info("Not logged in — no positive indicator found (strict mode)")
            return False

        # Lenient fallback for the normal research() path: assume logged in
        # (some UI states may not render an avatar immediately)
        logger.info("Login assumed — no login buttons found (no positive indicator either)")
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def research(self, query: str, save: bool = True) -> ResearchReport:
        """Research *query* and return a :class:`ResearchReport`.

        Args:
            query: The research question or topic.
            save:  If ``True``, automatically save the Markdown report to
                   ``config.output_dir``.

        Returns:
            A populated :class:`ResearchReport`.
        """
        start = time.monotonic()
        page = await self._ensure_ready()
        await self._pre_chat_hook(page)

        mode_used = "standard"

        # 1. Try to enable Deep Research mode (unless explicitly disabled)
        if self._research_config.research_mode in ("deep", "auto"):
            enabled = await self._enable_deep_research(page)
            if enabled:
                mode_used = "deep"
                logger.info("Deep Research mode enabled")
            elif self._research_config.research_mode == "deep":
                raise RuntimeError(
                    "Deep Research mode could not be activated and research_mode='deep'. "
                    "Set research_mode='auto' to fall back to standard search."
                )
            else:
                logger.info("Deep Research toggle not found — using standard search")

        # 2. Type the query
        input_el = await find_element(page, self.SELECTORS.input)
        await type_text(input_el, query)

        # 3. Count existing responses before submitting
        count_before, selector_hint = await self.detector.count_responses(
            page, self.SELECTORS.response
        )

        # 4. Submit
        await click_submit(page, self.SELECTORS.submit)

        # 5. Wait — Deep Research can take several minutes
        wait_timeout = (
            self._research_config.max_research_wait
            if mode_used == "deep"
            else self._research_config.timeout
        )
        raw_response_text = await self._wait_for_research_response(
            page,
            count_before,
            selector_hint=selector_hint,
            timeout=wait_timeout,
            is_deep=mode_used == "deep",
        )

        # 5a. Extract citations FIRST (while page is in clean post-research state,
        #     before the download flow clicks buttons that may change the DOM)
        citations = await self._extract_citations(page)

        # 5b. Get response content — prefer full download, fall back to clipboard
        output_dir = Path(self._research_config.output_dir)
        response_text = await self._download_all_documents(page, query, output_dir)
        if response_text is None:
            logger.info("Download all documents failed — trying HTML extraction")
            response_text = await self._extract_html_as_markdown(page)
        if response_text is None:
            logger.info("HTML extraction failed — falling back to clipboard/copy")
            response_text = await self._get_clean_response_text(page, raw_response_text)
        else:
            logger.info("Using content (%d chars)", len(response_text))

        elapsed = time.monotonic() - start

        report = ResearchReport(
            query=query,
            content=response_text,
            citations=citations,
            mode_used=mode_used,
            elapsed_seconds=elapsed,
        )
        self.last_report = report

        if save:
            report.save(Path(self._research_config.output_dir))

        return report

    # ------------------------------------------------------------------
    # Deep Research mode helpers
    # ------------------------------------------------------------------

    async def _enable_deep_research(self, page: Page) -> bool:
        """Enable Deep Research mode via the two-step dropdown interaction.

        Step 1: Click the mode-selector trigger button (shows "Search" by default).
        Step 2: Click the "Deep research" menu item from the resulting dropdown.

        Returns ``True`` if Deep Research was activated, ``False`` otherwise.
        """
        # If already active, nothing to do
        if await self._is_deep_research_active(page):
            logger.info("Deep Research mode already active")
            return True

        # Step 1: Find and click the mode selector trigger
        trigger_clicked = False
        for selector in DEEP_RESEARCH_MODE_TRIGGER_SELECTORS:
            try:
                el = page.locator(selector).first
                if await el.count() == 0:
                    continue
                if not await el.is_visible():
                    continue
                # Don't click if it already shows "Deep research" (already active)
                text = (await el.inner_text()).strip().lower()
                if "deep research" in text:
                    logger.info("Mode trigger already shows Deep research — active")
                    return True
                await el.click()
                await page.wait_for_timeout(600)
                logger.debug("Clicked mode trigger (%s)", selector)
                trigger_clicked = True
                break
            except Exception as exc:
                logger.debug("Trigger selector %s: %s", selector, exc)
                continue

        if not trigger_clicked:
            logger.warning("Could not find mode selector trigger button")
            return False

        # Step 2: Wait for the dropdown menu and click "Deep research"
        menu_item_clicked = False
        for selector in DEEP_RESEARCH_MENU_ITEM_SELECTORS:
            try:
                el = page.locator(selector).first
                # Wait briefly for menu to appear
                try:
                    await el.wait_for(state="visible", timeout=2000)
                except Exception:
                    pass
                if await el.count() == 0:
                    continue
                if not await el.is_visible():
                    continue
                await el.click()
                await page.wait_for_timeout(600)
                logger.debug("Clicked Deep research menu item (%s)", selector)
                menu_item_clicked = True
                break
            except Exception as exc:
                logger.debug("Menu item selector %s: %s", selector, exc)
                continue

        if not menu_item_clicked:
            logger.warning("Could not find Deep research menu item")
            # Close the dropdown by pressing Escape
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return False

        # Verify activation
        await page.wait_for_timeout(400)
        if await self._is_deep_research_active(page):
            return True

        # Best-effort: assume it worked if we clicked the item
        logger.debug("Deep research activated (best-effort — active indicator not confirmed)")
        return True

    async def _is_deep_research_active(self, page: Page) -> bool:
        """Return ``True`` if a Deep Research active indicator is present."""
        for selector in DEEP_RESEARCH_ACTIVE_INDICATORS:
            try:
                if await page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Response waiting with Deep Research awareness
    # ------------------------------------------------------------------

    async def _wait_for_research_response(
        self,
        page: Page,
        count_before: int,
        *,
        selector_hint: str | None,
        timeout: int,
        is_deep: bool,
    ) -> str:
        """Wait for the research response, with extended timeout for Deep Research.

        While waiting in deep mode we log progress indicators so the user can
        see the agent is still working.
        """
        if not is_deep:
            # Standard path — use the normal response detector
            original_timeout = self.detector.timeout
            self.detector.timeout = timeout
            try:
                return await self.detector.wait_for_new_response(
                    page, self.SELECTORS.response, count_before, selector_hint=selector_hint
                )
            finally:
                self.detector.timeout = original_timeout

        # Deep Research path — poll with progress logging
        start = time.monotonic()
        deadline = start + timeout
        selector = selector_hint or self.SELECTORS.response[0]

        logger.info("Waiting up to %ds for Deep Research to complete…", timeout)

        last_progress_log = 0.0

        while time.monotonic() < deadline:
            # Check if response has appeared
            count_now = await page.locator(selector).count()
            if count_now > count_before:
                break

            # Log progress hints every 15 seconds
            elapsed = time.monotonic() - start
            if elapsed - last_progress_log >= 15:
                progress_msg = await self._get_progress_message(page)
                if progress_msg:
                    logger.info("[%.0fs] %s", elapsed, progress_msg)
                else:
                    logger.info("[%.0fs] Still researching…", elapsed)
                last_progress_log = elapsed

            await page.wait_for_timeout(2000)
        else:
            logger.warning(
                "Deep Research did not complete within %ds — returning partial content", timeout
            )

        # Wait for content to stabilize (borrow from normal detector, extended timeout)
        original_timeout = self.detector.timeout
        remaining = max(30, int(deadline - time.monotonic()))
        self.detector.timeout = remaining
        try:
            return await self.detector.wait_for_new_response(
                page, self.SELECTORS.response, count_before, selector_hint=selector
            )
        finally:
            self.detector.timeout = original_timeout

    async def _get_progress_message(self, page: Page) -> str | None:
        """Return a human-readable progress message if one is visible."""
        for selector in DEEP_RESEARCH_PROGRESS_SELECTORS:
            try:
                el = page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    text = (await el.text_content() or "").strip()
                    if text:
                        return text[:120]
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Clean response text via Copy button / clipboard
    # ------------------------------------------------------------------

    async def _get_clean_response_text(self, page: Page, raw_text: str) -> str:
        """Get clean response text by clicking the Copy button and reading clipboard.

        Falls back to regex-stripping inline citation markers if clipboard read fails.
        """
        # Strategy 1: Click Copy and read clipboard
        try:
            copy_btn = page.locator('button[aria-label="Copy"]').first
            if await copy_btn.count() > 0 and await copy_btn.is_visible():
                await copy_btn.click()
                await page.wait_for_timeout(800)

                # Read clipboard via JS
                clipboard_text = await page.evaluate("""
                    (async () => {
                        try {
                            return await navigator.clipboard.readText();
                        } catch (e) {
                            return '';
                        }
                    })()
                """)

                if clipboard_text and len(clipboard_text) > 50:
                    logger.info("Got clean text from clipboard (%d chars)", len(clipboard_text))
                    return clipboard_text
        except Exception as exc:
            logger.debug("Copy-button clipboard read failed: %s", exc)

        # Strategy 2: Fallback — strip inline citation markers from raw text
        import re
        lines = raw_text.split("\n")
        cleaned_lines = []
        prev_was_short = False

        for line in lines:
            stripped = line.strip()

            # Match "+N" vote count lines (standalone)
            if re.match(r'^\+\d+$', stripped):
                prev_was_short = False
                continue

            # Match short source-name markers (like "bun", "wikipedia", "github")
            # that appear right before a "+N" line
            if re.match(r'^[a-z][a-z0-9.-]{1,30}$', stripped, re.IGNORECASE):
                prev_was_short = True
                continue

            # If previous line was a stripped source name and this isn't "+N",
            # the source name was probably intended as inline text — keep it
            if prev_was_short and stripped:
                # We already removed it; don't re-insert
                pass

            prev_was_short = False
            cleaned_lines.append(line)

        result = "\n".join(cleaned_lines)
        # Clean up any double-newlines created by stripping
        result = re.sub(r'\n{3,}', '\n\n', result)
        logger.info("Used fallback stripping for response text")
        return result.strip()

    # ------------------------------------------------------------------
    # HTML-to-markdown extraction (fallback when zip download fails)
    # ------------------------------------------------------------------

    async def _extract_html_as_markdown(self, page: Page) -> str | None:
        """Extract the response container's HTML and convert to markdown.
        
        Uses Playwright JS evaluation to get innerHTML and a simple regex-based
        converter. Returns None if the response container can't be found.
        """
        # Try to get the response container's innerHTML
        try:
            # Perplexity renders responses in a div with prose class
            html = await page.evaluate("""
                () => {
                    // Try known response containers
                    const selectors = [
                        'div.prose',
                        'div[class*="prose"]',
                        '[data-testid="response-text"]',
                        '.response-content',
                        '.message-content',
                        '[class*="threadContentWidth"] div.prose',
                        '[class*="thread"] div[class*="prose"]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerHTML.trim().length > 100) {
                            return el.innerHTML;
                        }
                    }
                    // Fallback: find the largest prose-like div
                    const divs = document.querySelectorAll('div');
                    let best = null;
                    let bestLen = 0;
                    for (const d of divs) {
                        if (d.className && d.className.includes('prose') && d.innerHTML.length > bestLen) {
                            best = d;
                            bestLen = d.innerHTML.length;
                        }
                    }
                    return best ? best.innerHTML : null;
                }
            """)
            
            if not html or len(html) < 100:
                logger.debug("HTML extraction: no suitable response container found")
                return None
            
            logger.info("Extracted response HTML (%d chars)", len(html))
            
            # Simple HTML-to-markdown conversion
            md = self._html_to_markdown(html)
            logger.info("Converted HTML to markdown (%d chars)", len(md))
            return md
            
        except Exception as exc:
            logger.debug("HTML extraction failed: %s", exc)
            return None
    
    @staticmethod
    def _html_to_markdown(html: str) -> str:
        """Convert basic HTML to Markdown using regex substitutions.
        
        Handles common patterns: headings, bold, italic, links, lists, paragraphs.
        No external dependencies required.
        """
        import re
        
        text = html
        
        # Remove script and style tags with their content
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Convert headings (h1-h6)
        for i in range(6, 0, -1):
            text = re.sub(
                rf'<h{i}[^>]*>(.*?)</h{i}>',
                lambda m, level=i: f'{"#" * level} {m.group(1).strip()}\n\n',
                text,
                flags=re.DOTALL | re.IGNORECASE
            )
        
        # Convert bold
        text = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Convert italic
        text = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Convert links
        text = re.sub(
            r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
            r'[\2](\1)',
            text,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # Convert unordered lists
        text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Convert paragraphs to double-newline
        text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        
        # Convert line breaks
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        
        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Decode common HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
        text = text.replace('&nbsp;', ' ')
        
        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        text = text.strip()
        
        return text

    # ------------------------------------------------------------------
    # Download → All documents → .zip → extract full Markdown artifacts
    # ------------------------------------------------------------------

    async def _download_all_documents(self, page: Page, query: str, output_dir: Path) -> str | None:
        """Download the full response as a .zip via Download → All documents.

        Returns the combined markdown content, or None if download failed.
        """
        from .selectors import DOWNLOAD_BUTTON_SELECTORS, DOWNLOAD_ALL_DOCUMENTS_SELECTORS

        logger.info("Attempting Download → All documents → .zip flow")

        # Step 1: Click the Download button to open dropdown
        for selector in DOWNLOAD_BUTTON_SELECTORS:
            logger.debug("Trying download button selector: %s", selector)
            # ── Find the element ─────────────────────────────────
            el = None
            try:
                el = page.locator(selector).first
                if await el.count() == 0:
                    continue
                if not await el.is_visible():
                    continue
            except Exception as exc:
                logger.debug("Download button selector %s: %s", selector, exc)
                continue

            logger.info("Found Download button: %s", selector)

            # ── Download flow (click → dropdown → zip → extract) ─
            try:
                # Set up download listener BEFORE clicking
                async with page.expect_download() as download_info:
                    await el.click()
                    logger.info("Clicked Download button, waiting for dropdown...")

                    # Wait for dropdown menu to appear
                    try:
                        await page.wait_for_selector('[role="menu"], [role="listbox"], [role="dialog"]', timeout=3000)
                        logger.debug("Dropdown appeared")
                    except Exception:
                        logger.debug("Dropdown wait timed out — trying anyway")
                        await page.wait_for_timeout(1000)

                    # Step 2: Click "All documents" in the dropdown
                    all_docs_clicked = False
                    for menu_selector in DOWNLOAD_ALL_DOCUMENTS_SELECTORS:
                        try:
                            menu_el = page.locator(menu_selector).first
                            if await menu_el.count() == 0:
                                continue
                            if not await menu_el.is_visible():
                                continue
                            await menu_el.click()
                            logger.info("Clicked 'All documents', waiting for download...")
                            all_docs_clicked = True
                            logger.debug("Clicked All documents (%s)", menu_selector)
                            break
                        except Exception as exc:
                            logger.debug("All docs selector %s: %s", menu_selector, exc)
                            continue

                    if not all_docs_clicked:
                        logger.warning("Could not find 'All documents' menu item")
                        return None

                    # Wait for download to complete
                    download = await download_info.value
                    logger.info("Download started: %s", download.suggested_filename or "(unknown)")

                    # Save to temp file
                    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                        await download.save_as(tmp.name)
                        zip_path = tmp.name

                    logger.info("Download saved to %s", zip_path)

                    # Clean artifacts dir from previous extractions to prevent duplication
                    extract_dir = output_dir / "artifacts"
                    if extract_dir.exists():
                        shutil.rmtree(extract_dir)
                        logger.debug("Cleaned previous artifacts from %s", extract_dir)
                    extract_dir.mkdir(parents=True, exist_ok=True)

                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(extract_dir)

                    logger.info("Extracted %d files to %s, zip kept at %s",
                                len(zf.namelist()), extract_dir, zip_path)

                    # Find and read all .md files
                    md_files = sorted(list(extract_dir.rglob("*.md")) + list(extract_dir.rglob("*.markdown")))
                    if not md_files:
                        # Try broader search
                        all_files = list(extract_dir.rglob("*"))
                        logger.warning("No .md/.markdown files in zip. Contents: %s",
                                       [str(f.relative_to(extract_dir)) for f in all_files if f.is_file()])
                        return None

                    logger.info("Found %d .md files in zip", len(md_files))

                    # Combine all .md files into one report
                    parts = []
                    for md_file in md_files:
                        content = md_file.read_text(encoding="utf-8")
                        parts.append(content)

                    full_md = "\n\n".join(parts)
                    logger.info("Combined %d .md files (%d total chars)", len(md_files), len(full_md))

                    # Clean up temp zip
                    try:
                        Path(zip_path).unlink()
                    except Exception:
                        pass

                    return full_md

            except Exception as exc:
                logger.debug("Download attempt failed: %s", exc)
                # Close dropdown if still open
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                continue

        logger.warning("Could not find Download button")
        return None

    # ------------------------------------------------------------------
    # Citation extraction (delegated to PerplexityChatAgent static helpers)
    # ------------------------------------------------------------------

    async def _extract_citations(self, page: Page) -> list[Citation]:
        """Extract citations by opening the sources panel.

        1. Click the "X sources" button to open the panel
        2. Extract all links from the opened panel
        3. Parse each link into a Citation (source name → URL → title → type)
        """
        citations: list[Citation] = []

        # Step 1: Click the "X sources" button to open the sources panel
        sources_button_clicked = False
        for selector in SOURCES_BUTTON_SELECTORS:
            try:
                el = page.locator(selector).first
                if await el.count() == 0:
                    continue
                if not await el.is_visible():
                    continue
                text = (await el.inner_text()).strip()
                logger.debug("Clicking sources button: %s", text)
                await el.click()
                await page.wait_for_timeout(1000)
                sources_button_clicked = True
                break
            except Exception as exc:
                logger.debug("Sources button selector %s: %s", selector, exc)
                continue

        if not sources_button_clicked:
            logger.warning("Could not find sources button — no citations extracted")
            return citations

        # Step 2: Extract all visible links from the panel
        # The page now has source links in a visible panel
        source_links_seen: set[str] = set()
        for selector in SOURCES_PANEL_LINK_SELECTORS:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                if count == 0:
                    continue
                for i in range(min(count, 50)):
                    el = elements.nth(i)
                    if not await el.is_visible():
                        continue
                    href = (await el.get_attribute("href") or "").strip()
                    if not href or not href.startswith("http"):
                        continue
                    # Deduplicate by URL
                    normalized = href.rstrip("/")
                    if normalized in source_links_seen:
                        continue
                    source_links_seen.add(normalized)

                    text = (await el.text_content() or "").strip()
                    citation = _parse_source_link(text, href)
                    citations.append(citation)
                if citations:
                    break
            except Exception as exc:
                logger.debug("Panel link selector %s: %s", selector, exc)
                continue

        logger.debug("Extracted %d citations from sources panel", len(citations))
        return citations
