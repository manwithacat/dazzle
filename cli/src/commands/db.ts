/**
 * db command - Database operations
 *
 * Replaces: dazzle dnr migrate
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'

const DbArgs = z.object({
  action: z.enum(['migrate', 'seed', 'reset']).default('migrate').describe('Database action'),
  production: z.boolean().default(false).describe('Run against production database'),
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

Use --production flag for production database (requires confirmation).
`,
  examples: [
    'dazzle db',
    'dazzle db migrate',
    'dazzle db seed',
    'dazzle db reset',
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

    // Safety check for destructive operations in production
    if (args.production && args.action === 'reset') {
      return error(
        'SAFETY_CHECK',
        'Cannot reset production database from CLI',
        'This operation is too destructive for automated execution. Use database tools directly with appropriate backups.'
      )
    }

    // Map actions to Python CLI commands
    const actionMap: Record<string, string[]> = {
      migrate: ['dnr', 'migrate'],
      seed: ['dnr', 'seed'],
      reset: ['dnr', 'migrate', '--reset'],
    }

    const cliArgs = actionMap[args.action] || ['dnr', 'migrate']
    if (args.production) cliArgs.push('--production')

    // Run database command
    const python = 'python3'

    console.log(`Running database ${args.action}...`)

    const proc = Bun.spawn([python, '-m', 'dazzle', ...cliArgs], {
      cwd: ctx.cwd,
      stdio: ['inherit', 'inherit', 'inherit'],
      env: {
        ...process.env,
        PYTHONPATH: new URL('../../../../src', import.meta.url).pathname,
      },
    })

    const exitCode = await proc.exited
    const duration_ms = Date.now() - startTime

    if (exitCode !== 0) {
      return error(
        'DB_FAILED',
        `Database ${args.action} failed with exit code ${exitCode}`,
        'Check the output above for details'
      )
    }

    return success(
      {
        action: args.action,
        production: args.production,
        duration_ms,
      },
      { duration_ms }
    )
  },
}
