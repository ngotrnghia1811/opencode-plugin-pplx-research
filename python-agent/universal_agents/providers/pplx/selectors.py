"""Perplexity DOM selectors."""

from ...browser.selectors import ProviderSelectors

PPLX_SELECTORS = ProviderSelectors(
    input=[
        "textarea[placeholder*='Ask']",
        "textarea[placeholder*='Search']",
        "textarea[placeholder*='Follow up']",
        "textarea[aria-label*='Search']",
        "textarea[aria-label*='Ask']",
        "[contenteditable='true']",
        "div[contenteditable='true']",
        "textarea",
        "[role='textbox']",
        "input[type='text']",
    ],
    submit=[
        'button[aria-label*="Submit"]',
        'button[aria-label*="Search"]',
        'button[aria-label*="Send"]',
        '[data-testid*="submit"]',
        '[data-testid*="search"]',
        'button[type="submit"]',
    ],
    response=[
        "div.prose",
        "div[class*='prose'][class*='dark']",
        "div[class*='prose'][class*='break-words']",
        "div[class*='threadContentWidth'] div.prose",
        "[class*='thread'] div[class*='prose']",
        ".response-content",
        '[data-testid="response-text"]',
        ".message-content",
    ],
    loading=[
        ".searching",
        ".loading",
        "[aria-label*='Loading']",
    ],
)

CITATION_SELECTORS = [
    ".sources-list",
    "[data-testid='sources']",
    ".citation-list",
    "[class*='source']",
    "[class*='citation']",
]

# Sources panel — appears after clicking the "X sources" button
SOURCES_BUTTON_SELECTORS = [
    'button:has-text("sources")',       # verified: "9 sources", "15 sources", etc.
    'button:has-text("Sources")',       # fallback: different casing
]

SOURCES_PANEL_LINK_SELECTORS = [
    'a[href*="http"]',                  # any link — the panel will have source links
]

# The Deep Research toggle uses a two-step dropdown interaction:
# 1. Click the mode-selector trigger button (shows "Search" initially)
# 2. Click "Deep research" (lowercase 'r') from the dropdown menu

# Step 1: The mode selector trigger button (always visible on home page)
DEEP_RESEARCH_MODE_TRIGGER_SELECTORS = [
    'button:has-text("Search")',          # verified: current mode button (default state)
    'button:has-text("Deep research")',   # verified: already in deep research mode
    '[role="button"]:has-text("Search")',
]

# Step 2: The menu item to click after the dropdown opens
DEEP_RESEARCH_MENU_ITEM_SELECTORS = [
    '[role="menuitemradio"]:has-text("Deep research")',   # verified: exact match
    '[role="menuitem"]:has-text("Deep research")',         # fallback
    '[role="option"]:has-text("Deep research")',           # fallback
    ':has-text("Deep research") >> [role="menuitemradio"]',  # nested fallback
]

# Indicators that Deep Research is currently running
DEEP_RESEARCH_PROGRESS_SELECTORS = [
    # Explicit progress / status text
    '[data-testid="research-progress"]',
    '[data-testid*="research-status"]',
    '[class*="research-progress"]',
    '[class*="researchProgress"]',
    # Loading / thinking states
    '[aria-label*="researching"]',
    '[aria-label*="Researching"]',
    # Generic streaming/loading spinners that appear only during deep research
    '.research-step',
    '[class*="researchStep"]',
    # Text-based progress cues
    ':has-text("Searching the web")',
    ':has-text("Reading sources")',
    ':has-text("Analyzing")',
]

# ---------------------------------------------------------------------------
# Login state detection selectors
# ---------------------------------------------------------------------------

# Negative indicators — presence implies the user is NOT logged in.
# These match login/signup buttons or links in the Perplexity UI header.
# Verified against live Perplexity DOM (2026-06-07):
#   - ONLY 'button:has-text("Sign in")' fires on the logged-out home page
#     (matches the 'Sign In' header button).
#   - All href-based anchors and data-testid variants return 0 visible.
#   - The text-based variants ("Log in" / "Sign up") also return 0 visible.
# Kept as fallbacks in case Perplexity UI changes (text casing, modal links);
# only one is strictly needed at present.
LOGIN_INDICATOR_NEGATIVE = [
    'button:has-text("Sign in")',   # verified: fires on logged-out home page
    'button:has-text("Log in")',    # fallback: text-variant (not seen currently)
    'a[href*="/login"]',            # fallback: modal / non-SPA login links
    '[data-testid="login-button"]', # fallback: if Perplexity adds test IDs
]

# Positive indicators — presence implies the user IS logged in.
# These match account/avatar/profile elements visible only in authenticated state.
# Verified against live logged-in Perplexity DOM (2026-06-07):
#   - Perplexity renders a profile-picture <img alt="profile"> or
#     <img alt="avatar"> inside the sidebar nav when authenticated.
#   - No data-testid or class-based avatar selectors are used in practice.
LOGIN_INDICATOR_POSITIVE = [
    "img[alt*='profile' i]",   # verified: sidebar profile picture img
    "img[alt*='avatar' i]",    # verified: sidebar avatar img
    "[aria-label*='Account' i]",
    "[aria-label*='Profile' i]",
]


# Indicator that Deep Research mode is *active* (trigger button shows "Deep research")
DEEP_RESEARCH_ACTIVE_INDICATORS = [
    'button:has-text("Deep research")',                                # verified: trigger text changes after selection
    '[role="menuitemradio"]:has-text("Deep research")[aria-checked="true"]',
    '[role="menuitemradio"]:has-text("Deep research")[data-state="checked"]',
]

# ---------------------------------------------------------------------------
# Download → "All documents" flow
# ---------------------------------------------------------------------------

# Step 1: The Download button in the response toolbar
DOWNLOAD_BUTTON_SELECTORS = [
    # Text-based (most reliable)
    'button:has-text("Download")',
    ':has-text("Download") >> button',
    # aria-label variants
    '[aria-label="Download"]',
    '[aria-label*="Download" i]',
    '[aria-label*="download" i]',
    # data-testid fallbacks
    '[data-testid*="download"]',
    '[data-testid*="Download"]',
    # Generic icon buttons that might be the download button
    '[aria-label*="export" i]',
    'button:has-text("Export")',
    # SVG/title-based (some UIs use icon-only buttons with title)
    '[title*="Download" i]',
    '[title*="download" i]',
    'svg[aria-label*="Download" i]',
    # Broader: any button in the response area
    'div[class*="response"] button',
    'div[class*="prose"] ~ div button',
]

# Step 2: The "All documents" option in the Download dropdown
DOWNLOAD_ALL_DOCUMENTS_SELECTORS = [
    # Menu items (most common pattern)
    '[role="menuitem"]:has-text("All documents")',
    '[role="menuitem"]:has-text("all documents")',
    '[role="option"]:has-text("All documents")',
    '[role="option"]:has-text("all documents")',
    # Nested patterns
    ':has-text("All documents") >> [role="menuitem"]',
    ':has-text("all documents") >> [role="menuitem"]',
    # Button variants
    'button:has-text("All documents")',
    'button:has-text("all documents")',
    # Generic: any element containing "All documents" text
    ':has-text("All documents")',
    '[aria-label*="All documents" i]',
    # ZIP-specific mentions
    ':has-text(".zip")',
    '[role="menuitem"]:has-text(".zip")',
]
