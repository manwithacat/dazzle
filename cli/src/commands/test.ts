/**
 * test command - Run tests
 *
 * Replaces: dazzle test run, dazzle dnr test
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'

const TestArgs = z.object({
  flow: z.string().optional().describe('Specific flow to run'),
  headless: z.boolean().default(true).describe('Run in headless mode'),
  coverage: z.boolean().default(false).describe('Generate UX coverage report'),
  watch: z.boolean().default(false).describe('Watch for changes and rerun'),
})

export const test: CommandDefinition<typeof TestArgs> = {
  name: 'test',
  description: 'Run E2E tests',
  help: `
Runs semantic E2E tests defined in your DSL flow declarations.

Tests run against a live server instance. The server is started automatically
if not already running.

Use --coverage to generate a UX coverage report showing which surfaces
and actions are covered by tests.
`,
  examples: [
    'dazzle test',
    'dazzle test --flow create_task',
    'dazzle test --coverage',
    'dazzle test --no-headless',
  ],
  args: TestArgs,

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

    // Build test command for Python
    const cliArgs = ['test', 'run']
    if (args.flow) cliArgs.push('--flow', args.flow)
    if (!args.headless) cliArgs.push('--no-headless')
    if (args.coverage) cliArgs.push('--coverage')
    if (args.watch) cliArgs.push('--watch')

    // Run tests interactively
    const python = 'python3'

    console.log('Running E2E tests...')
    if (args.flow) {
      console.log(`  Flow: ${args.flow}`)
    }
    console.log()

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
        'TEST_FAILED',
        `Tests failed with exit code ${exitCode}`,
        'Check the test output above for details. Run with --no-headless to debug interactively.'
      )
    }

    return success(
      {
        passed: true,
        flow: args.flow || 'all',
        duration_ms,
      },
      { duration_ms }
    )
  },
}
