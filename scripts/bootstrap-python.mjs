#!/usr/bin/env node
/**
 * bootstrap-python.mjs — postinstall Python dependency bootstrapper
 *
 * Called from package.json "postinstall" script.
 * Gracefully sets up the bundled Python agent — fails are non-fatal.
 *
 * Steps:
 *   1. Detect Python ≥ 3.10
 *   2. pip install -r python-agent/requirements.txt
 *   3. python -m camoufox fetch
 *
 * Every step prints coloured status lines and, on failure, actionable
 * manual-install instructions.  Always exits 0 so npm/bun install succeeds
 * even when Python is missing or the network is offline.
 */

import { execFileSync } from "node:child_process"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { existsSync } from "node:fs"

// ── Paths ────────────────────────────────────────────────────────────────
const scriptsDir = dirname(fileURLToPath(import.meta.url))
const pythonAgentDir = resolve(scriptsDir, "..", "python-agent")
const requirementsFile = resolve(pythonAgentDir, "requirements.txt")
const venvPython = resolve(pythonAgentDir, ".venv", "bin", "python")

// ── Colour helpers (ANSI, works in most terminals) ───────────────────────
const useColor = process.stdout.isTTY || process.env.FORCE_COLOR
const c = useColor
  ? { reset: "\x1b[0m", ok: "\x1b[32m", warn: "\x1b[33m", err: "\x1b[31m", info: "\x1b[36m" }
  : { reset: "", ok: "", warn: "", err: "", info: "" }

function ok(msg) {
  console.log(`${c.ok}✓${c.reset} ${msg}`)
}
function alert(label, msg) {
  console.log(`${label} ${msg}${c.reset}`)
}
function pwarn(msg) {
  alert(c.warn + "⚠", msg)
}
function perr(msg) {
  alert(c.err + "✗", msg)
}
function pinfo(msg) {
  alert(c.info + "→", msg)
}

// ── Step 1: Detect Python 3.10+ ─────────────────────────────────────────

let pythonBin = process.env.pythonBin || null

if (!pythonBin) {
  const candidates = ["python3", "python"]
  for (const cand of candidates) {
    try {
      execFileSync(cand, ["--version"], { timeout: 5000 })
      pythonBin = cand
      break
    } catch {
      /* continue */
    }
  }
}

if (!pythonBin) {
  pwarn("Python not found (tried python3, python, and $pythonBin env).")
  pinfo("Skipping Python bootstrap — plugin will still install.")
  pinfo("To use pplx-research, install Python 3.10+ then run manually:")
  pinfo("  pip install -r python-agent/requirements.txt")
  pinfo("  python -m camoufox fetch")
  process.exit(0)
}

try {
  const ver = execFileSync(pythonBin, ["--version"], { encoding: "utf-8" })
  const m = ver.match(/Python (\d+)\.(\d+)/)
  if (m) {
    const major = Number(m[1])
    const minor = Number(m[2])
    if (major < 3 || (major === 3 && minor < 10)) {
      pwarn(`Python ${major}.${minor} found (need ≥ 3.10). Skipping bootstrap.`)
      process.exit(0)
    }
  }
} catch {
  pwarn("Could not determine Python version. Skipping bootstrap.")
  process.exit(0)
}

ok(`Python found: ${pythonBin}`)

// ── Choose pip/camoufox runner (prefer .venv if present) ────────────────

const runner = existsSync(venvPython) ? venvPython : pythonBin

if (existsSync(venvPython)) {
  ok(`Using virtual env: ${venvPython}`)
}

// ── Step 2: pip install ─────────────────────────────────────────────────

pinfo(`Installing Python dependencies from ${requirementsFile} ...`)

function runPip(extraArgs = []) {
  execFileSync(
    runner,
    ["-m", "pip", "install", "-r", "requirements.txt", "--quiet", ...extraArgs],
    { cwd: pythonAgentDir, stdio: "inherit" },
  )
}

try {
  runPip()
  ok("Python dependencies installed.")
} catch (e) {
  // PEP 668 "externally managed" environment — retry with --break-system-packages
  if (e.stderr && String(e.stderr).includes("xternally managed")) {
    pinfo("PEP 668 detected — retrying with --break-system-packages ...")
    try {
      runPip(["--break-system-packages"])
      ok("Python dependencies installed (--break-system-packages).")
    } catch {
      perr("pip install failed even with --break-system-packages.")
      pinfo("Install dependencies manually:")
      pinfo(`  cd ${pythonAgentDir}`)
      pinfo("  pip install -r requirements.txt --break-system-packages")
    }
  } else {
    perr("pip install failed.")
    pinfo("Install dependencies manually:")
    pinfo(`  cd ${pythonAgentDir}`)
    pinfo("  pip install -r requirements.txt")
  }
}

// ── Step 3: camoufox fetch ──────────────────────────────────────────────

pinfo("Downloading camoufox browser (patched Firefox) ...")
pinfo("  This may take a few minutes on first install.")

try {
  execFileSync(runner, ["-m", "camoufox", "fetch"], {
    cwd: pythonAgentDir,
    stdio: "inherit",
  })
  ok("camoufox browser downloaded.")
} catch {
  perr("camoufox fetch failed.")
  pinfo("Download the browser manually:")
  pinfo(`  cd ${pythonAgentDir}`)
  pinfo("  python -m camoufox fetch")
}

process.exit(0)
