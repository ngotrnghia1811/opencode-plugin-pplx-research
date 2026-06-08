# pplx-research-plugin — Development Plan

*Reference: /Users/nghiango-mbp/git_repo/universal-agent_v2/compiled_agents/pplx_deep_research | Last updated: 2026-06-07*

---

## 1. Feature Description

**What.** An opencode plugin that exposes a `pplx_research` custom tool to coding agents. The tool drives Perplexity AI (https://www.perplexity.ai) through a real browser to perform research queries and returns a structured Markdown research report with citations.

**Example tool call (by an opencode agent).**

```
Tool: pplx_research
Args: { "query": "Latest advances in Rust async runtimes", "mode": "auto", "save": true }
→ Returns a Markdown research report with numbered citations, metadata (query, mode used, elapsed time), saved to the project directory.
```

**Purpose in an opencode workflow.** When a coding agent needs deeply-researched, cited context about a technology, library, or design question, it calls this tool instead of consuming LLM context tokens on speculative synthesis. The tool produces a citeable artifact that can be referenced in follow-up messages (or as an attached file). Deep Research queries can take 3–5 minutes; the tool's progress-text output keeps the user aware.

---

## 2. Reference Implementation Analysis

The Python reference at `.../universal-agent_v2/compiled_agents/pplx_deep_research` is a self-contained Playwright browser-automation agent. Key parts worth porting:

### 2.1 Login / Session Capture

- **Flow** (`agent.py:63–100`): opens a *visible* Chromium browser (headless: false) → navigates to `https://www.perplexity.ai` → waits for the user to manually log in → user presses Enter in the terminal → `page.context.storage_state()` is saved as JSON → subsequent invocations pass the path to `BrowserContext` (headless, cookies + localStorage injected).
- **Critical detail**: `storage/pplx_storage_state.json` contains **auth cookies**. Must **never** be committed to git, echoed in output, or included in prompts.

### 2.2 Research Flow

Full path in `research.py:117–191`:

1. **Optionally enable Deep Research mode** (`_enable_deep_research`, L197–229): iterates `DEEP_RESEARCH_TOGGLE_SELECTORS`, locates visible button, clicks it, waits 600ms, verifies activation via `DEEP_RESEARCH_ACTIVE_INDICATORS`. If mode=`deep` and toggle not found → raises. If mode=`auto` → silently falls back to standard.
2. **Type query** (`find_element` + `type_text`) into the input field.
3. **Count existing response nodes** (`detector.count_responses`) — used to detect when a *new* response arrives after submission.
4. **Submit** (`click_submit`).
5. **Wait for new response** — two paths:
   - *Standard mode*: `wait_for_new_response` with `timeout=60s`, content-stabilization check (3 stable reads at 2s interval).
   - *Deep Research mode*: poll loop up to `max_research_wait=300s`, logs progress every 15s via `DEEP_RESEARCH_PROGRESS_SELECTORS` (e.g. "Searching the web", "Reading sources"), then falls back to the stabilization-check with remaining time (min 30s). If timeout elapses, returns partial content with a warning.
6. **Extract citations** (`_extract_citations`): locates citation containers, parses each entry via regex (`_parse_citation`), extracts `<a>` href for URL and title.
7. **Build and save** `ResearchReport → to_markdown() → save()`.

### 2.3 ResearchReport

Fields: `query`, `content`, `citations[]`, `mode_used`, `elapsed_seconds`, `timestamp`.
`to_markdown()` renders:
- H1 title + metadata block (query, mode, generated, duration)
- Horizontal rule, full response content
- Horizontal rule, `## Sources` with numbered links/descriptions
`save()` writes `YYYYMMDD_HHMMSS_<safe-query>.md` to output dir.

### 2.4 Citation Parsing

`chat.py:18–133`. `Citation` dataclass: `{ text, url?, title?, year?, citation_type ∈ web|academic|wiki }`. Parsed via:
- URL: regex `https?://[^\s]+`
- Title: regex `"([^"]+)"` (quoted string)
- Year: regex `\b(19|20)\d{2}\b`
- Type: domain heuristic — `wikipedia` → wiki, `arxiv`/`.edu`/`.ac.uk`/`.ac.jp` → academic, else → web.
- `_is_citation_text()` gate: must match one of `\d+\.\s`, `\[\d+\]`, `https?://`, `.com|.org|.edu|.gov`, `Source:`, `Reference:`.

### 2.5 Selector Tables

**These are hard-won stability investments — port them verbatim as the starting point.** The reference has refined these over many Perplexity UI changes.

| Category | Count | First selector (target) |
|---|---|---|
| input | 10 | `textarea[placeholder*='Ask']` |
| submit | 6 | `button[aria-label*="Submit"]` |
| response | 8 | `div.prose` |
| citation | 5 | `.sources-list` |
| deep-research toggle | 10 | `[data-testid="deep-research-toggle"]` |
| deep-research progress | 10 | `[data-testid="research-progress"]` |
| deep-research active | 5 | `[data-testid*="deep-research"][aria-pressed="true"]` |

Full tables in `src/selectors.ts`.

### 2.6 Browser Management

- **Engine**: Camoufox (Firefox + C++ anti-detect patches) as primary; Chromium + `playwright-stealth` as fallback.
- **Cloudflare**: detected via title "Just a moment" / "Checking your browser" + body "security verification", waited up to 30s via `page.wait_for_function`.
- **Anti-detection**: `--disable-blink-features=AutomationControlled`, custom user agent, `navigator.webdriver` removal, `window.chrome` injection, `navigator.plugins` spoofing.

### 2.7 Config

`config.json`: `headless: true`, `timeout: 60`, `extract_citations: true`, `research_mode: "auto"`, `output_dir: "reports/"`, `max_research_wait: 300`.

---

## 3. Integration Strategy

### Option A — TS Playwright In-Process

Plug Playwright (`playwright` npm) into the plugin; the `pplx_research` tool spawns/runs a browser directly from the Bun/Node runtime.

| Pro | Con |
|---|---|
| Cleanest UX — everything in one process | Heavy dependency (~400MB Chromium download) |
| TypeScript end-to-end, no Python required | Login flow is awkward inside a *tool call* (must open browser, wait) |
| Long-lived warm browser possible across calls | Cloudflare/stealth harder in Bun than Python (playwright-stealth has npm package but may lag) |
| | Deep Research wait (300s) may exceed opencode's HTTP timeout |

### Option B — Shell to Python Agent

The plugin tool uses Bun `$` shell (from `PluginInput`) to invoke `python agent.py "<query>" --mode ... --output ...`, waits for the subprocess, reads the saved Markdown report, returns it as `ToolResult`.

| Pro | Con |
|---|---|
| Lowest effort — zero porting of browser logic | Requires Python 3.10+ + `pip install -r requirements.txt` |
| Reuses the battle-tested, selector-stable reference verbatim | Cross-process — error messages are stringly-typed |
| Deep Research wait handled by subprocess naturally | Two codebases to maintain if selectors drift |
| Python agent is self-contained (no plugin knows about Playwright internals) | Need to bundle the Python agent alongside the plugin, or check it out separately |

### Option C — Sidecar/Subprocess Server

A long-lived Playwright process (TS or Python) listening on a local socket/HTTP. The plugin tool sends serialized requests to the sidecar, receives responses.

| Pro | Con |
|---|---|
| Amortizes browser startup across multiple tool calls | Highest complexity for v1 |
| Session stays warm, no auth-repeat per call | Need a protocol (JSON/HTTP), process lifecycle management |
| Can return streaming progress updates | Overkill when the core use case is batch research |

### Recommended Strategy for v1: **Option B**

**Rationale.** The reference Python agent is proven against real Perplexity, selector-drifting, and Cloudflare evasions. Shelling out from the Bun plugin via `ctx.$` is a trivial integration — ~30 lines of TypeScript. The tool's execute function would:
1. Validate args (zod).
2. Build CLI command from args (query, mode, output_dir).
3. Run `python agent.py ...` via `ctx.$`.
4. Parse the stdout for report path.
5. Read the Markdown file with `Bun.file()`.
6. Return as `ToolResult` with optional file attachment.

**Migration path.** Once Option B is stable and the UX pain-points are known (e.g. Python env discovery, subprocess overhead), migrate to **Option A** (TS Playwright in-process) or **Option C** (warm sidecar). The tool's external interface (`pplx_research` args + ToolResult) stays constant, so migration is transparent to consuming agents.

**Resolved (OQ-1, 2026-06-07): Option B confirmed.** See §10 for the final decision.

---

## 4. Architecture (Option B — Shell to Python)

### 4.1 Module Breakdown

```
pplx-research-plugin/
├── src/
│   ├── index.ts          # Plugin entrypoint — wires tool hook
│   ├── tool.ts           # pplx_research tool definition (zod schema, execute)
│   ├── config.ts         # Plugin options parsing (research_mode, output_dir, etc.)
│   ├── selectors.ts      # Ported selector tables (reference, not used by shell strategy)
│   ├── citation.ts       # Citation parsing & Markdown rendering (used if we ever parse directly)
│   └── report.ts         # ResearchReport type + Markdown generation
├── package.json
├── tsconfig.json
├── README.md
├── DEVELOPMENT-PLAN.md   # This file
└── NOTES.md              # Scratchpad
```

### 4.2 How the `tool` Hook Wires In

```
opencode.json:
  "plugin": [
    ["@opencode-ai/plugin-pplx-research", {
      "pythonBin": "python",
      "agentPath": "path/to/compiled_agents/pplx_deep_research",
      "outputDir": "reports/",
      "defaultMode": "auto",
      "maxResearchWait": 300
    }]
  ]
```

The plugin entrypoint (`src/index.ts`) exports `const Plugin: Plugin = async (ctx, options) => { ... }`. It parses options, then returns:

```ts
{
  tool: {
    pplx_research: tool({
      description: "Research a topic via Perplexity AI ...",
      args: { query: z.string().describe(...), mode: ..., save: ..., output_dir: ... },
      async execute(args, toolCtx) {
        // 1. Build CLI command
        // 2. ctx.$.shell(...)
        // 3. Read result file
        // 4. Return ToolResult
      }
    })
  }
}
```

### 4.3 Config Flow via `options`

The `PluginOptions` (second arg to `Plugin`) is the JSON value from `opencode.json`'s `plugin` array tuple:

```ts
type PplxPluginOptions = {
  pythonBin?: string          // default "python" or "python3"
  agentPath?: string          // default "./compiled_agents/pplx_deep_research"
  outputDir?: string          // default "reports/" (relative to ctx.directory)
  defaultMode?: "deep" | "standard" | "auto"  // default "auto"
  maxResearchWait?: number    // default 300
  loginOnly?: boolean         // if true, run --login and exit (for first-time setup)
}
```

### 4.4 Session / Login Handling

**Inline auto-login (resolved decision OQ-5).** `pplx_research` does NOT hard-error on missing auth. Instead, on invocation it auto-detects missing/invalid auth and triggers login inline, then continues the research once login succeeds:

1. **Auth check**: `pplx_research` checks whether `storage/pplx_storage_state.json` exists AND appears valid. If missing/invalid → proceed to login.
2. **Inline login**: Launches the Python agent in **visible (headed) camoufox** login mode. The user sees a real browser window and logs in.
3. **Auto-detect success**: The Python agent **polls the DOM** for a logged-in indicator (e.g. presence of the account/avatar element, or absence of the login button/form) instead of blocking on `input("Press Enter…")`. When detected, it auto-saves `storage_state` and exits.
4. **Research continuation**: Once login succeeds, `pplx_research` proceeds to run the research query in the same logical flow — either as the same subprocess invocation (if the Python agent supports a combined "login-then-research" path) or as two sequential subprocess invocations (login → research).

**Why DOM-poll instead of stdin.** Through a plugin shell-out via Bun `$`, there is **no interactive stdin** for the user to press Enter. The Python agent's current `capture_login()` (`agent.py:63–100`) blocks on `input("Press Enter…")`, which is impossible through a plugin tool. The bundled Python agent MUST be changed to **auto-detect successful login** by polling the DOM for a logged-in indicator, then auto-save `storage_state`. Sketch of the polling loop:

```python
# Replacement for capture_login()'s input("Press Enter…") — pseudo-code
import asyncio, time
timeout_s = 120
poll_interval_s = 2
start = time.monotonic()
while time.monotonic() - start < timeout_s:
    logged_in = await page.evaluate("""
        () => !!(
            document.querySelector('[data-testid="user-avatar"]') ||
            document.querySelector('[class*="account"]') ||
            !document.querySelector('button:has-text("Log in")')
        )
    """)
    if logged_in:
        break
    await asyncio.sleep(poll_interval_s)
# after loop: if still not logged in, raise TimeoutError
```

The poll timeout should be generous (120s) so the user has time to type credentials.

**`pplx_login` tool preserved.** A separate `pplx_login` tool remains as an explicit/manual re-auth entry point (e.g. when the session expires and the user wants to re-login without running a research query). It calls the same Python agent path (headed browser + DOM-poll login).

**Storage state location (resolved OQ-2).** `storage/pplx_storage_state.json` lives inside the bundled Python agent directory (`python-agent/storage/`). Always **gitignored** (contains full auth cookies). Permission check: verify 0600 on Unix and warn if world-readable (see §7.3).

**Display precondition (resolved OQ-4).** The inline auto-login flow requires a **visible browser window**, which only works when opencode runs on a machine **with a display** (local TUI/desktop). In headless/remote/`serve` mode, there is no display, so interactive login cannot happen. Documented as a hard limitation and precondition.

### 4.5 How the Report Becomes a ToolResult

**No live stdout streaming (resolved OQ-4).** opencode does **NOT** stream a subprocess's stdout into the chat/TUI transcript line-by-line. The Python agent's captured stdout (including its every-15s Deep Research progress logs) is returned to the model **once, at tool completion** — not live. The user does not see real-time log output in the chat.

**In-flight feedback via `ctx.metadata`.** For status updates during the wait, the plugin SHOULD call `ctx.metadata({ title, metadata })` periodically. This updates the tool's **status line** in the opencode UI (e.g. "Researching… 45s elapsed"), which is a single-line indicator, NOT a live log tail. Example usage:

```ts
const interval = setInterval(() => {
  toolCtx.metadata({
    title: `Researching… ${Math.floor(elapsed)}s elapsed`,
    metadata: { elapsed_seconds: Math.floor(elapsed) },
  })
}, 15000)
// … after subprocess completes: clearInterval(interval)
```

**Browser GUI visibility (resolved OQ-4).** The camoufox/browser GUI window launched by the Python agent IS visible to the user — it's a real OS window on their machine, independent of the opencode TUI. During login, the user genuinely sees and interacts with the browser. During research (headless mode), the browser is invisible.

**Hard constraint — display required.** Visible login and any headed browser interaction only work when opencode runs on a machine **with a display** (local TUI/desktop mode). In headless/remote/`serve` mode there is no display, so interactive login cannot happen. This is a precondition for `pplx_research` auto-login.

**ToolResult structure:**

```ts
async function research(query, options, ctx): Promise<ToolResult> {
  const cmd = buildCommand(query, options, ctx.directory)
  const proc = ctx.$`python ...`    // Bun shell
  const stdout = (await proc).stdout.toString()
  
  // Parse report path from stdout (the Python agent prints "Report saved: <path>")
  const reportPath = parseReportPath(stdout)
  const markdown = await Bun.file(reportPath).text()
  
  return {
    title: `Research: ${query.slice(0, 80)}`,
    output: markdown,
    metadata: { query, mode, elapsed, citations, report_path: reportPath },
    attachments: [{ type: "file", mime: "text/markdown", url: `file://${reportPath}` }]
  }
}
```

---

## 5. Step-by-Step Implementation Plan

### Phase 0 — Scaffolding (30 min)

**Goal:** Skeleton plugin that compiles cleanly, registers the tool, has the right packages.

0.1 Create `pplx-research-plugin/` with `package.json` (modeled on `plugin-reminders`).
0.2 Create `tsconfig.json` (extends `@tsconfig/bun`).
0.3 Create `src/index.ts` with the `Plugin` signature and a `tool` hook that registers a stub `pplx_research` returning a placeholder string.
0.4 Add `scripts.postinstall` to `package.json` that bootstraps Python dependencies (resolved OQ-8). See Phase 6.1 for the design.
0.5 Run `bun typecheck` to confirm the skeleton compiles.

### Phase 1 — Config & Options Parsing (30 min)

**Goal:** Parse plugin options from `opencode.json` with sensible defaults.

1.1 Create `src/config.ts`: `parseOptions(options: unknown): ResolvedOptions`.
1.2 Zod schema for PluginOptions (pythonBin, agentPath, outputDir, defaultMode, maxResearchWait, loginOnly).
1.3 Defaults: pythonBin → `"python3"` (macOS/Linux) or `"python"`; agentPath → relative to plugin dir; outputDir → `ctx.directory + "/reports/"`.

**TS sketch (config.ts):**
```ts
import { z } from "zod"

const OptionsSchema = z.object({
  pythonBin: z.string().default("python3"),
  agentPath: z.string().optional(),
  outputDir: z.string().default("reports"),
  defaultMode: z.enum(["deep", "standard", "auto"]).default("auto"),
  maxResearchWait: z.number().int().positive().default(300),
  loginOnly: z.boolean().default(false),
})

export type ResolvedOptions = z.infer<typeof OptionsSchema>

export function parseOptions(input: unknown): ResolvedOptions {
  return OptionsSchema.parse(input ?? {})
}
```

### Phase 2 — Zod Args Schema for `pplx_research` (15 min)

**Goal:** Define the tool's argument schema.

**TS sketch (partial, in `src/tool.ts`):**
```ts
import { tool } from "@opencode-ai/plugin"

const pplxResearchArgs = {
  query: tool.schema.string().describe("Research query or topic"),
  mode: tool.schema.enum(["deep", "standard", "auto"]).default("auto")
    .describe("Research mode: 'deep' (force Deep Research), 'standard' (skip toggle), 'auto' (try deep, fall back)"),
  save: tool.schema.boolean().default(true)
    .describe("Whether to save the report as a Markdown file on disk"),
  output_dir: tool.schema.string().optional()
    .describe("Override output directory for saved reports"),
}
```

### Phase 3 — Shell Execution: Call Python Agent (2–3 hours)

**Goal:** The `execute()` function checks auth, auto-launches inline login if needed, builds the CLI command, runs it via `ctx.$`, captures output, and provides in-flight status via `ctx.metadata()`.

3.1 Implement `authValid(agentDir): boolean` — checks whether `storage/pplx_storage_state.json` exists AND appears valid (non-empty, has expected keys). Returns `false` if missing or invalid.

3.2 Implement `runInlineLogin(opts, ctx): Promise<boolean>` — launches `python agent.py --login-autodetect` in visible mode. The Python agent opens the browser, the user logs in, the agent auto-detects login via DOM poll (see §4.4), saves `storage_state`, and exits. Returns `true` on success.

3.3 Implement `buildCommand(query, resolvedOpts, toolArgs): string[]` — produces `["python3", "agent.py", query, "--mode", mode, "--output", outDir]`.

3.4 Implement `runResearch(query, opts, ctx): Promise<{stdout: string, stderr: string, exitCode: number}>`. During execution, set a 15s interval calling `ctx.metadata({ title: "Researching… Ns elapsed" })` for in-flight status updates (resolved OQ-4).

3.5 **Inline auth-check → login → research** orchestration (resolved OQ-5):
```ts
if (!authValid(agentDir)) {
  const loginOk = await runInlineLogin(opts, ctx)
  if (!loginOk) return "pplx_research: Login failed or timed out. Run pplx_login to try again."
}
```
Then proceed to `runResearch()`.

3.6 Handle failures: Python not found → clear error message; agent.py missing → clear error; non-zero exit → surface stderr; login timeout → clear error with manual fallback instructions.

3.7 Implement `parseReportPath(stdout: string): string | null` — matches `"Report saved: <path>"` regex.

**TS sketch (tool.ts execute function):**
```ts
async function execute(args: PplxResearchArgs, ctx: ToolContext): Promise<ToolResult> {
  const cwd = opts.agentPath ?? path.join(import.meta.dir, "..", "python-agent")
  const outputDir = args.output_dir ?? path.join(ctx.directory, opts.outputDir)
  
  // ── Inline auth check & auto-login (OQ-5) ────────────────────
  const storageState = path.join(cwd, "storage", "pplx_storage_state.json")
  if (!authValid(storageState)) {
    // TODO: Phase 3.2 — launch visible browser, user logs in,
    // Python auto-detects login via DOM poll, saves storage_state
    const loginOk = await runInlineLogin(opts, cwd, ctx)
    if (!loginOk) {
      return [
        "pplx_research: Login required. The auto-login flow did not succeed.",
        "Run the `pplx_login` tool to re-authenticate, or manually run:",
        `  cd ${cwd} && ${opts.pythonBin} agent.py --login-autodetect`,
      ].join("\n")
    }
  }
  
  const cmd = [
    opts.pythonBin,
    "agent.py",
    args.query,
    "--mode", args.mode,
    "--output", outputDir,
  ]
  
  // ── In-flight status updates (OQ-4) ──────────────────────────
  // opencode does NOT stream subprocess stdout live. Use ctx.metadata()
  // for a status-line indicator during the long Deep Research wait.
  const startTime = Date.now()
  const statusInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000)
    ctx.metadata({
      title: `Researching… ${elapsed}s elapsed`,
      metadata: { elapsed_seconds: elapsed, query: args.query },
    })
  }, 15000)
  
  const proc = ctx.$`cd ${cwd} && ${cmd.join(" ")}`
  const result = await proc
  clearInterval(statusInterval)
  
  if (result.exitCode !== 0) {
    return `Research failed (exit ${result.exitCode}):\n${result.stderr.toString()}`
  }
  
  const stdout = result.stdout.toString()
  const reportPath = parseReportPath(stdout)
  if (!reportPath) return `Research completed but couldn't parse report path.\n\n${stdout}`
  
  const markdown = await Bun.file(reportPath).text()
  
  return {
    title: `Research: ${args.query.slice(0, 80)}`,
    output: markdown,
    metadata: {
      query: args.query,
      mode: args.mode,
      report_path: reportPath,
    },
    attachments: args.save ? [{
      type: "file",
      mime: "text/markdown",
      url: `file://${reportPath}`,
      filename: path.basename(reportPath),
    }] : undefined,
  }
}
```

### Phase 4 — Citation Parsing & Markdown Rendering (TS-side) (1 hour)

**Goal:** If the plugin ever needs to format or filter citations directly (e.g. in a future Option A port), have the TS equivalents ready. For Option B, these are used only if we want to surface citation metadata in the ToolResult metadata block.

4.1 Port `Citation` type to TS (`src/citation.ts`).
4.2 Port `_parse_citation` regex logic.
4.3 Port `_is_citation_text` gate.
4.4 Port `ResearchReport.to_markdown()` — static function producing the same Markdown format.

### Phase 5 — `pplx_login` Tool (30 min)

**Goal:** Expose an explicit manual re-auth entry point (resolved OQ-5). `pplx_research` handles auth inline, but `pplx_login` remains for cases where the user wants to re-login proactively (e.g. session expired, switching accounts, or after failed auto-login).

5.1 Add `pplx_login` tool definition: no args, calls `python agent.py --login-autodetect` (the new DOM-poll variant, not the old `--login` that blocks on stdin).
5.2 The tool returns instructions: "A browser window should open. Log in to your Perplexity account. The session will auto-detect login success and save."
5.3 Unlike the old design, NO terminal Enter press is required — the Python agent auto-detects via DOM poll (see §4.4).

### Phase 6 — README, Packaging & Postinstall (1 hour)

6.1 **`scripts.postinstall` in `package.json`** (resolved OQ-8). Installing the plugin SHOULD also bootstrap its Python dependencies. Design:

```jsonc
{
  "scripts": {
    "postinstall": "node scripts/bootstrap-python.mjs"
  }
}
```

The `scripts/bootstrap-python.mjs` script (or inline shell in postinstall) performs:

1. **Detect Python** — try `python3 --version`, fall back to `python --version`. If neither found, print a warning with manual install instructions and exit 0 (warn-and-continue — don't block JS-only installs).
2. **Pip install requirements** — run `pip install -r python-agent/requirements.txt` (or `pip3` / `uv pip install`). Handle PEP 668 "externally managed environment" by detecting the error and printing instructions (`--break-system-packages` or use `venv` / `uv`). Do NOT exit non-zero for PEP 668 — warn and continue.
3. **Playwright browsers** — run `playwright install chromium`. Detect missing `playwright` CLI and print "run: pip install playwright && playwright install chromium".
4. **Camoufox fetch** — if requirements.txt includes camoufox, handle its browser binary fetch similarly.

**Graceful degradation model (all steps):**
- Any step that fails prints a **bold, actionable warning** but does NOT block the install (`exit 0`, not `exit 1`).
- Only exit non-zero for truly unrecoverable states (e.g. `python-agent/` directory missing entirely — the plugin is mispackaged).
- Manual fallback commands are printed at the end of the output for any failed step.
- The postinstall output is visible during `npm install` / `bun install` so the user sees what happened.

6.2 Write `README.md` (quick-start: npm install, auto-bootstrap via postinstall, manual fallback commands, login, configure `opencode.json`, use). Reflect standalone-npm framing (OQ-3): package is `@opencode-ai/plugin-pplx-research`, installed via `plugin` array in opencode.json. Document the display precondition (OQ-4) and inline auto-login (OQ-5).

6.3 Ensure `package.json` has correct exports, name, dependencies. Note the published form is standalone npm (remove `"private": true` before publishing, or keep for dev).

6.4 Gitignore `storage/` or any `pplx_storage_state.json`, `python-agent/venv/`, `python-agent/__pycache__/`, and any postinstall artifacts.

6.5 Write/update `NOTES.md` scratchpad with decisions-locked summary.

### Phase 7 — Testing (1–2 hours)

See §9 below.

---

## 6. Affected / New Files

| File | Purpose | New/Modified |
|---|---|---|
| `pplx-research-plugin/package.json` | Package manifest, deps, exports | **New** |
| `pplx-research-plugin/tsconfig.json` | TypeScript config (extends @tsconfig/bun) | **New** |
| `pplx-research-plugin/src/index.ts` | Plugin entrypoint — wires `tool` hook | **New** |
| `pplx-research-plugin/src/tool.ts` | `pplx_research` tool definition + execute | **New** |
| `pplx-research-plugin/src/config.ts` | Options parsing (Zod) | **New** |
| `pplx-research-plugin/src/selectors.ts` | Ported CSS selector tables (reference) | **New** |
| `pplx-research-plugin/src/citation.ts` | Citation type + parsing utilities | **New** |
| `pplx-research-plugin/src/report.ts` | ResearchReport + Markdown rendering | **New** |
| `pplx-research-plugin/src/browser.ts` | (Option A future) Playwright browser management | **New** (future) |
| `pplx-research-plugin/README.md` | Overview + quick-start | **New** |
| `pplx-research-plugin/DEVELOPMENT-PLAN.md` | This document | **New** |
| `pplx-research-plugin/NOTES.md` | Scratchpad | **New** |
| `pplx-research-plugin/.gitignore` | Ignore storage_state, reports/ | **New** |

---

## 7. Permission & Security Model

### 7.1 Browser Automation

- The Python agent launches a real browser (headless or visible). This is equivalent to the user running a script in their terminal — not a sandbox escape, but risky if the machine is untrusted.
- The plugin should gate `pplx_research` execution with `ctx.ask()` (permission.ask hook) on first use per session, similar to how opencode gates `bash` and `todo_write`. Pattern: `ctx.ask({ permission: "tool:pplx_research", patterns: ["*"], always: [], metadata: {} })`.

### 7.2 Perplexity Terms of Service

- Automated browser interaction with perplexity.ai may violate their ToS if done at scale or commercially. This plugin is intended for **personal, low-throughput research** by individual developers.
- Users should review Perplexity's ToS before using the plugin. A disclaimer in the README should note this.

### 7.3 Storage State (Auth Cookies)

**Critical.** `storage/pplx_storage_state.json` contains full auth cookies for perplexity.ai.
- The file **must** be `.gitignore`d.
- The plugin **must never** echo the file contents in tool output, metadata, or error messages.
- The file should live inside the Python agent's directory (not in the plugin or user's project root where it might be accidentally committed) — resolved OQ-2.
- A sanity check in the tool's execute function: if the file exists, verify its permissions are not world-readable (0600 on Unix) and warn if they are loose.

### 7.5 Postinstall Supply-Chain Concerns (resolved OQ-8)

The `postinstall` script runs `pip install` and `playwright install` on the user's machine. This has several implications:

- **Supply chain**: `pip install -r python-agent/requirements.txt` pulls packages from PyPI. The user trusts the plugin's `requirements.txt` to list correct versions. The postinstall should never run `curl <url> | bash` or similar patterns. Use only pinned requirements.
- **Privilege escalation**: `pip install` may need `--user` on some systems, or `sudo` on others. The postinstall script should NOT use `sudo`. Prefer `pip install --user` or `uv pip install` in a venv. If permission errors occur, print clear instructions and exit 0.
- **Network**: `pip install` and `playwright install` require internet access. If offline, the postinstall prints warnings and continues.
- **Inspection**: Users can (and should) inspect `scripts/bootstrap-python.mjs` and `python-agent/requirements.txt` before installing. Document this in the README.

### 7.4 `ctx.ask` Permission Gating

The `execute()` function should call `ctx.ask()` before launching the subprocess:

```ts
await ctx.ask({
  permission: "pplx_research",
  patterns: [args.query],
  always: [],
  metadata: { mode: args.mode, output_dir: args.output_dir },
})
```

This lets opencode's permission system show the user what the tool is about to do and allow/deny/always-allow.

---

## 8. Potential Challenges

| Problem | Resolution |
|---|---|
| **Selector drift**: Perplexity changes their DOM, selectors break | Port the full selector tables now (§2.5). Add a `--debug` mode to the Python agent that logs which selectors matched. Schedule quarterly selector-audit. |
| **Cloudflare challenges**: headless browsers trigger CF verification | Reference already handles this (title/body detection + 30s wait). For Option B, this is inherited. For Option A, port the CF logic. |
| **Deep Research timeout vs tool-call latency**: 300s may exceed opencode's HTTP timeout or user patience | Return **intermediate progress** via `ctx.metadata()` (status-line updates: "Researching… Ns elapsed"). The Python agent's stdout (progress logs every 15s) is captured and returned at tool completion. For real-time feedback, opencode does not yet support streaming tool output (resolved OQ-4). |
| **Headless / no-display login impossibility**: Headed browser login (inline auto-login, OQ-5) requires a machine with a display | Document as a hard precondition in README. Detect missing display in the plugin (e.g. `process.env.DISPLAY` on Linux, or opencode's `serve` mode) and return a clear error: "pplx_research auto-login requires a display. Run `pplx_login` on a machine with a desktop, or manually run `python agent.py --login-autodetect` in a terminal with a display." |
| **DOM-poll login-detection fragility**: The logged-in indicator selector (e.g. `[data-testid="user-avatar"]`) may break when Perplexity changes their UI | Use a fallback chain of selectors (similar to the existing selector tables). Add a generous timeout (120s). If all selectors fail, return a clear error with manual login instructions. Consider a `--login-visible-timeout=N` flag for the Python agent as an escape hatch. |
| **Python env detection**: `python3` might not exist or be the wrong version | Check `python3 --version` at plugin init; surface a clear error. Allow override via plugin options. `postinstall` script handles this with warn-and-continue (OQ-8). |
| **Postinstall failures (PEP 668, no Python, no network, permissions)** | Graceful degradation: each bootstrap step prints actionable warnings on failure and continues. Only exit non-zero for truly unrecoverable states (missing `python-agent/` dir). Manual fallback commands printed at end of postinstall output. See §7.5 and Phase 6.1. (Resolved OQ-8) |
| **Subprocess security**: shell injection via query string | Use Bun `$` with template literals (auto-escapes). Do NOT concatenate strings into a shell command. |
| **Partial response on timeout**: Deep Research returns partial content after 300s | Surface the partial content with a clear warning: "Research timed out — partial results shown." |
| **File permission leakage**: storage_state is world-readable | Add a `chmod 600` step after saving. Add a check during plugin init. |

---

## 9. Testing Plan

### 9.1 Unit Tests (`bun test` — no live browser needed)

| Test | File |
|---|---|
| `parseOptions` with defaults, valid input, invalid input | `test/config.test.ts` |
| `parseOptions` rejects negative maxResearchWait | `test/config.test.ts` |
| `buildCommand` produces correct CLI array for each mode | `test/tool.test.ts` |
| `buildCommand` handles optional output_dir correctly | `test/tool.test.ts` |
| `parseReportPath` extracts path from "Report saved: /tmp/foo.md" | `test/tool.test.ts` |
| `parseReportPath` returns null for no match | `test/tool.test.ts` |
| `_parseCitation` regex: extracts url, title, year from sample strings | `test/citation.test.ts` |
| `_parseCitation`: classifies arxiv.org → academic, wikipedia.org → wiki, example.com → web | `test/citation.test.ts` |
| `_is_citation_text`: true for "1. Foo", "[1] Bar", "https://...", "Source:"; false for prose | `test/citation.test.ts` |
| `ResearchReport.to_markdown()` produces correct format with and without citations | `test/report.test.ts` |
| Selector tables are non-empty arrays (sanity) | `test/selectors.test.ts` |
| Selector tables contain no duplicates | `test/selectors.test.ts` |

### 9.2 Manual Live-Run Smoke Checklist

1. **Login:** `python3 agent.py --login-autodetect` → browser opens → log in → agent auto-detects login via DOM poll → verify `storage/pplx_storage_state.json` exists.
2. **Standard search:** `python3 agent.py "hello world" --mode standard --output /tmp/test_reports/` → verify report saved with content and citations.
3. **Deep Research:** `python3 agent.py "explain quantum computing" --mode deep --output /tmp/test_reports/` → verify progress logging every 15s, final report with `mode_used: "deep"`.
4. **Auto mode:** `python3 agent.py "what is rust" --mode auto --output /tmp/test_reports/` → verify it works regardless of Deep Research availability.
5. **Plugin integration:** Load the plugin in opencode against a test project. Call `pplx_research` with a simple query. If no auth, verify auto-login flow triggers (visible browser). Verify the ToolResult includes the Markdown report and the file attachment.
6. **Permissions:** Verify `ctx.ask` triggers on first tool use, and `always allow` works on subsequent uses.
7. **Python missing:** Remove python → call tool → verify clear error message.
8. **Auth expired/invalid:** Delete or corrupt `storage_state` → call `pplx_research` → verify inline auto-login triggers (visible browser, DOM-poll detection, then research proceeds).
9. **Timeout:** Set `max_research_wait=10` → run a complex deep query → verify partial content warning.

---

## 10. Resolved Decisions

*All eight open questions from the initial drafting phase have been resolved by the user (2026-06-07). The resolutions below are now design constraints — they supersede any earlier "recommendation" drafts in this document.*

| # | Decision | Resolution |
|---|---|---|
| **OQ-1** | **Integration strategy**: Option B (shell to Python) vs Option A (TS Playwright in-process) for v1? | **Option B.** Shell out to the Python agent via Bun `$` from PluginInput. Fastest path to working tool, reuses the battle-tested reference. Migrate to Option A/C after v1 feedback on UX pain-points. *(Unchanged from initial recommendation.)* |
| **OQ-2** | Where should `storage/pplx_storage_state.json` live? | **(a)** Inside the bundled Python agent dir (`python-agent/storage/`), always gitignored. The auth file is a user-specific secret, not project-scoped. *(Unchanged.)* |
| **OQ-3** | Should the plugin ship as a workspace-internal package or as a standalone npm package? | **Standalone npm package** `@opencode-ai/plugin-pplx-research`. Installed by end users via the `plugin` array in `opencode.json`. NOT a workspace-internal package. The npm package ships the Python agent source inside it (see OQ-7). |
| **OQ-4** | How to surface the long Deep Research wait (3–5 min) to the opencode user while the tool call is in-flight? | opencode does **NOT** stream subprocess stdout into the chat/TUI transcript line-by-line. Therefore: (a) The Python agent's captured stdout (incl. every-15s progress logs) is returned to the model **once, at tool completion** — not live. (b) For in-flight feedback, the plugin SHOULD call `ctx.metadata({ title, metadata })` periodically to update the tool's status line (e.g. "Researching… 45s elapsed"), but this is a status line, not a live log tail. (c) The **camoufox/browser GUI window IS visible** to the user — it's a real OS window on their machine, independent of the TUI. So during login the user genuinely sees and interacts with the browser. (d) **Hard constraint:** visible login and any headed browser interaction only work when opencode runs on a machine **with a display** (local TUI/desktop). In headless/remote/`serve` mode there is no display, so interactive login cannot happen — document this as a limitation and precondition. |
| **OQ-5** | Should the `pplx_login` tool be a separate tool, or should `pplx_research` auto-detect missing auth and prompt? | **OVERRIDE.** `pplx_research` **auto-detects missing/invalid auth and triggers the login flow inline**, then continues the research once login succeeds. Concretely: on invocation, `pplx_research` checks whether `storage_state` exists AND appears valid. If missing/invalid → it launches the Python agent in visible (headed) camoufox login mode. The Python login path MUST be changed to **auto-detect successful login by polling the DOM** for a logged-in indicator (e.g. account/avatar element presence, or absence of login button) and auto-save `storage_state` — instead of waiting for `input("Press Enter…")` which is impossible through a plugin shell-out. Keep `pplx_login` as an explicit/manual re-auth entry point. Subject to the display precondition from OQ-4. See §4.4 for detailed design. |
| **OQ-6** | Citation extraction: do it in Python (as now) or in TS (post-process the Markdown)? | **Python-side citation extraction** for v1. The Python `_extract_citations` is DOM-aware (extracts `<a>` hrefs). Post-processing raw Markdown for citations is fragile. If migrating to Option A, port citation extraction to TS. *(Unchanged.)* |
| **OQ-7** | Package the Python agent alongside the plugin, or require the user to check it out separately? | **Self-contained / bundle** the Python agent inside the plugin package (under `python-agent/`). The npm package ships the Python agent source inside it. Works with OQ-3: the standalone npm package bundles the Python agent. *(Unchanged.)* |
| **OQ-8** | Should the plugin auto-install Python deps? | **OVERRIDE** the earlier "no auto-install" recommendation. Installing the plugin SHOULD also install its dependencies: (a) npm/bun JS deps come naturally when the plugin package is installed. (b) For the **Python** deps (playwright/camoufox/etc.): add an npm **`postinstall`** script in `package.json` that bootstraps the Python side — runs `pip install -r python-agent/requirements.txt` and `playwright install chromium`. (c) **Graceful degradation:** detect missing Python, PEP 668 externally-managed-pip environments, no network, permissions errors — print actionable instructions and continue (`exit 0`, not `exit 1`). Prefer warn-and-continue so a JS-only install isn't blocked. Only exit non-zero when truly unrecoverable (e.g. `python-agent/` directory missing). Keep manual commands documented as a fallback. See Phase 6.1 and §7.5 for detailed design. |

---

*Reference: /Users/nghiango-mbp/git_repo/universal-agent_v2/compiled_agents/pplx_deep_research | Last updated: 2026-06-07*
