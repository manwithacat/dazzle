/**
 * eject command - Generate standalone code
 *
 * Replaces: dazzle eject run
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints, progress } from '../lib/output'

const EjectArgs = z.object({
  output: z.string().default('./ejected').describe('Output directory'),
  backend: z.enum(['fastapi', 'none']).default('fastapi').describe('Backend framework'),
  frontend: z.enum(['react', 'none']).default('react').describe('Frontend framework'),
  'dry-run': z.boolean().default(false).describe('Preview without writing files'),
})

export const eject: CommandDefinition<typeof EjectArgs> = {
  name: 'eject',
  description: 'Generate standalone code from DSL',
  help: `
Generates standalone, production-ready code from your DAZZLE DSL definitions.

This creates a fully functional application that can be deployed without
the DAZZLE runtime. The generated code is yours to modify and extend.

Backend options:
  fastapi  - FastAPI with SQLAlchemy (default)
  none     - Skip backend generation

Frontend options:
  react    - React with TypeScript (default)
  none     - Skip frontend generation
`,
  examples: [
    'dazzle eject',
    'dazzle eject --output ./standalone',
    'dazzle eject --backend fastapi --frontend react',
    'dazzle eject --dry-run',
  ],
  args: EjectArgs,

  async run(args, ctx) {
    const startTime = Date.now()

    // Check if we have a project
    if (!ctx.configPath) {
      return error(
        ErrorHints.NO_PROJECT.code,
        'No dazzle.toml found',
        ErrorHints.NO_PROJECT.hint
      )
    }

    if (args['dry-run']) {
      progress({ type: 'progress', step: 1, total: 2, message: 'Analyzing project...' }, ctx.output)
    } else {
      progress({ type: 'progress', step: 1, total: 4, message: 'Analyzing project...' }, ctx.output)
    }

    // Call Python ejection
    const result = await ctx.python<{
      output_path: string
      backend_files: string[]
      frontend_files: string[]
      total_files: number
    }>(
      'dazzle.core.cli_bridge',
      'eject_project_json',
      {
        path: ctx.cwd,
        output: args.output,
        backend: args.backend,
        frontend: args.frontend,
        dry_run: args['dry-run'],
      }
    )

    if (!result.success) {
      return error(
        'EJECT_FAILED',
        result.error || 'Ejection failed',
        'Check that your project is valid with `dazzle check`'
      )
    }

    const duration_ms = Date.now() - startTime

    if (args['dry-run']) {
      progress({ type: 'progress', step: 2, total: 2, message: 'Done (dry run)' }, ctx.output)
      return success(
        {
          dry_run: true,
          would_create: result.data?.total_files || 0,
          backend_files: result.data?.backend_files || [],
          frontend_files: result.data?.frontend_files || [],
        },
        { duration_ms }
      )
    }

    progress({ type: 'progress', step: 4, total: 4, message: 'Done' }, ctx.output)

    return success(
      {
        output: result.data?.output_path || args.output,
        backend: args.backend,
        frontend: args.frontend,
        total_files: result.data?.total_files || 0,
        next_steps: [
          `cd ${args.output}`,
          args.backend !== 'none' ? 'pip install -r requirements.txt' : null,
          args.frontend !== 'none' ? 'cd frontend && npm install' : null,
          args.backend !== 'none' ? 'uvicorn main:app --reload' : null,
        ].filter(Boolean),
      },
      { duration_ms }
    )
  },
}
