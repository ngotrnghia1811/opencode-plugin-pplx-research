# NOTES — pplx-research-plugin

Scratchpad for the next developer. Things to verify, reference paths, and
opencode contract facts relied upon.

## Reference Implementation Files Consulted

| File | Key Content |
|---|---|
| `.../compiled_agents/pplx_deep_research/agent.py` | CLI entrypoint: login capture, research runner, arg parsing |
| `.../compiled_agents/pplx_deep_research/config.json` | Default config (headless, timeout, research_mode, output_dir) |
| `.../compiled_agents/pplx_deep_research/source_spec.json` | Source spec used by universal-agents compiler |
| `.../compiled_agents/pplx_deep_research/requirements.txt` | Python deps: playwright>=1.40, httpx, pyyaml, rich, playwright-stealth |
| `src/universal_agents/providers/pplx/research.py` | Core: ResearchReport, _enable_deep_research, _wait_for_research_response, _extract_citations |
| `src/universal_agents/providers/pplx/chat.py` | Citation type, _parse_citation, _is_citation_text |
| `src/universal_agents/providers/pplx/selectors.py` | All 52 CSS selectors across 8 categories |
| `src/universal_agents/providers/pplx/config.py` | PerplexityConfig, PerplexityResearchConfig (research_mode enum) |
| `src/universal_agents/browser/browser_manager.py` | Playwright lifecycle, Camoufox/Chromium launch, Cloudflare handling, stealth, storage_state |
| `src/universal_agents/browser/base_browser_agent.py` | Base class: _ensure_ready, chat(), _send_message, click_submit |
| `src/universal_agents/browser/response_detector.py` | Response stabilization: wait_for_new_response, copy button extraction |
| `src/universal_agents/browser/selectors.py` | ProviderSelectors dataclass |
| `src/universal_agents/core/config.py` | BaseConfig, BrowserConfig (timeout, headless, storage_state, etc.) |

## OpenCode Plugin Contract Facts

These were verified by reading the `@opencode-ai/plugin` source (`packages/plugin/src/`):

1. **Plugin type**: `Plugin = (input: PluginInput, options?: PluginOptions) => Promise<Hooks>`.
2. **PluginInput**: `{ client, project, directory, worktree, serverUrl, $ }`. `$` is BunShell — allows running shell commands via template literal.
3. **PluginOptions**: `Record<string, unknown>` — parsed from the second element of the `plugin` array tuple in `opencode.json`.
4. **tool hook**: `{ tool: { [key: string]: ToolDefinition } }`. Tool names that collide with builtins OVERRIDE them — so namespace with `pplx_`.
5. **tool() fn**: `import { tool } from "@opencode-ai/plugin"`. Takes `{ description, args (zod shape), execute(args, context): Promise<ToolResult> }`. Uses `z` from zod (re-exported as `tool.schema`).
6. **ToolContext**: `{ sessionID, messageID, agent, directory, worktree, abort, metadata({title?, metadata?}), ask({permission, patterns, always, metadata}) }`.
7. **ToolResult**: `string | { title?, output, metadata?, attachments?: [{type:"file", mime, url, filename?}] }`.
8. **ToolAttachment**: `{ type: "file", mime: string, url: string, filename?: string }`.
9. **OpenCode code style** (from `opencode/AGENTS.md`): `const` over `let`, early return (no `else`), avoid try/catch and `any`, Bun APIs, type inference preferred, snake_case drizzle fields.
10. **Tests**: run from package dir with `bun test`, never from repo root (guard exists).
11. **Typecheck**: `tsgo --noEmit` (plugin-reminders pattern) or `bun typecheck`.
12. **Package template**: `plugin-reminders/` — `package.json` (name `@opencode-ai/plugin-*`, type module, workspace deps), `tsconfig.json` (extends `@tsconfig/bun`), `src/index.ts`, `test/`.

## Things to Verify Against Live Perplexity.ai

Before claiming the plugin works, the next developer should:

1. **Run login flow manually**: `python3 agent.py --login` — does it still work? Has Perplexity added SSO/CAPTCHA changes?
2. **Verify selectors still match**: After login, `python3 agent.py "test" --visible --mode standard` and watch the browser. Are the input/submit/response elements matching? If not, update `selectors.ts` AND the Python `selectors.py`.
3. **Deep Research availability**: Is the Deep Research toggle present for free-tier users? Pro-only? The `auto` mode handles this gracefully (falls back), but `deep` mode will error.
4. **Cloudflare challenges**: Run headless. Does the CF detection still trigger? The Camoufox path may need updating (Camoufox versions are tightly coupled to Firefox versions).
5. **Storage state expiry**: How long do Perplexity cookies last? Does the session persist across days? Test: login Monday, research Tuesday with `--headless`.
6. **Rate limits**: Does Perplexity throttle headless browser queries? Test with 3-5 sequential queries.
7. **Citation format**: Has Perplexity changed how they render source citations? The selector `.sources-list` may have been renamed. Run a query with `--visible` and inspect the DOM.
8. **Markdown rendering in response**: The `inner_text()` extraction produces newlines from block elements. Verify the output Markdown is well-formatted. If Perplexity changed their response container structure, the copy-button extraction fallback may need updating.

## Python Agent Bundling Notes

- The Python agent (`agent.py` + all of `src/universal_agents/`) lives at:
  `/Users/nghiango-mbp/git_repo/universal-agent_v2/compiled_agents/pplx_deep_research/`
  and its source modules at:
  `/Users/nghiango-mbp/git_repo/universal-agent_v2/src/universal_agents/`
- For bundling inside this plugin, copy the `compiled_agents/pplx_deep_research/` directory as `python-agent/` and ensure the import paths resolve. The `agent.py` imports `from universal_agents.providers.pplx.*` — these need to be findable. Options:
  - (a) Set `PYTHONPATH` to include `src/` from the universal-agent_v2 repo.
  - (b) Copy `src/universal_agents/` alongside `python-agent/` and adjust `sys.path`.
  - (c) Install the `universal_agents` package as a pip editable install.
  - For v1, recommend (b) — it makes the plugin self-contained.

## OpenCode Integration Hacks / Gotchas

- **Tool output size**: Deep Research reports can be 10K–50K chars. This is well within opencode's context window for a tool result, but may be large for follow-up messages. The file attachment pattern (return the path as metadata + attach via `attachments: [{type:"file", ...}]`) lets the agent reference it without consuming full context.
- **`ctx.ask` timing**: The permission.ask hook fires *before* the tool executes. If the user denies, the tool never runs. If they "always allow", it's cached in the session.
- **Abort signal**: `ctx.abort` is an `AbortSignal`. If the user cancels the opencode turn, the tool's subprocess should be killed. Pass `{ signal: ctx.abort }` to Bun `$` if supported, or track it manually.
- **Plugin loading**: opencode loads plugins at startup. If the Python agent is missing, the plugin should still load (don't crash) — surface the error when the tool is actually called.

## gitignore

```
# Must be gitignored — contains auth cookies
python-agent/storage/pplx_storage_state.json
python-agent/storage/

# Optional — report output dirs
reports/

# Python venv if created locally
python-agent/.venv/
python-agent/__pycache__/
```

## Decisions Locked 2026-06-07 (OQ1-8)

All eight open questions from the initial DEVELOPMENT-PLAN.md draft are now resolved.
These are design constraints, not recommendations.

| # | Resolution |
|---|---|
| **OQ-1** | **Option B confirmed.** Shell to Python agent via Bun `$` from PluginInput. |
| **OQ-2** | `storage/pplx_storage_state.json` lives inside `python-agent/storage/`, always gitignored. |
| **OQ-3** | **Standalone npm package** `@opencode-ai/plugin-pplx-research`. Installed via `plugin` array. Ships Python agent inside it (OQ-7). |
| **OQ-4** | No live subprocess stdout streaming in opencode. Use `ctx.metadata()` for status-line updates ("Researching… Ns elapsed"). Camoufox browser GUI IS visible (real OS window). Hard constraint: headed login only works on machines with a display (local TUI/desktop). |
| **OQ-5** | `pplx_research` **auto-detects missing/invalid auth and triggers inline login**, then continues research. `pplx_login` kept as explicit re-auth entry point. Python `capture_login()` MUST be changed to DOM-poll for logged-in indicator instead of blocking on `input("Press Enter…")`. |
| **OQ-6** | Python-side citation extraction (DOM-aware). Port to TS if migrating to Option A. |
| **OQ-7** | Python agent bundled inside the plugin package under `python-agent/`. |
| **OQ-8** | **Postinstall bootstraps Python deps** (`pip install`, `playwright install chromium`) with graceful degradation. Each step warns and continues on failure — JS-only installs are not blocked. Manual fallback commands documented. |

### Key Engineering Consequences

**1. Python `capture_login()` must DOM-poll, not wait for stdin.** The reference `agent.py` uses `input("Press Enter…")` to signal login completion. Through a plugin shell-out via Bun `$`, there is no interactive stdin for the user. The bundled Python agent MUST be changed to poll the DOM for a logged-in indicator (e.g. `[data-testid="user-avatar"]`, absence of `button:has-text("Log in")`) on a 2s interval, with a 120s timeout. When detected, save `context.storage_state()` and exit. This is an implementation change to the Python agent, not the TS plugin. A new flag `--login-autodetect` (or a modification of `--login`) activates this path. See DEVELOPMENT-PLAN.md §4.4 for the polling-loop sketch.

**2. Postinstall must bootstrap Python deps with graceful degradation.** The `scripts.postinstall` entry in `package.json` runs during `npm install` / `bun install`. It must handle: missing Python, PEP 668 externally-managed-pip, no network, permission errors — all with warn-and-continue (exit 0). Only exit non-zero for truly unrecoverable states (e.g. `python-agent/` directory missing). Implementation lives in `scripts/bootstrap-python.mjs`. See DEVELOPMENT-PLAN.md Phase 6.1 for the full design.
