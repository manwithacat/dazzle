/**
 * Python bridge for DAZZLE CLI
 *
 * Provides typed interface to call Python functions from TypeScript.
 * Uses Bun's subprocess API for fast execution.
 */

import type { PythonResult } from '../types/commands'

/**
 * Find Python executable
 *
 * Priority:
 * 1. DAZZLE_PYTHON env var (set by Homebrew wrapper)
 * 2. Common Python paths
 */
async function findPython(): Promise<string> {
  // First check DAZZLE_PYTHON (set by Homebrew wrapper)
  const dazzlePython = process.env.DAZZLE_PYTHON
  if (dazzlePython) {
    try {
      const proc = Bun.spawn([dazzlePython, '--version'], {
        stdout: 'pipe',
        stderr: 'pipe',
      })
      await proc.exited
      if (proc.exitCode === 0) {
        return dazzlePython
      }
    } catch {
      // Fall through to other candidates
    }
  }

  // Check common Python paths
  const candidates = ['python3', 'python', '/usr/bin/python3', '/usr/local/bin/python3']

  for (const candidate of candidates) {
    try {
      const proc = Bun.spawn([candidate, '--version'], {
        stdout: 'pipe',
        stderr: 'pipe',
      })
      await proc.exited
      if (proc.exitCode === 0) {
        return candidate
      }
    } catch {
      // Continue to next candidate
    }
  }

  throw new Error('Python 3 not found. Please install Python 3.11 or later.')
}

let cachedPython: string | null = null

async function getPython(): Promise<string> {
  if (!cachedPython) {
    cachedPython = await findPython()
  }
  return cachedPython
}

/**
 * Get Python executable path for external use (e.g., interactive commands)
 */
export async function getPythonPath(): Promise<string> {
  return getPython()
}

/**
 * Call a Python function and return the result
 *
 * @param module - Python module path (e.g., 'dazzle.core.dsl_parser')
 * @param fn - Function name to call
 * @param args - Arguments to pass as keyword arguments
 * @returns Result with typed data or error
 */
export async function callPython<T>(
  module: string,
  fn: string,
  args: Record<string, unknown> = {}
): Promise<PythonResult<T>> {
  const python = await getPython()

  // Build Python code to execute
  const argsJson = JSON.stringify(args)
  const code = `
import json
import sys

try:
    from ${module} import ${fn}
    result = ${fn}(**json.loads('''${argsJson}'''))
    # Handle Pydantic models and dataclasses
    if hasattr(result, 'model_dump'):
        result = result.model_dump()
    elif hasattr(result, '__dict__') and hasattr(result, '__dataclass_fields__'):
        from dataclasses import asdict
        result = asdict(result)
    print(json.dumps({"success": True, "data": result}))
except Exception as e:
    import traceback
    print(json.dumps({
        "success": False,
        "error": str(e),
        "traceback": traceback.format_exc()
    }))
    sys.exit(1)
`

  try {
    // Find the dazzle source directory relative to this CLI
    const dazzleSrc = new URL('../../../../src', import.meta.url).pathname

    const proc = Bun.spawn([python, '-c', code], {
      stdout: 'pipe',
      stderr: 'pipe',
      cwd: process.cwd(),
      env: {
        ...process.env,
        PYTHONPATH: `${dazzleSrc}:${process.env.PYTHONPATH || ''}`,
      },
    })

    const [stdout, stderr] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
    ])

    await proc.exited

    if (proc.exitCode !== 0) {
      // Try to parse error from stdout (our JSON output)
      try {
        const result = JSON.parse(stdout.trim())
        return {
          success: false,
          error: result.error || 'Unknown Python error',
          stderr: stderr || result.traceback,
        }
      } catch {
        return {
          success: false,
          error: stderr || stdout || 'Unknown Python error',
          stderr,
        }
      }
    }

    // Parse successful result
    const result = JSON.parse(stdout.trim())
    return {
      success: result.success,
      data: result.data as T,
      error: result.error,
    }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : String(err),
    }
  }
}

/**
 * Run a Python CLI command and capture output
 *
 * @param args - Command line arguments
 * @returns Result with stdout/stderr
 */
export async function runPythonCli(args: string[]): Promise<PythonResult<string>> {
  const python = await getPython()

  try {
    const proc = Bun.spawn([python, '-m', 'dazzle', ...args], {
      stdout: 'pipe',
      stderr: 'pipe',
      cwd: process.cwd(),
    })

    const [stdout, stderr] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
    ])

    await proc.exited

    if (proc.exitCode !== 0) {
      return {
        success: false,
        error: stderr || stdout,
        stderr,
      }
    }

    return {
      success: true,
      data: stdout,
    }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : String(err),
    }
  }
}

/**
 * Check if Python dazzle package is available
 */
export async function checkPythonDazzle(): Promise<{
  available: boolean
  version?: string
  error?: string
}> {
  const result = await callPython<{ version: string }>('dazzle', '__version__', {})

  if (result.success && result.data) {
    return {
      available: true,
      version: String(result.data),
    }
  }

  // Try alternative check
  const versionResult = await callPython<string>('importlib.metadata', 'version', {
    distribution_name: 'dazzle',
  })

  if (versionResult.success && versionResult.data) {
    return {
      available: true,
      version: versionResult.data,
    }
  }

  return {
    available: false,
    error: result.error || 'dazzle package not found',
  }
}
