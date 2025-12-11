/**
 * dev command - Start development server
 *
 * Replaces: dazzle dnr serve
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'
import { getPythonPath } from '../lib/python'

const DevArgs = z.object({
  port: z.number().default(3000).describe('UI server port'),
  'api-port': z.number().default(8000).describe('API server port'),
  host: z.string().default('localhost').describe('Host to bind to'),
  watch: z.boolean().default(true).describe('Watch for file changes (local mode only)'),
  local: z.boolean().default(true).describe('Run locally without Docker (default)'),
  docker: z.boolean().default(false).describe('Run in Docker container (requires Docker)'),
  'test-mode': z.boolean().default(false).describe('Enable test endpoints'),
  graphql: z.boolean().default(false).describe('Enable GraphQL endpoint'),
})

export const dev: CommandDefinition<typeof DevArgs> = {
  name: 'dev',
  description: 'Start development server',
  help: `
Starts the Dazzle Native Runtime (DNR) development server with hot reload.

The server runs both the API backend and UI frontend:
- UI:  http://localhost:3000 (or --port)
- API: http://localhost:8000 (or --api-port)
- Docs: http://localhost:8000/docs

By default runs locally (--local). Use --docker for containerized mode.
With --test-mode, enables /__test__/* endpoints for E2E testing.
With --graphql, enables /graphql endpoint.
`,
  examples: [
    'dazzle dev',
    'dazzle dev --port 4000',
    'dazzle dev --api-port 9000',
    'dazzle dev --docker',
    'dazzle dev --test-mode --graphql',
  ],
  args: DevArgs,

  async run(args, ctx) {
    // Check if we have a project
    if (!ctx.configPath) {
      return error(
        ErrorHints.NO_PROJECT.code,
        'No dazzle.toml found',
        ErrorHints.NO_PROJECT.hint
      )
    }

    // Build command arguments for Python CLI
    const cliArgs = ['dnr', 'serve']

    if (args.port !== 3000) cliArgs.push('--port', String(args.port))
    if (args['api-port'] !== 8000) cliArgs.push('--api-port', String(args['api-port']))
    if (args.host !== 'localhost') cliArgs.push('--host', args.host)

    // Handle local vs docker mode
    // --docker overrides --local (they're mutually exclusive)
    // Note: --watch forces local mode in Python, so don't pass it with --docker
    if (args.docker) {
      // Don't pass --local or --watch, let Python use Docker
      // Docker mode has its own hot reload via volume mounts
    } else {
      // Local mode (default)
      cliArgs.push('--local')
      // Python dnr serve defaults watch=False, so pass --watch if enabled
      if (args.watch) cliArgs.push('--watch')
    }
    if (args['test-mode']) cliArgs.push('--test-mode')
    if (args.graphql) cliArgs.push('--graphql')

    // For the dev server, we need to run interactively (not capture output)
    // This hands control to the Python process
    // Use getPythonPath() to respect DAZZLE_PYTHON env var (set by Homebrew)
    const python = await getPythonPath()

    console.log(`Starting development server...`)
    console.log(`  UI:  http://${args.host}:${args.port}`)
    console.log(`  API: http://${args.host}:${args['api-port']}`)
    console.log(`  Docs: http://${args.host}:${args['api-port']}/docs`)
    console.log()

    const proc = Bun.spawn([python, '-m', 'dazzle', ...cliArgs], {
      cwd: ctx.cwd,
      stdio: ['inherit', 'inherit', 'inherit'],
      env: {
        ...process.env,
        // Pass through color settings
        FORCE_COLOR: ctx.output.color ? '1' : '0',
      },
    })

    // Wait for process to exit
    const exitCode = await proc.exited

    if (exitCode !== 0) {
      return error(
        'SERVER_ERROR',
        `Server exited with code ${exitCode}`,
        'Check the server logs above for details'
      )
    }

    return success({ message: 'Server stopped' })
  },
}
