/**
 * MCP Commands Unit Tests
 *
 * These tests verify that MCP commands correctly construct Python CLI arguments.
 * The bug this catches: `mcp setup` (subcommand) vs `mcp-setup` (hyphenated command).
 */

import { describe, test, expect, mock, beforeEach, afterEach, spyOn } from 'bun:test'
import { join, dirname } from 'path'
import type { CommandContext } from '../types/commands'
import type { OutputOptions } from '../types/output'

// Get the directory containing this test file, then find mcp.ts
const TEST_DIR = dirname(import.meta.path)
const MCP_SOURCE_PATH = join(TEST_DIR, 'mcp.ts')

// Resolve Python path - DAZZLE_PYTHON might contain $HOME which needs expanding
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

describe('MCP Commands - Argument Construction', () => {
  /**
   * These tests verify the exact Python CLI arguments are correct.
   * The Python CLI uses hyphenated commands (mcp-setup, mcp-check),
   * NOT subcommands (mcp setup, mcp check).
   */

  test('mcp-setup source uses hyphenated command name', async () => {
    // Read the source directly using absolute path
    const source = await Bun.file(MCP_SOURCE_PATH).text()

    // Should contain 'mcp-setup' as a single argument
    expect(source).toContain("'mcp-setup'")

    // Should NOT contain patterns that would split into subcommand
    // Bad patterns: ['mcp', 'setup'] or 'mcp', 'setup'
    expect(source).not.toMatch(/\['mcp',\s*'setup'\]/)
    expect(source).not.toMatch(/cliArgs\s*=\s*\['mcp',\s*'setup'/)
  })

  test('mcp-check source uses hyphenated command name', async () => {
    const source = await Bun.file(MCP_SOURCE_PATH).text()

    // Should contain 'mcp-check' as a single argument
    expect(source).toContain("'mcp-check'")

    // Should NOT contain patterns that would split into subcommand
    expect(source).not.toMatch(/\['mcp',\s*'check'\]/)
    expect(source).not.toMatch(/'mcp',\s*'check'/)
  })

  test('mcp command uses dazzle.mcp module directly (not dazzle mcp subcommand)', async () => {
    const source = await Bun.file(MCP_SOURCE_PATH).text()

    // The mcp server command should use `python -m dazzle.mcp` (module)
    // NOT `python -m dazzle mcp` (cli subcommand)
    expect(source).toContain("'-m', 'dazzle.mcp'")
  })
})

describe('MCP Commands - Python CLI Command Validation', () => {
  /**
   * These tests validate that the Python CLI accepts the commands we're calling.
   * This is an integration test that catches mismatches between Bun CLI and Python CLI.
   */

  test('Python CLI has mcp-setup command (hyphenated)', async () => {
    // Run Python CLI help and verify mcp-setup exists
    const proc = Bun.spawn([
      getPythonPath(),
      '-m', 'dazzle', '--help'
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const stdout = await new Response(proc.stdout).text()
    await proc.exited

    // Verify mcp-setup is a command (Typer converts underscores to hyphens)
    expect(stdout).toContain('mcp-setup')
  })

  test('Python CLI has mcp-check command (hyphenated)', async () => {
    const proc = Bun.spawn([
      getPythonPath(),
      '-m', 'dazzle', '--help'
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const stdout = await new Response(proc.stdout).text()
    await proc.exited

    expect(stdout).toContain('mcp-check')
  })

  test('Python CLI mcp-setup command is callable', async () => {
    // Call the actual command with --help to verify it's wired correctly
    const proc = Bun.spawn([
      getPythonPath(),
      '-m', 'dazzle', 'mcp-setup', '--help'
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const exitCode = await proc.exited
    const stdout = await new Response(proc.stdout).text()

    // Should exit 0 (help is shown) and contain expected help text
    expect(exitCode).toBe(0)
    expect(stdout).toContain('Register')
  })

  test('Python CLI mcp-check command is callable', async () => {
    const proc = Bun.spawn([
      getPythonPath(),
      '-m', 'dazzle', 'mcp-check', '--help'
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const exitCode = await proc.exited
    const stdout = await new Response(proc.stdout).text()

    expect(exitCode).toBe(0)
    expect(stdout).toContain('Check')
  })

  test('Python CLI rejects "mcp setup" as invalid (catches the bug)', async () => {
    // This is the WRONG way to call it - should fail
    const proc = Bun.spawn([
      getPythonPath(),
      '-m', 'dazzle', 'mcp', 'setup'  // BAD: subcommand style
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const exitCode = await proc.exited
    const stderr = await new Response(proc.stderr).text()

    // Should fail with "unexpected extra argument"
    expect(exitCode).not.toBe(0)
    expect(stderr).toContain('unexpected extra argument')
  })

  test('Python CLI rejects "mcp check" as invalid (catches the bug)', async () => {
    const proc = Bun.spawn([
      getPythonPath(),
      '-m', 'dazzle', 'mcp', 'check'  // BAD: subcommand style
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const exitCode = await proc.exited
    const stderr = await new Response(proc.stderr).text()

    expect(exitCode).not.toBe(0)
    expect(stderr).toContain('unexpected extra argument')
  })
})

describe('MCP Commands - dazzle.mcp Module', () => {
  /**
   * The MCP server itself uses `python -m dazzle.mcp` (the module directly),
   * not `python -m dazzle mcp` (the CLI subcommand that wraps it).
   */

  test('dazzle.mcp module can be imported', async () => {
    const proc = Bun.spawn([
      getPythonPath(),
      '-c', 'import dazzle.mcp; print("OK")'
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const exitCode = await proc.exited
    const stdout = await new Response(proc.stdout).text()

    expect(exitCode).toBe(0)
    expect(stdout.trim()).toBe('OK')
  })
})

describe('MCP Commands - Spawn Arguments Snapshot', () => {
  /**
   * These tests capture the exact arguments that should be passed to Bun.spawn.
   * They serve as a contract test to prevent regressions.
   */

  test('mcp-setup constructs correct spawn arguments', async () => {
    // Expected pattern for mcp-setup (without --force)
    const expectedPattern = /Bun\.spawn\(\[python,\s*'-m',\s*'dazzle',\s*\.\.\.cliArgs\]/

    // Read source using Bun.file
    const source = await Bun.file(MCP_SOURCE_PATH).text()

    // The cliArgs should be ['mcp-setup'] not ['mcp', 'setup']
    expect(source).toMatch(/cliArgs\s*=\s*\['mcp-setup'\]/)
  })

  test('mcp-check constructs correct spawn arguments', async () => {
    const source = await Bun.file(MCP_SOURCE_PATH).text()

    // Should call with 'mcp-check' as single arg
    expect(source).toContain("'mcp-check'")
  })
})
