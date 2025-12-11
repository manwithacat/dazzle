/**
 * test command - Run tests
 *
 * Replaces: dazzle test run, dazzle dnr test
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints, progress } from '../lib/output'

const TestArgs = z.object({
  flow: z.string().optional().describe('Specific flow to run'),
  headless: z.boolean().default(true).describe('Run in headless mode'),
  coverage: z.boolean().default(false).describe('Generate UX coverage report'),
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

    progress({ type: 'progress', step: 1, total: 2, message: 'Running tests...' }, ctx.output)

    // Call Python bridge
    const result = await ctx.python<{
      passed: number
      failed: number
      skipped: number
      total: number
      duration_ms?: number
      coverage?: unknown
      error?: string
      hint?: string
    }>(
      'dazzle.core.cli_bridge',
      'run_tests_json',
      {
        path: ctx.cwd,
        flow: args.flow,
        headless: args.headless,
        coverage: args.coverage,
      }
    )

    if (!result.success) {
      return error(
        'TEST_FAILED',
        result.error || 'Tests failed',
        'Check that the project is valid and test dependencies are installed'
      )
    }

    progress({ type: 'progress', step: 2, total: 2, message: 'Done' }, ctx.output)

    const duration_ms = Date.now() - startTime
    const data = result.data!

    // Check if there was an error in the test run itself
    if (data.error) {
      return error(
        'TEST_FAILED',
        data.error,
        data.hint || 'Check test configuration'
      )
    }

    // Check if any tests failed
    if (data.failed > 0) {
      return {
        success: false,
        error: {
          code: 'TESTS_FAILED',
          message: `${data.failed} of ${data.total} tests failed`,
          __agent_hint: 'Run with --no-headless to debug interactively',
        },
        data: {
          passed: data.passed,
          failed: data.failed,
          skipped: data.skipped,
          total: data.total,
          flow: args.flow || 'all',
        },
        meta: { duration_ms },
      }
    }

    return success(
      {
        passed: data.passed,
        failed: data.failed,
        skipped: data.skipped,
        total: data.total,
        flow: args.flow || 'all',
        coverage: data.coverage,
      },
      { duration_ms }
    )
  },
}
