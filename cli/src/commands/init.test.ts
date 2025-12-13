/**
 * Project Initialization Tests
 *
 * Tests for `dazzle new` command and related project setup.
 */

import { describe, test, expect, beforeAll, afterAll } from 'bun:test'
import { existsSync, rmSync, readFileSync } from 'fs'
import { join } from 'path'

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
const TEST_DIR = '/tmp/dazzle-init-test'

describe('Project Initialization - MCP Config', () => {
  beforeAll(() => {
    // Clean up any previous test
    if (existsSync(TEST_DIR)) {
      rmSync(TEST_DIR, { recursive: true })
    }
  })

  afterAll(() => {
    // Clean up
    if (existsSync(TEST_DIR)) {
      rmSync(TEST_DIR, { recursive: true })
    }
  })

  test('create_mcp_config generates correct module path', async () => {
    // Create a test project using Python directly
    const proc = Bun.spawn([
      PYTHON, '-c', `
import json
import sys
from pathlib import Path

# Create test directory
test_dir = Path('${TEST_DIR}')
test_dir.mkdir(parents=True, exist_ok=True)

# Import and run create_mcp_config
from dazzle.core.init_impl.project import create_mcp_config
create_mcp_config(test_dir)

# Read and print the config
mcp_path = test_dir / '.mcp.json'
print(mcp_path.read_text())
`
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const stdout = await new Response(proc.stdout).text()
    const exitCode = await proc.exited

    expect(exitCode).toBe(0)

    // Parse the generated config
    const config = JSON.parse(stdout.trim())

    // Verify correct structure
    expect(config.mcpServers).toBeDefined()
    expect(config.mcpServers.dazzle).toBeDefined()

    // Verify correct module path (dazzle.mcp, NOT dazzle.mcp.server)
    const args = config.mcpServers.dazzle.args
    expect(args).toContain('-m')
    expect(args).toContain('dazzle.mcp')
    expect(args).not.toContain('dazzle.mcp.server')

    // Verify command is a real Python path (not just "python")
    const command = config.mcpServers.dazzle.command
    expect(command).not.toBe('python')
    expect(command).toContain('python')  // Should be a path containing "python"
  })

  test('MCP config module can be imported', async () => {
    // Verify the module path dazzle.mcp is importable
    const proc = Bun.spawn([
      PYTHON, '-c', 'import dazzle.mcp; print("OK")'
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const stdout = await new Response(proc.stdout).text()
    const exitCode = await proc.exited

    expect(exitCode).toBe(0)
    expect(stdout.trim()).toBe('OK')
  })

  test('MCP config module has __main__ or run_server', async () => {
    // Verify dazzle.mcp can be run as a module
    const proc = Bun.spawn([
      PYTHON, '-c', `
import dazzle.mcp
# Check it has the expected entry point
if hasattr(dazzle.mcp, 'run_server'):
    print("OK: has run_server")
elif hasattr(dazzle.mcp, 'main'):
    print("OK: has main")
else:
    # Try importing __main__
    try:
        import dazzle.mcp.__main__
        print("OK: has __main__")
    except ImportError:
        print("FAIL: no entry point")
        exit(1)
`
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const stdout = await new Response(proc.stdout).text()
    const exitCode = await proc.exited

    expect(exitCode).toBe(0)
    expect(stdout.trim()).toContain('OK')
  })
})

describe('Project Initialization - dazzle new', () => {
  const NEW_PROJECT_DIR = '/tmp/dazzle-new-test-project'

  beforeAll(() => {
    if (existsSync(NEW_PROJECT_DIR)) {
      rmSync(NEW_PROJECT_DIR, { recursive: true })
    }
  })

  afterAll(() => {
    if (existsSync(NEW_PROJECT_DIR)) {
      rmSync(NEW_PROJECT_DIR, { recursive: true })
    }
  })

  test('dazzle new creates valid .mcp.json', async () => {
    // Run dazzle new via Python CLI
    const proc = Bun.spawn([
      PYTHON, '-m', 'dazzle', 'init',
      '--name', 'test-project',
      NEW_PROJECT_DIR
    ], {
      stdout: 'pipe',
      stderr: 'pipe',
    })

    await proc.exited

    // Check .mcp.json exists
    const mcpPath = join(NEW_PROJECT_DIR, '.mcp.json')
    expect(existsSync(mcpPath)).toBe(true)

    // Verify config content
    const config = JSON.parse(readFileSync(mcpPath, 'utf-8'))

    expect(config.mcpServers?.dazzle?.args).toContain('dazzle.mcp')
    expect(config.mcpServers?.dazzle?.args).not.toContain('dazzle.mcp.server')
  })
})
