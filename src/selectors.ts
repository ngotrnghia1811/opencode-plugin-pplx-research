/**
 * Perplexity.ai DOM selectors.
 *
 * Ported verbatim from the Python reference implementation:
 *   src/universal_agents/providers/pplx/selectors.py
 *
 * These are ordered by priority — the first selector that matches is used.
 * They are the hard-won result of tracking Perplexity's UI across many versions.
 * When selectors drift (Perplexity changes their DOM), update these tables and
 * the corresponding Python lists together.
 *
 * NOTE: In the v1 integration strategy (Option B — shell to Python), these
 * selectors are NOT used by the TS plugin code. They live here as:
 *   (a) documentation of what the Python agent tries,
 *   (b) a reference for future Option A (TS Playwright in-process) migration,
 *   (c) a single source of truth for selector drift remediation.
 */

// ── Core interaction selectors ──────────────────────────────────────────

/** Text input area for the query. */
export const PPLX_INPUT_SELECTORS = [
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
] as const

/** Submit / send button. */
export const PPLX_SUBMIT_SELECTORS = [
  'button[aria-label*="Submit"]',
  'button[aria-label*="Search"]',
  'button[aria-label*="Send"]',
  '[data-testid*="submit"]',
  '[data-testid*="search"]',
  'button[type="submit"]',
] as const

/** Response content container. */
export const PPLX_RESPONSE_SELECTORS = [
  "div.prose",
  "div[class*='prose'][class*='dark']",
  "div[class*='prose'][class*='break-words']",
  "div[class*='threadContentWidth'] div.prose",
  "[class*='thread'] div[class*='prose']",
  ".response-content",
  '[data-testid="response-text"]',
  ".message-content",
] as const

/** Loading / thinking indicators. */
export const PPLX_LOADING_SELECTORS = [
  ".searching",
  ".loading",
  "[aria-label*='Loading']",
] as const

// ── Citation selectors ──────────────────────────────────────────────────

export const CITATION_SELECTORS = [
  ".sources-list",
  "[data-testid='sources']",
  ".citation-list",
  "[class*='source']",
  "[class*='citation']",
] as const

// ── Deep Research mode selectors ────────────────────────────────────────

/**
 * Buttons / toggles that enable Deep Research mode before submitting.
 * Tried in order; first visible match is clicked.
 */
export const DEEP_RESEARCH_TOGGLE_SELECTORS = [
  // data-testid patterns (most stable across UI changes)
  '[data-testid="deep-research-toggle"]',
  '[data-testid="deep-research-button"]',
  '[data-testid*="deep-research"]',
  // Aria-label patterns
  'button[aria-label*="Deep Research"]',
  'button[aria-label*="deep research"]',
  // Text-based (Playwright :has-text pseudo)
  'button:has-text("Deep Research")',
  '[role="button"]:has-text("Deep Research")',
  // Class / generic patterns
  '[class*="deep-research"]',
  '[class*="deepResearch"]',
  // Fallback — icon button near the search bar labelled "Pro" or "Research"
  'button:has-text("Pro")',
  'button[aria-label*="Research"]',
] as const

/**
 * Indicators that Deep Research is currently running.
 * Used to log human-readable progress messages during the long wait.
 */
export const DEEP_RESEARCH_PROGRESS_SELECTORS = [
  // Explicit progress / status text
  '[data-testid="research-progress"]',
  '[data-testid*="research-status"]',
  '[class*="research-progress"]',
  '[class*="researchProgress"]',
  // Loading / thinking states
  '[aria-label*="researching"]',
  '[aria-label*="Researching"]',
  // Generic streaming/loading spinners that appear only during deep research
  ".research-step",
  '[class*="researchStep"]',
  // Text-based progress cues
  ':has-text("Searching the web")',
  ':has-text("Reading sources")',
  ':has-text("Analyzing")',
] as const

/**
 * Indicators that Deep Research mode is *active* (toggle is ON).
 * Used to verify the toggle click actually worked.
 */
export const DEEP_RESEARCH_ACTIVE_INDICATORS = [
  '[data-testid*="deep-research"][aria-pressed="true"]',
  '[data-testid*="deep-research"][class*="active"]',
  '[data-testid*="deep-research"][class*="selected"]',
  '[class*="deepResearch"][class*="active"]',
  'button:has-text("Deep Research")[aria-pressed="true"]',
] as const

// ── Aggregated selector table (matches Python ProviderSelectors shape) ──

export const PPLX_SELECTORS = {
  input: PPLX_INPUT_SELECTORS,
  submit: PPLX_SUBMIT_SELECTORS,
  response: PPLX_RESPONSE_SELECTORS,
  loading: PPLX_LOADING_SELECTORS,
  citation: CITATION_SELECTORS,
  deepResearchToggle: DEEP_RESEARCH_TOGGLE_SELECTORS,
  deepResearchProgress: DEEP_RESEARCH_PROGRESS_SELECTORS,
  deepResearchActive: DEEP_RESEARCH_ACTIVE_INDICATORS,
} as const

/**
 * Summary: total 52 selectors across 8 categories.
 *
 *   input:           10 selectors
 *   submit:           6 selectors
 *   response:         8 selectors
 *   loading:          3 selectors
 *   citation:         5 selectors
 *   deep-research toggle:   10 selectors
 *   deep-research progress: 10 selectors
 *   deep-research active:    5 selectors
 *
 * When migrating to Option A (TS Playwright in-process), use these
 * selectors with page.locator(selector).first in priority order.
 */
