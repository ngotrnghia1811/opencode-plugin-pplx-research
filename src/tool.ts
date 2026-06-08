/**
 * pplx_research tool definition — args schema and types.
 *
 * The actual shell-execution body (execute()) lives in src/index.ts,
 * wired through the `tool` hook.  This module exports only the shared
 * arg schema and the derived TypeScript type so both index.ts and
 * callers can stay in sync.
 */
import { tool } from "@opencode-ai/plugin"
import type { z } from "zod"

/** Argument schema for the `pplx_research` tool. */
export const pplxResearchArgs = {
  query: tool.schema
    .string()
    .describe("Research query or topic"),
  mode: tool.schema
    .enum(["deep", "standard", "auto"])
    .default("auto")
    .describe(
      "Research mode: 'deep' (force Deep Research), 'standard' (skip toggle), 'auto' (try deep, fall back)"
    ),
  save: tool.schema
    .boolean()
    .default(true)
    .describe("Whether to save the report as a Markdown file on disk"),
  output_dir: tool.schema
    .string()
    .optional()
    .describe("Override output directory for saved reports"),
} as const

/** Inferred TypeScript type for the tool's arguments. */
export type PplxResearchArgs = z.infer<z.ZodObject<typeof pplxResearchArgs>>
