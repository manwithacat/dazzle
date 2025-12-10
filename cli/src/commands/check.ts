/**
 * check command - Validate DSL files
 *
 * Replaces: dazzle validate + dazzle lint
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints, progress } from '../lib/output'

const CheckArgs = z.object({
  path: z.string().optional().describe('Project path (default: current directory)'),
  strict: z.boolean().default(false).describe('Treat warnings as errors'),
  fix: z.boolean().default(false).describe('Auto-fix issues where possible'),
})

interface ValidationResult {
  valid: boolean
  modules: Array<{
    name: string
    path: string
    entities: number
    surfaces: number
  }>
  entities: string[]
  surfaces: string[]
  errors: Array<{
    file: string
    line: number
    message: string
    code: string
  }>
  warnings: Array<{
    file: string
    line: number
    message: string
    code: string
  }>
}

export const check: CommandDefinition<typeof CheckArgs> = {
  name: 'check',
  description: 'Validate DSL files and check for issues',
  help: `
Parses all DSL modules, resolves dependencies, and validates the merged AppSpec.

With --strict, warnings are treated as errors (non-zero exit code).
With --fix, auto-fixable issues are corrected in place.
`,
  examples: [
    'dazzle check',
    'dazzle check --strict',
    'dazzle check ./my-project',
  ],
  args: CheckArgs,

  async run(args, ctx) {
    const startTime = Date.now()
    const projectPath = args.path ?? ctx.cwd

    // Check if we have a project
    if (!ctx.configPath) {
      return error(
        ErrorHints.NO_PROJECT.code,
        `No dazzle.toml found in ${projectPath}`,
        ErrorHints.NO_PROJECT.hint
      )
    }

    // Report progress
    progress({ type: 'progress', step: 1, total: 3, message: 'Parsing DSL files...' }, ctx.output)

    // Call Python to validate
    const result = await ctx.python<ValidationResult>(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      { path: projectPath, strict: args.strict }
    )

    if (!result.success) {
      return error(
        ErrorHints.PYTHON_ERROR.code,
        result.error || 'Validation failed',
        ErrorHints.PYTHON_ERROR.hint,
        { stderr: result.stderr }
      )
    }

    progress({ type: 'progress', step: 2, total: 3, message: 'Checking lint rules...' }, ctx.output)

    const data = result.data!
    const duration_ms = Date.now() - startTime

    progress({ type: 'progress', step: 3, total: 3, message: 'Done' }, ctx.output)

    // Format response
    if (!data.valid || (args.strict && data.warnings.length > 0)) {
      const issues = [...data.errors, ...(args.strict ? data.warnings : [])]
      const firstIssue = issues[0]

      return {
        success: false,
        error: {
          code: ErrorHints.INVALID_DSL.code,
          message: `Found ${data.errors.length} error(s) and ${data.warnings.length} warning(s)`,
          __agent_hint: firstIssue
            ? `First issue at ${firstIssue.file}:${firstIssue.line}: ${firstIssue.message}`
            : ErrorHints.INVALID_DSL.hint,
          context: {
            errors: data.errors,
            warnings: data.warnings,
          },
        },
        meta: { duration_ms },
      }
    }

    return success(
      {
        valid: true,
        modules: data.modules.length,
        entities: data.entities.length,
        surfaces: data.surfaces.length,
        warnings: data.warnings.length,
        details: {
          modules: data.modules,
          entities: data.entities,
          surfaces: data.surfaces,
        },
      },
      { duration_ms }
    )
  },
}
