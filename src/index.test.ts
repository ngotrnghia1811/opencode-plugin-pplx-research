/**
 * Smoke tests for pure TS functions in pplx-research-plugin.
 * No subprocess, no browser, no network required.
 *
 * Run with: bun test
 */
import { describe, it, expect } from "bun:test"
import { writeFileSync, unlinkSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { parseOptions } from "./config.js"
import { isCitationText, parseCitation } from "./citation.js"
import { toMarkdown, type ResearchReport } from "./report.js"
import { authValid, parseReportPath } from "./index.js"

// ── helpers ──────────────────────────────────────────────────────────────

/** Create a temp file with content, return its path. */
function tmpFile(content: string): string {
  const p = join(tmpdir(), `pplx-test-${Date.now()}-${Math.random().toString(36).slice(2)}.json`)
  writeFileSync(p, content)
  return p
}

/** Create a temp file and clean it up after the callback. */
function withTempFile(content: string, fn: (path: string) => void) {
  const p = tmpFile(content)
  try {
    fn(p)
  } finally {
    try { unlinkSync(p) } catch { /* ignore */ }
  }
}

// ── config.ts — parseOptions ─────────────────────────────────────────────

describe("parseOptions", () => {
  const defaults = {
    pythonBin: "python3",
    outputDir: "reports",
    defaultMode: "auto" as const,
    maxResearchWait: 300,
    loginOnly: false,
  }

  it("returns defaults for undefined", () => {
    const parsed = parseOptions(undefined)
    expect(parsed.pythonBin).toBe("python3")
    expect(parsed.outputDir).toBe("reports")
    expect(parsed.defaultMode).toBe("auto")
    expect(parsed.maxResearchWait).toBe(300)
    expect(parsed.loginOnly).toBe(false)
    expect(parsed.agentPath).toBeUndefined()
  })

  it("returns defaults for empty object", () => {
    expect(parseOptions({})).toMatchObject(defaults)
  })

  it("overrides specific fields", () => {
    const parsed = parseOptions({ pythonBin: "python3.11", maxResearchWait: 600 })
    expect(parsed.pythonBin).toBe("python3.11")
    expect(parsed.maxResearchWait).toBe(600)
    // unchanged defaults
    expect(parsed.outputDir).toBe("reports")
    expect(parsed.defaultMode).toBe("auto")
    expect(parsed.loginOnly).toBe(false)
  })

  it("accepts valid enum for defaultMode", () => {
    const parsed = parseOptions({ defaultMode: "deep" })
    expect(parsed.defaultMode).toBe("deep")
  })

  it("throws for invalid defaultMode enum", () => {
    expect(() => parseOptions({ defaultMode: "invalid" })).toThrow()
  })

  it("throws for negative maxResearchWait", () => {
    expect(() => parseOptions({ maxResearchWait: -1 })).toThrow()
  })

  it("throws for zero maxResearchWait (positive only)", () => {
    expect(() => parseOptions({ maxResearchWait: 0 })).toThrow()
  })
})

// ── citation.ts — isCitationText ─────────────────────────────────────────

describe("isCitationText", () => {
  it("matches numbered citation", () => {
    expect(isCitationText("1. Some citation")).toBe(true)
  })

  it("matches bracket reference", () => {
    expect(isCitationText("[1] Reference")).toBe(true)
  })

  it("matches URL", () => {
    expect(isCitationText("https://example.com")).toBe(true)
  })

  it("matches .org domain-like pattern", () => {
    expect(isCitationText("See arxiv.org paper")).toBe(true)
  })

  it("matches 'Source:' prefix", () => {
    expect(isCitationText("Source: Wikipedia")).toBe(true)
  })

  it("matches 'Reference:' prefix", () => {
    expect(isCitationText("Reference: RFC 1234")).toBe(true)
  })

  it("returns false for plain sentence", () => {
    expect(isCitationText("Just a normal sentence")).toBe(false)
  })

  it("returns false for empty string", () => {
    expect(isCitationText("")).toBe(false)
  })
})

// ── citation.ts — parseCitation ──────────────────────────────────────────

describe("parseCitation", () => {
  it("extracts URL and strips trailing punctuation", () => {
    const c = parseCitation("See https://example.com/path?q=1.")
    expect(c.url).toBe("https://example.com/path?q=1")
    expect(c.citationType).toBe("web")
  })

  it("extracts quoted title", () => {
    const c = parseCitation('1. "The Future of AI" https://example.com')
    expect(c.title).toBe("The Future of AI")
  })

  it("extracts year as number", () => {
    const c = parseCitation("Published in 2023 by someone")
    expect(c.year).toBe(2023)
  })

  it("classifies wikipedia URL as wiki", () => {
    const c = parseCitation("https://en.wikipedia.org/wiki/AI")
    expect(c.citationType).toBe("wiki")
  })

  it("classifies arxiv URL as academic", () => {
    const c = parseCitation("https://arxiv.org/abs/2301.00001")
    expect(c.citationType).toBe("academic")
  })

  it("classifies .edu URL as academic", () => {
    const c = parseCitation("https://cs.stanford.edu/papers/foo")
    expect(c.citationType).toBe("academic")
  })

  it("classifies generic URL as web", () => {
    const c = parseCitation("https://example.com")
    expect(c.citationType).toBe("web")
  })

  it("returns unknown type and undefined url for no-URL text", () => {
    const c = parseCitation("Just some text without URL")
    expect(c.citationType).toBe("unknown")
    expect(c.url).toBeUndefined()
  })

  it("preserves original text", () => {
    const c = parseCitation("[1] Research Paper https://arxiv.org/abs/2301.00001")
    expect(c.text).toBe("[1] Research Paper https://arxiv.org/abs/2301.00001")
  })
})

// ── report.ts — toMarkdown ───────────────────────────────────────────────

describe("toMarkdown", () => {
  const baseReport: ResearchReport = {
    query: "test query",
    content: "Some research content.",
    citations: [],
    modeUsed: "standard",
    elapsedSeconds: 42.123,
    timestamp: "2026-06-07T12:00:00.000Z",
  }

  it("renders header, metadata, and content without sources", () => {
    const md = toMarkdown(baseReport)
    expect(md).toContain("# Research Report")
    expect(md).toContain("**Query:** test query")
    expect(md).toContain("**Mode:** standard")
    expect(md).toContain("**Generated:** 2026-06-07T12:00:00.000Z")
    expect(md).toContain("**Duration:** 42.1s")
    expect(md).toContain("Some research content.")
    expect(md).not.toContain("## Sources")
  })

  it("renders sources section with citations", () => {
    const report: ResearchReport = {
      ...baseReport,
      citations: [
        { text: "ref 1", url: "https://a.com", title: "Title A", citationType: "web" },
        { text: "ref 2", url: "https://b.com", title: undefined, citationType: "wiki" },
        { text: "ref 3", url: undefined, citationType: "unknown" },
      ],
    }
    const md = toMarkdown(report)
    expect(md).toContain("## Sources")
    // citation with title uses [title](url)
    expect(md).toContain("1. [Title A](https://a.com)")
    // citation with no title uses [url](url)
    expect(md).toContain("2. [https://b.com](https://b.com)")
    // citation with no url renders as plain text
    expect(md).toContain("3. ref 3")
    // ensure no stray link for url-less citation
    expect(md).not.toContain("3. [ref 3](")
  })

  it("formats duration to 1 decimal place", () => {
    const report: ResearchReport = {
      ...baseReport,
      elapsedSeconds: 60.0,
    }
    expect(toMarkdown(report)).toContain("**Duration:** 60.0s")
  })
})

// ── index.ts — authValid ─────────────────────────────────────────────────

describe("authValid", () => {
  it("returns false for non-existent path", () => {
    expect(authValid("/nonexistent/path/to/storage.json")).toBe(false)
  })

  it("returns false for empty file", () => {
    withTempFile("", (p) => {
      expect(authValid(p)).toBe(false)
    })
  })

  it("returns true for valid JSON with cookies", () => {
    withTempFile(JSON.stringify({ cookies: [{ name: "x" }], origins: [] }), (p) => {
      expect(authValid(p)).toBe(true)
    })
  })

  it("returns true for valid JSON with origins", () => {
    withTempFile(
      JSON.stringify({ cookies: [], origins: [{ origin: "https://x.com", localStorage: [] }] }),
      (p) => {
        expect(authValid(p)).toBe(true)
      },
    )
  })

  it("returns false when both cookies and origins are empty", () => {
    withTempFile(JSON.stringify({ cookies: [], origins: [] }), (p) => {
      expect(authValid(p)).toBe(false)
    })
  })

  it("returns false for invalid JSON", () => {
    withTempFile("not valid json {{", (p) => {
      expect(authValid(p)).toBe(false)
    })
  })
})

// ── index.ts — parseReportPath ───────────────────────────────────────────

describe("parseReportPath", () => {
  it("extracts path from simple output", () => {
    expect(parseReportPath("Report saved: /tmp/foo.md\n")).toBe("/tmp/foo.md")
  })

  it("extracts path with leading whitespace", () => {
    expect(parseReportPath("  Report saved: /path/to/report with spaces.md")).toBe(
      "/path/to/report with spaces.md",
    )
  })

  it("extracts path from multi-line output", () => {
    expect(
      parseReportPath("some preamble\nReport saved: /path/to/deep-research-2026-06-07T120000.md\nother text"),
    ).toBe("/path/to/deep-research-2026-06-07T120000.md")
  })

  it("returns null for no match", () => {
    expect(parseReportPath("No report saved here")).toBeNull()
    expect(parseReportPath("")).toBeNull()
  })

  it("handles Windows-style paths", () => {
    expect(parseReportPath("Report saved: C:\\Users\\foo\\report.md")).toBe("C:\\Users\\foo\\report.md")
  })
})
