/**
 * @opencode-ai/plugin-pplx-research
 *
 * Plugin entrypoint.
 *
 * Registers two custom tools:
 *   - pplx_research  — submit a research query to Perplexity AI via browser.
 *                      Auto-detects missing auth and triggers inline login (OQ-5).
 *   - pplx_login     — explicit manual Perplexity login session capture (re-auth).
 *
 * Integration strategy (v1): Shells out to the Python Playwright agent
 * (bundled under python-agent/) via Bun's `$` shell (PluginInput.$).
 * The Python agent is the battle-tested reference from:
 *   /Users/nghiango-mbp/git_repo/universal-agent_v2/compiled_agents/pplx_deep_research
 *
 * Key design decisions (2026-06-07):
 *   - OQ-1: Option B — shell to Python via Bun $ (confirmed)
 *   - OQ-2: storage_state lives inside python-agent/storage/, gitignored (confirmed)
 *   - OQ-3: standalone npm package @opencode-ai/plugin-pplx-research
 *   - OQ-4: no live stdout streaming; use ctx.metadata() for status line;
 *           headed browser only works with display (local TUI/desktop)
 *   - OQ-5: pplx_research auto-detects missing auth → inline login → continues research;
 *           Python capture_login() must DOM-poll, not wait for stdin Enter
 *   - OQ-6: Python-side citation extraction (confirmed)
 *   - OQ-7: Python agent bundled under python-agent/ (confirmed)
 *   - OQ-8: postinstall bootstraps Python deps with graceful degradation
 *
 * See DEVELOPMENT-PLAN.md for full architecture, trade-offs, and migration path.
 */
import type { Plugin } from "@opencode-ai/plugin"
import { tool } from "@opencode-ai/plugin"
import path from "node:path"
import fs from "node:fs"
import { parseOptions, type ResolvedOptions } from "./config.js"
import { pplxResearchArgs, type PplxResearchArgs } from "./tool.js"
import { parseCitation, isCitationText, type Citation } from "./citation.js"
import { toMarkdown, type ResearchReport } from "./report.js"

export const PplxResearchPlugin: Plugin = async (pluginCtx, options) => {
  const opts = parseOptions(options)
  // Capture Bun $ shell from PluginInput for use in tool execute closures.
  // (ToolContext does not have $ — only PluginInput does.)
  const $ = pluginCtx.$

  // ── Inline login helper (closes over $, opts) ────────────────
  /**
   * Launch the Python agent in login mode (headed browser, DOM-poll).
   *
   * The Python agent opens a visible browser, the user logs in to
   * Perplexity, and the agent auto-detects login success via DOM
   * polling (no stdin).  Returns `true` if the subprocess exited 0.
   *
   * Wired to `AbortSignal` — rejects if opencode cancels the tool call.
   * See DEVELOPMENT-PLAN.md §4.4 (resolved OQ-5).
   */
  async function runInlineLogin(agentDir: string, abort: AbortSignal): Promise<boolean> {
    const shell = $.cwd(agentDir)
    const proc = shell`${opts.pythonBin} agent.py --login`.nothrow()

    const abortPromise = new Promise<never>((_, reject) => {
      if (abort.aborted) {
        reject(new Error("Login aborted"))
        return
      }
      const onAbort = () => reject(new Error("Login aborted"))
      abort.addEventListener("abort", onAbort, { once: true })
    })

    let result: { exitCode: number }
    try {
      result = await Promise.race([proc, abortPromise])
    } catch {
      return false
    }

    return result.exitCode === 0
  }

  return {
    tool: {
      // ── pplx_research ──────────────────────────────────────────
      pplx_research: tool({
        description: [
          "Submit a research query to Perplexity AI and return a structured Markdown",
          "report with citations. Supports three modes:",
          "  - 'auto' (default): Try Deep Research mode, fall back to standard search if unavailable.",
          "  - 'deep': Force Deep Research mode (errors if unavailable, may take 3–5 minutes).",
          "  - 'standard': Simple Perplexity search (fastest, ~30–60 seconds).",
          "If no login session exists, auto-launches a visible browser for login (requires a display).",
        ].join("\n"),
        args: pplxResearchArgs,

        async execute(args, toolCtx) {
          // ── Permission gate (§7.4) ────────────────────────────
          await toolCtx.ask({
            permission: "pplx_research",
            patterns: [args.query],
            always: [],
            metadata: { mode: args.mode },
          })

          // ── Resolve paths ────────────────────────────────────
          const agentDir = opts.agentPath ?? path.join(import.meta.dir!, "..", "python-agent")
          const agentScript = path.join(agentDir, "agent.py")
          const outputDir = args.output_dir ?? path.join(toolCtx.directory, opts.outputDir)
          const storageState = path.join(agentDir, "storage", "pplx_storage_state.json")

          // Verify Python agent is present
          if (!fs.existsSync(agentScript)) {
            return [
              "pplx_research: Python agent not found at:",
              `  ${agentScript}`,
              "Check agentPath in plugin config or ensure python-agent/ is bundled.",
            ].join("\n")
          }

          // ── Inline auth check & auto-login (§4.4, OQ-5) ─────
          if (!authValid(storageState)) {
            // Gate login with permission ask — warn about display requirement
            await toolCtx.ask({
              permission: "pplx_research:login",
              patterns: ["*"],
              always: [],
              metadata: {
                note: "Login required — a visible browser window will open. Requires a local display (headless/remote/serve cannot complete interactive login).",
              },
            })

            const loginOk = await runInlineLogin(agentDir, toolCtx.abort)
            if (!loginOk) {
              return [
                "pplx_research: Login required. The auto-login flow did not succeed.",
                "This may be because no display is available (headless/remote/serve mode).",
                "Run the `pplx_login` tool on a machine with a display, or manually:",
                `  cd ${agentDir} && ${opts.pythonBin} agent.py --login`,
              ].join("\n")
            }

            // Re-check auth after login
            if (!authValid(storageState)) {
              return "pplx_research: Login appeared to succeed but storage state not found. Run pplx_login manually."
            }
          }

          // ── Execute Python agent ─────────────────────────────
          const startTime = Date.now()

          // Progress updates via ctx.metadata (§4.5, OQ-4)
          const statusInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - startTime) / 1000)
            toolCtx.metadata({
              title: `Researching… ${elapsed}s elapsed`,
              metadata: { elapsed_seconds: elapsed, query: args.query },
            })
          }, 10000)

          // Race the subprocess against the abort signal
          const shell = $.cwd(agentDir)
          const proc = shell`${opts.pythonBin} agent.py ${args.query} --mode ${args.mode} --output ${outputDir}`.nothrow()

          const abortPromise = new Promise<never>((_, reject) => {
            if (toolCtx.abort.aborted) {
              reject(new Error("Research aborted"))
              return
            }
            const onAbort = () => reject(new Error("Research aborted"))
            toolCtx.abort.addEventListener("abort", onAbort, { once: true })
          })

          let result: { readonly stdout: Buffer; readonly stderr: Buffer; readonly exitCode: number }
          try {
            result = await Promise.race([proc, abortPromise])
          } catch (err) {
            clearInterval(statusInterval)
            return `pplx_research: ${err instanceof Error ? err.message : "Aborted"}`
          } finally {
            clearInterval(statusInterval)
          }

          // ── Handle failure ───────────────────────────────────
          if (result.exitCode !== 0) {
            const stderr = result.stderr.toString().trim()
            const stdout = result.stdout.toString().trim()
            const tail = (stderr || stdout || "(no output)").split("\n").slice(-20).join("\n")
            return `Research failed (exit ${result.exitCode}):\n\`\`\`\n${tail}\n\`\`\``
          }

          // ── Parse report path and read result ─────────────────
          const stdout = result.stdout.toString()
          const reportPath = parseReportPath(stdout)
          if (!reportPath) {
            return `Research completed but couldn't parse report path from output.\n\nLast 1000 chars:\n\`\`\`\n${stdout.slice(-1000)}\n\`\`\``
          }

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
              type: "file" as const,
              mime: "text/markdown",
              url: `file://${reportPath}`,
              filename: path.basename(reportPath),
            }] : undefined,
          }
        },
      }),

      // ── pplx_login ───────────────────────────────────────────
      pplx_login: tool({
        description: [
          "Explicitly capture a fresh Perplexity login session.",
          "Opens a visible browser so you can log in. Login success is auto-detected",
          "via DOM polling (no terminal Enter required). The session is saved to disk",
          "and reused by pplx_research for subsequent queries.",
          "",
          "Use this when:",
          "  - Your session has expired and pplx_research auto-login failed",
          "  - You want to switch Perplexity accounts",
          "  - You are on a machine with a display and want to pre-authenticate",
          "",
          "Display required. Does not work in headless/remote/serve mode.",
        ].join("\n"),
        args: {},

        async execute(_args, toolCtx) {
          const agentDir = opts.agentPath ?? path.join(import.meta.dir!, "..", "python-agent")
          const agentScript = path.join(agentDir, "agent.py")

          if (!fs.existsSync(agentScript)) {
            return [
              "pplx_login: Python agent not found at:",
              `  ${agentScript}`,
              "Check agentPath in plugin config or ensure python-agent/ is bundled.",
            ].join("\n")
          }

          // Permission gate — display-required warning
          await toolCtx.ask({
            permission: "pplx_login",
            patterns: ["*"],
            always: [],
            metadata: {
              note: "A visible browser window will open for Perplexity login. Requires a local display.",
            },
          })

          // Run login subprocess
          const shell = $.cwd(agentDir)
          const proc = shell`${opts.pythonBin} agent.py --login`.nothrow()

          const abortPromise = new Promise<never>((_, reject) => {
            if (toolCtx.abort.aborted) {
              reject(new Error("Login aborted"))
              return
            }
            const onAbort = () => reject(new Error("Login aborted"))
            toolCtx.abort.addEventListener("abort", onAbort, { once: true })
          })

          let result: { readonly stdout: Buffer; readonly stderr: Buffer; readonly exitCode: number }
          try {
            result = await Promise.race([proc, abortPromise])
          } catch (err) {
            return `pplx_login: ${err instanceof Error ? err.message : "Aborted"}`
          }

          if (result.exitCode !== 0) {
            const stderr = result.stderr.toString().trim()
            const stdout = result.stdout.toString().trim()
            const tail = (stderr || stdout || "(no output)").split("\n").slice(-20).join("\n")
            return `pplx_login: Login failed (exit ${result.exitCode}):\n\`\`\`\n${tail}\n\`\`\``
          }

          const storageStatePath = path.join(agentDir, "storage", "pplx_storage_state.json")
          const sessionSaved = fs.existsSync(storageStatePath)
          const output = result.stdout.toString()

          if (sessionSaved) {
            return [
              "## Perplexity Login — Success",
              "",
              `Session saved to \`${storageStatePath}\`.`,
              "`pplx_research` will now use the saved session for subsequent queries.",
              "",
              "---",
              "<details><summary>Agent output</summary>",
              "",
              "```",
              output.slice(-2000),
              "```",
              "</details>",
            ].join("\n")
          }

          return [
            "## Perplexity Login — May Have Failed",
            "",
            `No session file found at \`${storageStatePath}\`.`,
            "The agent reported success but the storage state was not written.",
            "Try again or run manually:",
            "",
            `  cd ${agentDir} && ${opts.pythonBin} agent.py --login`,
            "",
            "---",
            "<details><summary>Agent output</summary>",
            "",
            "```",
            output.slice(-2000),
            "```",
            "</details>",
          ].join("\n")
        },
      }),
    },
  }
}

export default PplxResearchPlugin

/**
 * Check whether a Perplexity storage_state file exists and appears valid.
 *
 * "Valid" means: file exists, non-empty, and JSON-parses with expected keys.
 * A minimal check — full validation is done by the Python agent at load time.
 *
 * See DEVELOPMENT-PLAN.md §4.4 (resolved OQ-5).
 */
export function authValid(storageStatePath: string): boolean {
  try {
    if (!fs.existsSync(storageStatePath)) return false
    const raw = fs.readFileSync(storageStatePath, "utf-8")
    if (raw.trim().length === 0) return false
    const parsed = JSON.parse(raw)
    // A valid Playwright storageState has "cookies" and/or "origins" arrays
    const hasCookies = Array.isArray(parsed.cookies) && parsed.cookies.length > 0
    const hasOrigins = Array.isArray(parsed.origins) && parsed.origins.length > 0
    return hasCookies || hasOrigins
  } catch {
    // File missing, unreadable, or not valid JSON
    return false
  }
}

/**
 * Extract the report file path from the Python agent's stdout.
 *
 * The Python agent prints:
 *   Report saved: /absolute/path/to/report.md
 *
 * Returns the absolute path, or null if not found.
 */
export function parseReportPath(stdout: string): string | null {
  const match = stdout.match(/Report saved:\s+(.+\.md)/)
  return match?.[1] ?? null
}
