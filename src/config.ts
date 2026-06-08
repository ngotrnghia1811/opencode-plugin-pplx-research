/**
 * Plugin options parsing.
 *
 * Parses the second element of the plugin tuple from opencode.json:
 *
 *   { "plugin": [ ["@opencode-ai/plugin-pplx-research", { "pythonBin": "python3", ... }] ] }
 *
 * All fields have sensible defaults.  Unknown keys are silently ignored (Zod strip).
 */
import { z } from "zod"

const OptionsSchema = z.object({
  /** Path or name of the Python 3 binary.  Default "python3" (macOS/Linux). */
  pythonBin: z.string().default("python3"),
  /** Path to the bundled Python agent directory.  Defaults are resolved at runtime. */
  agentPath: z.string().optional(),
  /** Output directory for saved research reports (relative to ctx.directory). */
  outputDir: z.string().default("reports"),
  /** Default research mode for tool invocations that don't specify one. */
  defaultMode: z.enum(["deep", "standard", "auto"]).default("auto"),
  /** Max seconds to wait for Deep Research to complete.  Must be ≥ 1. */
  maxResearchWait: z.number().int().positive().default(300),
  /** If true, skip research and only run the login flow (used for first-time setup). */
  loginOnly: z.boolean().default(false),
})

export type ResolvedOptions = z.infer<typeof OptionsSchema>

/**
 * Parse and validate plugin options from opencode.json.
 *
 * Unknown keys are silently stripped (Zod default .strip() behaviour).
 * Missing keys get the defaults declared above.
 */
export function parseOptions(input: unknown): ResolvedOptions {
  return OptionsSchema.parse(input ?? {})
}
