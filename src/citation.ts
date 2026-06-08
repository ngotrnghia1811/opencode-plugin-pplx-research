/**
 * Citation parsing — ported from the Python reference:
 *   src/universal_agents/providers/pplx/chat.py  (Citation, _parse_citation, _is_citation_text)
 *
 * These utilities parse raw citation text extracted from Perplexity's DOM
 * into a structured Citation object with URL, title, year, and type.
 *
 * In the v1 integration strategy (Option B — shell to Python), citation
 * extraction happens on the Python side (DOM-aware).  These TS equivalents
 * are provided for:
 *   (a) surfacing citation metadata in the ToolResult metadata block,
 *   (b) future Option A (TS Playwright in-process) migration,
 *   (c) post-processing Python-extracted citations if needed.
 */

/** A structured citation extracted from a Perplexity response. */
export type Citation = {
  text: string
  url?: string
  title?: string
  year?: number
  citationType: "web" | "academic" | "wiki" | "unknown"
}

// ── Domain heuristics for citation type classification ────────────────────

/**
 * Determine citation type from a URL's domain.
 *
 * Mirrors the Python domain heuristic in chat.py:_parse_citation() L120-129.
 */
function classifyUrl(url: string): Citation["citationType"] {
  const domain = new URL(url).hostname.toLowerCase()
  if (domain.includes("wikipedia")) return "wiki"
  if (
    domain.includes("arxiv") ||
    domain.endsWith(".edu") ||
    domain.endsWith(".ac.uk") ||
    domain.endsWith(".ac.jp")
  )
    return "academic"
  return "web"
}

// ── Citation text detection gate ──────────────────────────────────────────

/**
 * Check whether *text* looks like a citation line.
 *
 * Ported from chat.py:_is_citation_text() L87-98.
 * Matches against the same six indicator patterns.
 */
export function isCitationText(text: string): boolean {
  const patterns: (string | RegExp)[] = [
    /\d+\.\s/,                          // "1. Foo"
    /\[\d+\]/,                          // "[1] Bar"
    /https?:\/\//,                      // starts with http(s)
    /\.com|\.org|\.edu|\.gov/i,         // domain-like
    "Source:",
    "Reference:",
  ]
  for (const p of patterns) {
    if (typeof p === "string" ? text.toLowerCase().includes(p.toLowerCase()) : p.test(text))
      return true
  }
  return false
}

// ── Citation parsing ──────────────────────────────────────────────────────

/**
 * Parse raw citation text into a structured Citation.
 *
 * Ported from chat.py:_parse_citation() L101-133.
 *
 * Extraction order:
 *   1. URL  — regex  /https?:\/\/[^\s]+/
 *   2. Title — regex  /"([^"]+)"/
 *   3. Year  — regex  /\b(19|20)\d{2}\b/
 *   4. Type — domain heuristic on URL (wiki / academic / web)
 */
export function parseCitation(text: string): Citation {
  let url: string | undefined
  let title: string | undefined
  let year: number | undefined
  let citationType: Citation["citationType"] = "unknown"

  // 1. URL
  const urlMatch = text.match(/https?:\/\/[^\s]+/)
  if (urlMatch) {
    url = urlMatch[0].replace(/[.,;]+$/, "") // strip trailing punctuation
  }

  // 2. Title (quoted string)
  const titleMatch = text.match(/"([^"]+)"/)
  if (titleMatch) {
    title = titleMatch[1]!.trim()
  }

  // 3. Year (19xx or 20xx)
  const yearMatch = text.match(/\b(19|20)\d{2}\b/)
  if (yearMatch) {
    year = Number(yearMatch[0])
  }

  // 4. Citation type (domain heuristic)
  if (url) {
    citationType = classifyUrl(url)
  }

  return { text, url, title, year, citationType }
}
