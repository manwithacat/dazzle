/**
 * mcp command - Run MCP server for Claude Code integration
 *
 * The MCP server provides context-aware tools for working with DAZZLE projects
 * from within Claude Code.
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'
import { getPythonPath } from '../lib/python'

const McpArgs = z.object({
  'working-dir': z.string().optional().describe('Project root directory (default: current directory)'),
})

export const mcp: CommandDefinition<typeof McpArgs> = {
  name: 'mcp',
  description: 'Run MCP server for Claude Code',
  help: `
Runs the DAZZLE MCP (Model Context Protocol) server.

This server provides tools for Claude Code to interact with DAZZLE projects:
- list_modules: List DSL modules in the project
- lookup_concept: Get documentation for DSL concepts
- find_examples: Find example code patterns
- validate_dsl: Validate DSL syntax
- analyze_patterns: Analyze project patterns

The server communicates via stdio and is typically started automatically
by Claude Code based on the MCP configuration in ~/.claude/mcp_servers.json.

To register the server with Claude Code, run:
  dazzle mcp-setup
`,
  examples: [
    'dazzle mcp',
    'dazzle mcp --working-dir /path/to/project',
  ],
  args: McpArgs,

  async run(args, ctx) {
    const python = await getPythonPath()
    const cliArgs = []

    if (args['working-dir']) {
      cliArgs.push('--working-dir', args['working-dir'])
    }

    // Run MCP server - it communicates via stdio
    const proc = Bun.spawn([python, '-m', 'dazzle.mcp', ...cliArgs], {
      cwd: ctx.cwd,
      stdio: ['inherit', 'inherit', 'inherit'],
      env: {
        ...process.env,
      },
    })

    // Wait for process to exit
    const exitCode = await proc.exited

    if (exitCode !== 0) {
      return error(
        'MCP_ERROR',
        `MCP server exited with code ${exitCode}`,
        'Check the server logs for details'
      )
    }

    return success({ message: 'MCP server stopped' })
  },
}

/**
 * mcp-setup command - Register MCP server with Claude Code
 */

const McpSetupArgs = z.object({
  force: z.boolean().default(false).describe('Overwrite existing MCP server config'),
})

export const mcpSetup: CommandDefinition<typeof McpSetupArgs> = {
  name: 'mcp-setup',
  description: 'Register MCP server with Claude Code',
  help: `
Registers the DAZZLE MCP server with Claude Code.

This command updates your Claude Code configuration (usually at
~/.claude/mcp_servers.json) to include the DAZZLE MCP server.

After registration, restart Claude Code to activate the tools.
`,
  examples: [
    'dazzle mcp-setup',
    'dazzle mcp-setup --force',
  ],
  args: McpSetupArgs,

  async run(args, ctx) {
    const python = await getPythonPath()
    const cliArgs = ['mcp', 'setup']

    if (args.force) {
      cliArgs.push('--force')
    }

    // Run mcp setup via Python CLI
    const proc = Bun.spawn([python, '-m', 'dazzle', ...cliArgs], {
      cwd: ctx.cwd,
      stdio: ['inherit', 'inherit', 'inherit'],
      env: {
        ...process.env,
      },
    })

    const exitCode = await proc.exited

    if (exitCode !== 0) {
      return error(
        'MCP_SETUP_ERROR',
        `MCP setup failed with code ${exitCode}`,
        'Check the output above for details'
      )
    }

    return success({ message: 'MCP server registered' })
  },
}

/**
 * mcp-check command - Check MCP server status
 */

const McpCheckArgs = z.object({})

export const mcpCheck: CommandDefinition<typeof McpCheckArgs> = {
  name: 'mcp-check',
  description: 'Check MCP server status',
  help: `
Checks if the DAZZLE MCP server is registered with Claude Code
and shows available tools.

Use this to verify your MCP configuration is correct.
`,
  examples: [
    'dazzle mcp-check',
  ],
  args: McpCheckArgs,

  async run(args, ctx) {
    const python = await getPythonPath()

    // Run mcp check via Python CLI
    const proc = Bun.spawn([python, '-m', 'dazzle', 'mcp', 'check'], {
      cwd: ctx.cwd,
      stdio: ['inherit', 'inherit', 'inherit'],
      env: {
        ...process.env,
      },
    })

    const exitCode = await proc.exited

    if (exitCode !== 0) {
      return error(
        'MCP_CHECK_ERROR',
        `MCP check failed`,
        'Run `dazzle mcp-setup` to register the MCP server'
      )
    }

    return success({ message: 'MCP server is configured correctly' })
  },
}
