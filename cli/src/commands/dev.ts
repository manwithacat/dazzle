/**
 * dev command - Start development server
 *
 * Replaces: dazzle dnr serve
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'

const DevArgs = z.object({
  port: z.number().default(8000).describe('API server port'),
  'ui-port': z.number().default(3000).describe('UI server port'),
  host: z.string().default('localhost').describe('Host to bind to'),
  watch: z.boolean().default(true).describe('Watch for file changes'),
  docker: z.boolean().default(false).describe('Run in Docker container'),
  'test-mode': z.boolean().default(false).describe('Enable test endpoints'),
  graphql: z.boolean().default(false).describe('Enable GraphQL endpoint'),
})

export const dev: CommandDefinition<typeof DevArgs> = {
  name: 'dev',
  description: 'Start development server',
  help: `
Starts the Dazzle Native Runtime (DNR) development server with hot reload.

The server runs both the API backend and UI frontend:
- API: http://localhost:8000 (or --port)
- UI:  http://localhost:3000 (or --ui-port)
- Docs: http://localhost:8000/docs

With --docker, runs in a containerized environment.
With --test-mode, enables /__test__/* endpoints for E2E testing.
With --graphql, enables /graphql endpoint.
`,
  examples: [
    'dazzle dev',
    'dazzle dev --port 9000',
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

    if (args.port !== 8000) cliArgs.push('--port', String(args.port))
    if (args['ui-port'] !== 3000) cliArgs.push('--ui-port', String(args['ui-port']))
    if (args.host !== 'localhost') cliArgs.push('--host', args.host)
    if (!args.watch) cliArgs.push('--no-watch')
    if (args.docker) cliArgs.push('--docker')
    if (args['test-mode']) cliArgs.push('--test-mode')
    if (args.graphql) cliArgs.push('--graphql')

    // For the dev server, we need to run interactively (not capture output)
    // This hands control to the Python process
    const python = 'python3'

    console.log(`Starting development server...`)
    console.log(`  API: http://${args.host}:${args.port}`)
    console.log(`  UI:  http://${args.host}:${args['ui-port']}`)
    console.log(`  Docs: http://${args.host}:${args.port}/docs`)
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
