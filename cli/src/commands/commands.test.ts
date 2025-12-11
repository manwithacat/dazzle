/**
 * CLI Command Unit Tests
 *
 * These tests verify that all CLI commands follow the bridging methodology:
 * - Commands should call ctx.python() instead of spawning subprocesses
 * - Commands should use the dazzle.core.cli_bridge module
 *
 * Exception: `dev` command uses subprocess intentionally for interactive mode
 */

import { describe, test, expect, mock, beforeEach } from 'bun:test'
import type { CommandContext, PythonResult } from '../types/commands'
import type { OutputOptions } from '../types/output'

// Import all commands
import { check } from './check'
import { show } from './show'
import { build } from './build'
import { eject } from './eject'
import { newCommand } from './new'
import { test as testCommand } from './test'
import { db } from './db'
import { version } from './version'
import { dev } from './dev'

// Test utilities
/**
 * Default mock responses for bridge functions
 * These match the expected return types from cli_bridge.py
 */
const mockResponses: Record<string, unknown> = {
  validate_project_json: {
    valid: true,
    modules: [{ name: 'test', path: 'dsl/app.dsl', entities: 1, surfaces: 1 }],
    entities: ['Task'],
    surfaces: ['task_list'],
    errors: [],
    warnings: [],
  },
  get_project_info_json: {
    name: 'test',
    version: '1.0.0',
    entities: [{ name: 'Task', fields: [], relationships: [] }],
    surfaces: [{ name: 'task_list', entity: 'Task', mode: 'list', sections: [] }],
    workspaces: ['main'],
    services: [],
  },
  init_project_json: {
    name: 'test-project',
    path: './test-project',
  },
  build_project_json: {
    output_path: './dist',
    files: ['main.py', 'Dockerfile'],
    docker: true,
  },
  eject_project_json: {
    output_path: './ejected',
    backend_files: ['main.py'],
    frontend_files: ['App.tsx'],
    total_files: 2,
  },
  run_tests_json: {
    passed: 1,
    failed: 0,
    skipped: 0,
    total: 1,
  },
  db_migrate_json: { success: true, tables_created: 1 },
  db_seed_json: { success: true, records_created: 5 },
  db_reset_json: { success: true },
}

function createMockContext(overrides: Partial<CommandContext> = {}): CommandContext {
  const mockPython = mock(async <T>(_module: string, fn: string, _args: Record<string, unknown>): Promise<PythonResult<T>> => {
    const data = mockResponses[fn] ?? {}
    return { success: true, data: data as T }
  })

  return {
    cwd: '/test/project',
    output: { color: false, format: 'json' } as OutputOptions,
    python: mockPython,
    configPath: '/test/project/dazzle.toml',
    config: { name: 'test', version: '1.0.0' },
    ...overrides,
  }
}

function getCommandSource(command: { run: Function }): string {
  return command.run.toString()
}

describe('CLI Commands - Import Tests', () => {
  test('check command can be imported', () => {
    expect(check).toBeDefined()
    expect(check.name).toBe('check')
    expect(typeof check.run).toBe('function')
  })

  test('show command can be imported', () => {
    expect(show).toBeDefined()
    expect(show.name).toBe('show')
    expect(typeof show.run).toBe('function')
  })

  test('build command can be imported', () => {
    expect(build).toBeDefined()
    expect(build.name).toBe('build')
    expect(typeof build.run).toBe('function')
  })

  test('eject command can be imported', () => {
    expect(eject).toBeDefined()
    expect(eject.name).toBe('eject')
    expect(typeof eject.run).toBe('function')
  })

  test('new command can be imported', () => {
    expect(newCommand).toBeDefined()
    expect(newCommand.name).toBe('new')
    expect(typeof newCommand.run).toBe('function')
  })

  test('test command can be imported', () => {
    expect(testCommand).toBeDefined()
    expect(testCommand.name).toBe('test')
    expect(typeof testCommand.run).toBe('function')
  })

  test('db command can be imported', () => {
    expect(db).toBeDefined()
    expect(db.name).toBe('db')
    expect(typeof db.run).toBe('function')
  })

  test('version command can be imported', () => {
    expect(version).toBeDefined()
    expect(version.name).toBe('version')
    expect(typeof version.run).toBe('function')
  })

  test('dev command can be imported', () => {
    expect(dev).toBeDefined()
    expect(dev.name).toBe('dev')
    expect(typeof dev.run).toBe('function')
  })
})

describe('CLI Commands - Bridge Methodology Tests', () => {
  /**
   * These tests verify that commands use ctx.python() for Python interop
   * instead of spawning subprocesses directly.
   *
   * The dev command is an exception - it needs interactive subprocess
   * for live server with stdio inheritance.
   */

  test('check command uses ctx.python bridge', async () => {
    const ctx = createMockContext()
    const args = { path: undefined, strict: false, fix: false }

    await check.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      expect.any(Object)
    )
  })

  test('show command uses ctx.python bridge', async () => {
    const ctx = createMockContext()
    const args = { what: 'all' as const, name: undefined, verbose: false }

    await show.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'get_project_info_json',
      expect.any(Object)
    )
  })

  test('build command uses ctx.python bridge', async () => {
    const ctx = createMockContext()
    // Mock successful validation first
    const mockPython = mock(async <T>(_module: string, fn: string, _args: Record<string, unknown>): Promise<PythonResult<T>> => {
      if (fn === 'validate_project_json') {
        return { success: true, data: { valid: true } as T }
      }
      return { success: true, data: {} as T }
    })
    ctx.python = mockPython

    const args = { output: './dist', docker: true, graphql: false }

    await build.run(args, ctx)

    // Should call both validate_project_json and build_project_json
    expect(mockPython).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      expect.any(Object)
    )
    expect(mockPython).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'build_project_json',
      expect.any(Object)
    )
  })

  test('eject command uses ctx.python bridge', async () => {
    const ctx = createMockContext()
    const args = { output: './ejected', backend: 'fastapi' as const, frontend: 'react' as const, 'dry-run': false }

    await eject.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'eject_project_json',
      expect.any(Object)
    )
  })

  test('new command uses ctx.python bridge', async () => {
    const ctx = createMockContext({ configPath: undefined }) // No existing project
    const args = { name: 'test-project', template: 'simple_task', path: undefined }

    await newCommand.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'init_project_json',
      expect.any(Object)
    )
  })

  test('test command uses ctx.python bridge', async () => {
    const ctx = createMockContext()
    const args = { flow: undefined, headless: true, coverage: false }

    await testCommand.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'run_tests_json',
      expect.any(Object)
    )
  })

  test('db command uses ctx.python bridge for migrate', async () => {
    const ctx = createMockContext()
    const args = { action: 'migrate' as const, 'dry-run': false }

    await db.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'db_migrate_json',
      expect.any(Object)
    )
  })

  test('db command uses ctx.python bridge for seed', async () => {
    const ctx = createMockContext()
    const args = { action: 'seed' as const, 'dry-run': false }

    await db.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'db_seed_json',
      expect.any(Object)
    )
  })

  test('db command uses ctx.python bridge for reset', async () => {
    const ctx = createMockContext()
    const args = { action: 'reset' as const, 'dry-run': false }

    await db.run(args, ctx)

    expect(ctx.python).toHaveBeenCalledWith(
      'dazzle.core.cli_bridge',
      'db_reset_json',
      expect.any(Object)
    )
  })

  test('version command does not require ctx.python for basic info', async () => {
    const ctx = createMockContext()
    const args = { full: false }

    const result = await version.run(args, ctx)

    // version --full=false should NOT call python
    expect(ctx.python).not.toHaveBeenCalled()
    expect(result.success).toBe(true)
  })
})

describe('CLI Commands - No Subprocess Pattern Tests', () => {
  /**
   * These tests verify that commands do NOT use Bun.spawn/subprocess
   * for Python interop. Instead they should use ctx.python().
   *
   * We analyze the source code of each command's run function.
   */

  const commandsUsingBridge = [
    { name: 'check', command: check },
    { name: 'show', command: show },
    { name: 'build', command: build },
    { name: 'eject', command: eject },
    { name: 'new', command: newCommand },
    { name: 'test', command: testCommand },
    { name: 'db', command: db },
  ]

  for (const { name, command } of commandsUsingBridge) {
    test(`${name} command does NOT spawn python subprocess directly`, () => {
      const source = getCommandSource(command)

      // Should not contain direct subprocess spawning for Python
      expect(source).not.toContain("Bun.spawn([python")
      expect(source).not.toContain("Bun.spawn(['python")
      expect(source).not.toContain('Bun.spawn(["python')
      expect(source).not.toContain("-m', 'dazzle")
      expect(source).not.toContain('-m", "dazzle')

      // Should contain ctx.python call instead
      expect(source).toContain('ctx.python')
    })
  }

  test('dev command DOES use subprocess (intentionally for interactive mode)', () => {
    const source = getCommandSource(dev)

    // dev command should use Bun.spawn because it needs interactive stdio
    expect(source).toContain('Bun.spawn')
    expect(source).toContain('stdio')

    // But should NOT use ctx.python
    expect(source).not.toContain('ctx.python')
  })
})

describe('CLI Commands - Bridge Function Names', () => {
  /**
   * Verify that commands call the correct bridge functions.
   * This catches typos and ensures consistency.
   */

  const expectedBridgeFunctions: Record<string, string[]> = {
    check: ['validate_project_json'],
    show: ['get_project_info_json'],
    build: ['validate_project_json', 'build_project_json'],
    eject: ['eject_project_json'],
    new: ['init_project_json'],
    test: ['run_tests_json'],
    db: ['db_migrate_json', 'db_seed_json', 'db_reset_json'],
  }

  for (const [commandName, functions] of Object.entries(expectedBridgeFunctions)) {
    test(`${commandName} command source references correct bridge functions`, () => {
      const commands: Record<string, { run: Function }> = {
        check, show, build, eject, new: newCommand, test: testCommand, db
      }
      const source = getCommandSource(commands[commandName])

      for (const fn of functions) {
        expect(source).toContain(fn)
      }
    })
  }
})

describe('CLI Commands - Error Handling', () => {
  /**
   * Verify commands handle missing project gracefully
   */

  const projectRequiredCommands = [
    { name: 'check', command: check, args: { path: undefined, strict: false, fix: false } },
    { name: 'show', command: show, args: { what: 'all' as const, name: undefined, verbose: false } },
    { name: 'build', command: build, args: { output: './dist', docker: true, graphql: false } },
    { name: 'eject', command: eject, args: { output: './ejected', backend: 'fastapi' as const, frontend: 'react' as const, 'dry-run': false } },
    { name: 'test', command: testCommand, args: { flow: undefined, headless: true, coverage: false } },
    { name: 'db', command: db, args: { action: 'migrate' as const, 'dry-run': false } },
  ]

  for (const { name, command, args } of projectRequiredCommands) {
    test(`${name} command returns error when no project found`, async () => {
      const ctx = createMockContext({ configPath: undefined })

      const result = await command.run(args as any, ctx)

      expect(result.success).toBe(false)
      expect(result.error).toBeDefined()
      expect(result.error?.code).toBe('NO_PROJECT')
    })
  }
})
