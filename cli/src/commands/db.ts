/**
 * db command - Database operations
 *
 * Replaces: dazzle dnr migrate
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints, progress } from '../lib/output'

const DbArgs = z.object({
  action: z.enum(['migrate', 'seed', 'reset']).default('migrate').describe('Database action'),
  'dry-run': z.boolean().default(false).describe('Preview changes without applying'),
})

export const db: CommandDefinition<typeof DbArgs> = {
  name: 'db',
  description: 'Database operations (migrate, seed, reset)',
  help: `
Manage your database schema and data.

Actions:
  migrate  - Apply pending migrations (default)
  seed     - Populate with test data
  reset    - Drop and recreate all tables (DESTRUCTIVE)
`,
  examples: [
    'dazzle db',
    'dazzle db migrate',
    'dazzle db seed',
    'dazzle db reset',
    'dazzle db migrate --dry-run',
  ],
  args: DbArgs,

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

    progress({ type: 'progress', step: 1, total: 2, message: `Running ${args.action}...` }, ctx.output)

    // Map actions to bridge functions
    const actionMap: Record<string, string> = {
      migrate: 'db_migrate_json',
      seed: 'db_seed_json',
      reset: 'db_reset_json',
    }

    const bridgeFunc = actionMap[args.action] || 'db_migrate_json'

    // Call Python bridge
    const result = await ctx.python<Record<string, unknown>>(
      'dazzle.core.cli_bridge',
      bridgeFunc,
      {
        path: ctx.cwd,
        dry_run: args['dry-run'],
      }
    )

    if (!result.success) {
      return error(
        'DB_FAILED',
        result.error || `Database ${args.action} failed`,
        'Check that the project is valid and DNR backend is installed'
      )
    }

    progress({ type: 'progress', step: 2, total: 2, message: 'Done' }, ctx.output)

    const duration_ms = Date.now() - startTime

    return success(
      {
        action: args.action,
        ...result.data,
      },
      { duration_ms }
    )
  },
}
