/**
 * ResearchReport type and Markdown rendering.
 *
 * Ported from the Python reference:
 *   src/universal_agents/providers/pplx/research.py  (ResearchReport.to_markdown)
 *
 * Produces the identical Markdown format:
 *   H1 title → metadata block → HR → content → HR → Sources (if any)
 */
import type { Citation } from "./citation.js"

/** A completed Perplexity research report. */
export type ResearchReport = {
  query: string
  content: string
  citations: Citation[]
  modeUsed: string   // "deep" | "standard"
  elapsedSeconds: number
  timestamp: string  // ISO-8601
}

/**
 * Render a ResearchReport as a Markdown string.
 *
 * Matches the Python ResearchReport.to_markdown() format exactly:
 *
 *   # Research Report
 *
 *   **Query:** ...
 *   **Mode:** ...
 *   **Generated:** ...
 *   **Duration:** ...
 *
 *   ---
 *
 *   <content>
 *
 *   ---
 *
 *   ## Sources
 *
 *   1. [Title](url)
 *   2. text
 */
export function toMarkdown(report: ResearchReport): string {
  const lines: string[] = [
    "# Research Report",
    "",
    `**Query:** ${report.query}`,
    `**Mode:** ${report.modeUsed}`,
    `**Generated:** ${report.timestamp}`,
    `**Duration:** ${report.elapsedSeconds.toFixed(1)}s`,
    "",
    "---",
    "",
    report.content,
  ]

  if (report.citations.length > 0) {
    lines.push("", "---", "", "## Sources", "")
    for (const [i, c] of report.citations.entries()) {
      const num = i + 1
      if (c.url) {
        const label = c.title || c.url
        lines.push(`${num}. [${label}](${c.url})`)
      } else {
        lines.push(`${num}. ${c.text}`)
      }
    }
  }

  return lines.join("\n")
}
