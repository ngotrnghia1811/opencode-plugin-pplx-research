# @ngotrnghia1811/plugin-pplx-research

An opencode plugin that exposes a `pplx_research` custom tool. The tool drives
[Perplexity AI](https://www.perplexity.ai) through a real browser (Camoufox —
patched Firefox via `camoufox>=0.4`) to perform research queries and returns
structured Markdown research reports with citations. Citations are extracted
from the Perplexity sources panel via the Copy button for clean Markdown output.

**Integration strategy:** Shells out to an existing, battle-tested Python
Camoufox agent via Bun's `$` shell. This keeps the plugin lightweight while
reusing a selector-stable, Cloudflare-hardened implementation. See
[DEVELOPMENT-PLAN.md](./DEVELOPMENT-PLAN.md) §3 for trade-off analysis.

## Quick Start

### 1. Install the plugin

Add to your `opencode.json` plugin array:

```jsonc
{
  "plugin": [
    ["@ngotrnghia1811/plugin-pplx-research", {
      "pythonBin": "python3",
      "outputDir": ".opencode/pplx-research-reports",
      "defaultMode": "deep",
      "maxResearchWait": 600
    }]
  ]
}
```

> **Note:** opencode installs plugins with `ignoreScripts: true`, so the
> package's `postinstall` hook does **not** run automatically. Instead, the
> plugin bootstraps itself at runtime: its `server()` hook checks for
> `.venv/bin/python` and, if missing, runs `scripts/bootstrap-python.mjs` to
> set up Python dependencies and download the Camoufox browser.

If the runtime bootstrap fails, you can run it manually from the plugin
directory:

```bash
cd python-agent/ && pip install -r requirements.txt
cd python-agent/ && python -m camoufox fetch
```

### 2. Log in to Perplexity

**Automatic.** When `pplx_research` is first called, it auto-detects missing
auth and launches a visible browser window for login. Log in to Perplexity —
the session is auto-detected via DOM polling (120-iteration poll loop,
~10 minutes max) and saved. The poll loop detects login through positive
indicators (profile image, avatar appearing in the DOM) and negative
indicator disappearance (login form vanishing). Both strict and lenient
detection modes are supported; lenient mode tolerates slower page loads.

You can also log in proactively via the `pplx_login` tool:

```bash
# Manual login from a terminal with a display:
cd python-agent/
python3 agent.py --login
```

> **Display required.** Headed browser login only works on machines with a
> display (local TUI/desktop). Does not work in headless/remote/serve mode.

### 3. Tool permissions

All agents see plugin tools by default — no agent config is required for the
`pplx_research` and `pplx_login` tools to be visible. The `permission` config
on an agent controls whether opencode prompts for confirmation before each
invocation:

| Value | Behavior |
|---|---|
| `"ask"` | Prompt the user before each tool call |
| `"allow"` | Auto-approve every call without prompting |
| `"deny"` | Block the tool entirely for that agent |

All plugin tools default to `"ask"` — the user must approve each use.

### 4. Use from opencode

The tool is available as `pplx_research` to any agent with tool access.
First use auto-launches login (visible browser) if no session exists:

```
> Research the latest advances in Rust async runtimes
(agent calls pplx_research tool; if no auth: browser opens → user logs in → research proceeds)
(agent receives Markdown report with citations)
```

## Tools

| Tool | Description |
|---|---|
| `pplx_research` | Submit a research query to Perplexity. Returns a Markdown report with citations. Mode: `"search"` (fast, ~30s) or `"deep"` (Deep Research, 2–10 min, Pro tier required). Deep Research is toggled via a two-step dropdown interaction (click mode selector → click "Deep research"). |
| `pplx_login` | Open a browser to capture a fresh Perplexity login session (manual re-auth). Auto-detects login via DOM poll — no Enter required. Uses positive indicators (profile image) and negative indicator disappearance. Supports strict and lenient detection modes. |

## Planning Docs

| File | Purpose |
|---|---|
| `DEVELOPMENT-PLAN.md` | Full design: feature description, reference analysis, integration strategy, architecture, implementation plan, tests, resolved decisions |
| `NOTES.md` | Scratchpad: reference file paths, contract facts, things to verify |
| `src/index.ts` | Plugin entrypoint skeleton |
| `src/selectors.ts` | Ported CSS selector tables from reference |

## Limitations

- **Latency**: Standard Search queries complete in ~30 seconds. Deep Research queries take 2–10 minutes. A status line shows elapsed time ("Researching… 45s elapsed") via `ctx.metadata()`. Full progress logs are returned at completion — opencode does not stream subprocess stdout live.
- **Display required for login**: Auto-login launches a visible browser window. This only works on machines with a display (local TUI/desktop). In headless/remote/`serve` mode, login must be performed separately on a machine with a display.
- **Deep Research requires Pro**: Deep Research mode requires a Perplexity Pro tier subscription. On free-tier accounts, the mode selector may not appear or the query will fall back to Search.
- **Copy button requires clipboard-read**: The citation extraction strategy uses the Copy button in the Perplexity sources panel. This requires the `clipboard-read` permission in the browser. Camoufox headless mode supports this; other browser configurations may not.
- **Python required**: The plugin shells out to a bundled Python agent. Python 3.10+ and the dependencies in `python-agent/requirements.txt` are required. The runtime bootstrap sets these up automatically; manual fallback is available if needed.
- **ToS**: Automated browser interaction may violate Perplexity's ToS if used at scale. Intended for personal, low-throughput research use.
- **Title-split heuristic**: Source names containing punctuation (e.g. "Bun (software)") can produce verbatim title output due to the split heuristic. URLs are unaffected — only the display title may be slightly malformed.

## Changelog

- **Camoufox engine integration**: The Python agent uses Camoufox (patched Firefox) instead of Playwright/Chromium. A previous silent fallback to Chromium was fixed; the agent validates the Camoufox binary at startup.
- **Login timing fix**: The browser no longer closes prematurely before login completes. A DOM polling loop (120 iterations, ~10 minutes max) detects login via positive and negative indicators.
- **Deep Research toggle fix**: The mode selector now uses a two-step dropdown interaction (click selector → click "Deep research" in the dropdown), matching the live Perplexity DOM.
- **Citation extraction**: Citations are extracted from the Perplexity sources panel via the Copy button, producing clean Markdown output. Requires clipboard-read permission (works in Camoufox headless mode).
- **Selector hardening**: All CSS selectors were verified against the live Perplexity DOM (2026-06-07).
- **Bootstrap script**: The `postinstall` script provides graceful Python + pip + Camoufox setup with actionable error messages on failure.
- **38 unit tests passing** (`bun test`).
