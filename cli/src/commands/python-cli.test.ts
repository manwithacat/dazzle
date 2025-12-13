/**
 * Python CLI Delegation Tests
 *
 * These tests verify that all Bun CLI commands that delegate to the Python CLI
 * use the correct command structure. The Python CLI has two patterns:
 *
 * 1. Top-level commands (hyphenated): mcp-setup, mcp-check
 * 2. Subcommand groups: dnr serve, dnr build, vocab list, etc.
 *
 * This test file catches mismatches between the Bun CLI's expectations and
 * the Python CLI's actual command structure.
 */

import { describe, test, expect } from 'bun:test'
import { join, dirname } from 'path'

// Get the directory containing this test file for source file paths
const TEST_DIR = dirname(import.meta.path)

// Get Python path, expanding ~ and $HOME if needed
function getPythonPath(): string {
  let python = process.env.DAZZLE_PYTHON || 'python3'
  // Expand $HOME if present
  if (python.includes('$HOME')) {
    python = python.replace('$HOME', process.env.HOME || '')
  }
  // Expand ~ at start
  if (python.startsWith('~')) {
    python = python.replace('~', process.env.HOME || '')
  }
  return python
}

const PYTHON = getPythonPath()

/**
 * Helper to run a Python CLI command and capture output
 */
async function runPythonCLI(args: string[]): Promise<{
  exitCode: number
  stdout: string
  stderr: string
}> {
  const proc = Bun.spawn([PYTHON, '-m', 'dazzle', ...args], {
    stdout: 'pipe',
    stderr: 'pipe',
  })

  const [exitCode, stdout, stderr] = await Promise.all([
    proc.exited,
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
  ])

  return { exitCode, stdout, stderr }
}

describe('Python CLI - Top Level Commands', () => {
  /**
   * These commands are top-level (not subcommands of a group).
   * They use underscores in Python but hyphens on the CLI.
   */

  const topLevelCommands = [
    'init',
    'validate',
    'lint',
    'inspect',
    'layout-plan',
    'analyze-spec',
    'example',
    'mcp',
    'mcp-setup',
    'mcp-check',
  ]

  for (const cmd of topLevelCommands) {
    test(`"${cmd}" is a valid top-level command`, async () => {
      const { exitCode, stderr } = await runPythonCLI([cmd, '--help'])

      // Should succeed (exit 0) when asking for help
      expect(exitCode).toBe(0)

      // Should NOT contain "No such command" or "unexpected extra argument"
      expect(stderr).not.toContain('No such command')
      expect(stderr).not.toContain('unexpected extra argument')
    })
  }
})

describe('Python CLI - Subcommand Groups', () => {
  /**
   * These are Typer sub-apps (subcommand groups).
   * The Bun CLI calls them as: python -m dazzle <group> <subcommand>
   */

  const subcommandGroups = [
    { group: 'dnr', subcommands: ['serve', 'build', 'build-ui', 'build-api', 'info', 'migrate'] },
    { group: 'vocab', subcommands: ['init', 'list', 'show', 'expand'] },
    { group: 'stubs', subcommands: ['generate', 'sync', 'list'] },
    { group: 'test', subcommands: ['generate', 'run'] },
    { group: 'e2e', subcommands: ['run', 'run-all', 'clean'] },
    { group: 'eject', subcommands: ['run', 'adapters'] },
  ]

  for (const { group, subcommands } of subcommandGroups) {
    test(`"${group}" is a valid subcommand group`, async () => {
      const { exitCode, stderr } = await runPythonCLI([group, '--help'])

      expect(exitCode).toBe(0)
      expect(stderr).not.toContain('No such command')
    })

    for (const sub of subcommands) {
      test(`"${group} ${sub}" is a valid subcommand`, async () => {
        const { exitCode, stderr } = await runPythonCLI([group, sub, '--help'])

        expect(exitCode).toBe(0)
        expect(stderr).not.toContain('No such command')
        expect(stderr).not.toContain('unexpected extra argument')
      })
    }
  }
})

describe('Python CLI - Invalid Command Patterns', () => {
  /**
   * These tests verify that INVALID patterns fail.
   * This catches the bug where we call `mcp setup` instead of `mcp-setup`.
   */

  const invalidPatterns = [
    { args: ['mcp', 'setup'], description: 'mcp setup (should be mcp-setup)' },
    { args: ['mcp', 'check'], description: 'mcp check (should be mcp-check)' },
    { args: ['layout', 'plan'], description: 'layout plan (should be layout-plan)' },
    { args: ['analyze', 'spec'], description: 'analyze spec (should be analyze-spec)' },
  ]

  for (const { args, description } of invalidPatterns) {
    test(`"${description}" should fail`, async () => {
      const { exitCode, stderr } = await runPythonCLI(args)

      // Should NOT succeed
      expect(exitCode).not.toBe(0)

      // Should contain error message about unexpected argument
      expect(stderr).toMatch(/unexpected extra argument|No such command/i)
    })
  }
})

describe('Bun CLI Source - Command Argument Verification', () => {
  /**
   * These tests read the Bun CLI source to verify correct patterns.
   */

  test('dev.ts uses correct dnr serve subcommand', async () => {
    const source = await Bun.file(join(TEST_DIR, 'dev.ts')).text()

    // Should use ['dnr', 'serve'] as separate args
    expect(source).toContain("'dnr', 'serve'")

    // The full pattern should be: Bun.spawn([python, '-m', 'dazzle', ...cliArgs])
    // where cliArgs starts with ['dnr', 'serve', ...]
  })

  test('mcp.ts uses correct hyphenated commands', async () => {
    const source = await Bun.file(join(TEST_DIR, 'mcp.ts')).text()

    // mcp-setup should be a single string, not ['mcp', 'setup']
    expect(source).toContain("'mcp-setup'")
    expect(source).toContain("'mcp-check'")

    // Should NOT have split pattern
    expect(source).not.toMatch(/cliArgs.*=.*\['mcp',\s*'setup'\]/)
    expect(source).not.toMatch(/cliArgs.*=.*\['mcp',\s*'check'\]/)
  })
})

describe('Python CLI - Module Paths', () => {
  /**
   * Some commands call Python modules directly (e.g., python -m dazzle.mcp)
   * rather than through the CLI (python -m dazzle mcp).
   */

  const directModules = [
    { module: 'dazzle.mcp', description: 'MCP server module' },
    { module: 'dazzle.core.cli_bridge', description: 'CLI bridge module' },
  ]

  for (const { module, description } of directModules) {
    test(`${description} (${module}) can be imported`, async () => {
      const proc = Bun.spawn([PYTHON, '-c', `import ${module}; print('OK')`], {
        stdout: 'pipe',
        stderr: 'pipe',
      })

      const exitCode = await proc.exited
      const stdout = await new Response(proc.stdout).text()

      expect(exitCode).toBe(0)
      expect(stdout.trim()).toBe('OK')
    })
  }
})

describe('Python CLI - Help Text Consistency', () => {
  /**
   * Verify that the commands exposed by Python CLI match what Bun CLI expects.
   */

  test('Python CLI main help lists expected commands', async () => {
    const { exitCode, stdout } = await runPythonCLI(['--help'])

    expect(exitCode).toBe(0)

    // Check for top-level commands the Bun CLI depends on
    expect(stdout).toContain('mcp-setup')
    expect(stdout).toContain('mcp-check')
    expect(stdout).toContain('validate')
    expect(stdout).toContain('lint')
    expect(stdout).toContain('init')

    // Check for subcommand groups
    expect(stdout).toContain('dnr')
    expect(stdout).toContain('vocab')
    expect(stdout).toContain('eject')
  })

  test('dnr subcommand help lists serve command', async () => {
    const { exitCode, stdout } = await runPythonCLI(['dnr', '--help'])

    expect(exitCode).toBe(0)
    expect(stdout).toContain('serve')
    expect(stdout).toContain('build')
  })
})
