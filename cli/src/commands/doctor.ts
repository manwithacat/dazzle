/**
 * doctor command - Check environment and dependencies
 *
 * Validates that all required tools are installed and configured correctly.
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error } from '../lib/output'

const DoctorArgs = z.object({
  fix: z.boolean().default(false).describe('Attempt to fix issues'),
})

interface Check {
  name: string
  status: 'ok' | 'warn' | 'error'
  message: string
  fix?: string
}

async function checkPython(ctx: any): Promise<Check> {
  try {
    const result = await ctx.python<{ version: string; path: string }>(
      'dazzle.core.cli_bridge',
      'get_python_info',
      {}
    )
    if (result.success && result.data) {
      return {
        name: 'Python',
        status: 'ok',
        message: `Python ${result.data.version} at ${result.data.path}`,
      }
    }
    return {
      name: 'Python',
      status: 'error',
      message: 'Python not found or dazzle not installed',
      fix: 'pip install dazzle',
    }
  } catch (e) {
    return {
      name: 'Python',
      status: 'error',
      message: `Python check failed: ${e}`,
      fix: 'Ensure Python 3.11+ is installed and dazzle package is available',
    }
  }
}

async function checkDocker(): Promise<Check> {
  try {
    const proc = Bun.spawn(['docker', '--version'], {
      stdout: 'pipe',
      stderr: 'pipe',
    })
    const output = await new Response(proc.stdout).text()
    await proc.exited

    if (proc.exitCode === 0) {
      const version = output.trim().split(' ')[2]?.replace(',', '') || 'unknown'
      return {
        name: 'Docker',
        status: 'ok',
        message: `Docker ${version}`,
      }
    }
    return {
      name: 'Docker',
      status: 'warn',
      message: 'Docker not running',
      fix: 'Start Docker Desktop or run: docker-machine start',
    }
  } catch {
    return {
      name: 'Docker',
      status: 'warn',
      message: 'Docker not installed (optional, needed for dazzle dev)',
      fix: 'Install Docker: https://docs.docker.com/get-docker/',
    }
  }
}

async function checkGit(): Promise<Check> {
  try {
    const proc = Bun.spawn(['git', '--version'], {
      stdout: 'pipe',
      stderr: 'pipe',
    })
    const output = await new Response(proc.stdout).text()
    await proc.exited

    if (proc.exitCode === 0) {
      const version = output.trim().split(' ')[2] || 'unknown'
      return {
        name: 'Git',
        status: 'ok',
        message: `Git ${version}`,
      }
    }
    return {
      name: 'Git',
      status: 'warn',
      message: 'Git not available',
    }
  } catch {
    return {
      name: 'Git',
      status: 'warn',
      message: 'Git not installed (optional)',
      fix: 'Install Git: https://git-scm.com/downloads',
    }
  }
}

async function checkProject(ctx: any): Promise<Check> {
  if (!ctx.configPath) {
    return {
      name: 'Project',
      status: 'warn',
      message: 'No DAZZLE project found in current directory',
      fix: 'Run: dazzle new my-project',
    }
  }

  try {
    const result = await ctx.python<{ valid: boolean; errors: string[] }>(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      { path: ctx.cwd }
    )

    if (result.success && result.data?.valid) {
      return {
        name: 'Project',
        status: 'ok',
        message: `Valid project at ${ctx.cwd}`,
      }
    }

    return {
      name: 'Project',
      status: 'error',
      message: `Project has errors: ${result.data?.errors?.join(', ') || 'unknown'}`,
      fix: 'Run: dazzle check --verbose',
    }
  } catch {
    return {
      name: 'Project',
      status: 'ok',
      message: `Project found at ${ctx.cwd}`,
    }
  }
}

async function checkMcp(ctx: any): Promise<Check> {
  try {
    const result = await ctx.python<{ registered: boolean; config_path: string }>(
      'dazzle.mcp.setup',
      'check_mcp_server',
      {}
    )

    if (result.success && result.data?.registered) {
      return {
        name: 'MCP Server',
        status: 'ok',
        message: 'Registered with Claude Code',
      }
    }

    return {
      name: 'MCP Server',
      status: 'warn',
      message: 'Not registered with Claude Code',
      fix: 'Run: dazzle mcp-setup',
    }
  } catch {
    return {
      name: 'MCP Server',
      status: 'warn',
      message: 'MCP check failed (optional feature)',
      fix: 'Run: dazzle mcp-setup',
    }
  }
}

export const doctor: CommandDefinition<typeof DoctorArgs> = {
  name: 'doctor',
  description: 'Check environment and dependencies',
  help: `
Validates your development environment for DAZZLE.

Checks:
  - Python installation and dazzle package
  - Docker availability (for dev server)
  - Git availability
  - Current project validity
  - MCP server registration
`,
  examples: [
    'dazzle doctor',
    'dazzle doctor --fix',
  ],
  args: DoctorArgs,

  async run(args, ctx) {
    const startTime = Date.now()

    // Run all checks in parallel
    const checks = await Promise.all([
      checkPython(ctx),
      checkDocker(),
      checkGit(),
      checkProject(ctx),
      checkMcp(ctx),
    ])

    const errors = checks.filter((c) => c.status === 'error')
    const warnings = checks.filter((c) => c.status === 'warn')
    const ok = checks.filter((c) => c.status === 'ok')

    const duration_ms = Date.now() - startTime

    // Format for human-readable output
    const summary = {
      checks: checks.map((c) => ({
        name: c.name,
        status: c.status,
        message: c.message,
        ...(c.fix ? { fix: c.fix } : {}),
      })),
      summary: {
        ok: ok.length,
        warnings: warnings.length,
        errors: errors.length,
      },
      healthy: errors.length === 0,
    }

    if (errors.length > 0) {
      return error(
        'ENVIRONMENT_ISSUES',
        `Found ${errors.length} error(s) and ${warnings.length} warning(s)`,
        errors.map((e) => e.fix).filter(Boolean).join('\n'),
        summary,
        { duration_ms }
      )
    }

    return success(summary, { duration_ms })
  },
}
