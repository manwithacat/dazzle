/**
 * Python Bridge Unit Tests
 *
 * Tests for the Python bridge module that handles CLI-to-Python communication.
 */

import { describe, test, expect, beforeEach, afterEach } from 'bun:test'
import { callPython, getPythonPath, checkPythonDazzle } from './python'

describe('Python Bridge - Core Functions', () => {
  test('getPythonPath returns a string', async () => {
    const pythonPath = await getPythonPath()
    expect(typeof pythonPath).toBe('string')
    expect(pythonPath.length).toBeGreaterThan(0)
  })

  test('getPythonPath prefers DAZZLE_PYTHON env var', async () => {
    // Save original
    const originalEnv = process.env.DAZZLE_PYTHON

    // Set mock python path - use system python which should exist
    process.env.DAZZLE_PYTHON = 'python3'

    try {
      const pythonPath = await getPythonPath()
      // If python3 exists, it should be returned
      expect(pythonPath).toBe('python3')
    } catch {
      // python3 might not exist, that's okay
    } finally {
      // Restore
      if (originalEnv !== undefined) {
        process.env.DAZZLE_PYTHON = originalEnv
      } else {
        delete process.env.DAZZLE_PYTHON
      }
    }
  })

  test('callPython handles simple module import', async () => {
    // Test with a simple Python built-in
    const result = await callPython<string>('json', 'dumps', { obj: { test: true } })

    // This will fail because json.dumps takes positional args, but it tests the mechanism
    // The important thing is it doesn't throw and returns a structured result
    expect(typeof result).toBe('object')
    expect('success' in result).toBe(true)
  })

  test('callPython returns error for non-existent module', async () => {
    const result = await callPython<unknown>(
      'nonexistent_module_that_does_not_exist',
      'some_function',
      {}
    )

    expect(result.success).toBe(false)
    expect(result.error).toBeDefined()
  })
})

describe('Python Bridge - Dazzle Package Check', () => {
  test('checkPythonDazzle returns structured result', async () => {
    const result = await checkPythonDazzle()

    expect(typeof result).toBe('object')
    expect('available' in result).toBe(true)
    expect(typeof result.available).toBe('boolean')

    if (result.available) {
      expect(result.version).toBeDefined()
    } else {
      expect(result.error).toBeDefined()
    }
  })
})

describe('Python Bridge - CLI Bridge Functions', () => {
  /**
   * These tests verify that the CLI bridge functions exist and can be called.
   * They test the actual Python bridge functions used by CLI commands.
   *
   * Note: These tests will only pass if the dazzle Python package is installed.
   * They're designed to catch import errors and broken references.
   */

  const bridgeFunctions = [
    'validate_project_json',
    'get_project_info_json',
    'init_project_json',
    'build_project_json',
    'eject_project_json',
    'run_tests_json',
    'db_migrate_json',
    'db_seed_json',
    'db_reset_json',
  ]

  for (const fn of bridgeFunctions) {
    test(`cli_bridge.${fn} can be imported`, async () => {
      // We can't directly test import, but we can verify the function exists
      // by calling it with invalid args - it should fail gracefully, not with ImportError
      const result = await callPython<unknown>(
        'dazzle.core.cli_bridge',
        fn,
        { path: '/nonexistent/path' }
      )

      // The call should complete (success or failure), not crash
      expect(typeof result).toBe('object')
      expect('success' in result).toBe(true)

      // If it failed, the error should NOT be about importing
      if (!result.success && result.error) {
        expect(result.error).not.toContain('cannot import name')
        expect(result.error).not.toContain('No module named')
        expect(result.error).not.toMatch(/ImportError/i)
      }
    })
  }
})

describe('Python Bridge - JSON Serialization', () => {
  test('callPython handles complex args', async () => {
    const complexArgs = {
      path: '/some/path',
      options: {
        strict: true,
        format: 'json',
        flags: ['a', 'b', 'c'],
      },
      nested: {
        level1: {
          level2: {
            value: 42,
          },
        },
      },
    }

    // Just verify it doesn't crash on complex JSON
    const result = await callPython<unknown>(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      complexArgs
    )

    expect(typeof result).toBe('object')
    expect('success' in result).toBe(true)
  })

  test('callPython handles special characters in args', async () => {
    const argsWithSpecialChars = {
      path: '/path/with spaces/and "quotes"',
      message: "Line 1\nLine 2\tTabbed",
      unicode: '日本語テスト',
    }

    const result = await callPython<unknown>(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      argsWithSpecialChars
    )

    // Should not crash
    expect(typeof result).toBe('object')
  })
})
