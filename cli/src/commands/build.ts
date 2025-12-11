/**
 * build command - Build for production
 *
 * Replaces: dazzle dnr build
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints, progress } from '../lib/output'

const BuildArgs = z.object({
  output: z.string().default('./dist').describe('Output directory'),
  docker: z.boolean().default(true).describe('Generate Dockerfile'),
  graphql: z.boolean().default(false).describe('Include GraphQL schema'),
})

export const build: CommandDefinition<typeof BuildArgs> = {
  name: 'build',
  description: 'Build for production deployment',
  help: `
Generates production-ready artifacts from your DAZZLE project.

Output includes:
  - Compiled Python backend
  - Static frontend assets
  - Dockerfile for containerized deployment
  - docker-compose.yml for orchestration
`,
  examples: [
    'dazzle build',
    'dazzle build --output ./release',
    'dazzle build --no-docker',
  ],
  args: BuildArgs,

  async run(args, ctx) {
    const startTime = Date.now()

    // Check if we have a project
    if (!ctx.configPath) {
      return error(
        ErrorHints.NO_PROJECT.code,
        'No dazzle.toml found',
        ErrorHints.NO_PROJECT.hint
      )
    }

    progress({ type: 'progress', step: 1, total: 4, message: 'Validating project...' }, ctx.output)

    // First validate
    const validateResult = await ctx.python<{ valid: boolean }>(
      'dazzle.core.cli_bridge',
      'validate_project_json',
      { path: ctx.cwd }
    )

    if (!validateResult.success || !validateResult.data?.valid) {
      return error(
        'BUILD_FAILED',
        'Project validation failed',
        'Run `dazzle check` to see validation errors'
      )
    }

    progress({ type: 'progress', step: 2, total: 4, message: 'Building backend...' }, ctx.output)

    // Call Python to build
    const result = await ctx.python<{
      output_path: string
      files: string[]
      docker: boolean
    }>(
      'dazzle.core.cli_bridge',
      'build_project_json',
      {
        path: ctx.cwd,
        output: args.output,
        docker: args.docker,
        graphql: args.graphql,
      }
    )

    if (!result.success) {
      // Extract actionable hint from error message
      const errorMsg = result.error || 'Build failed'
      let hint = 'Run `dazzle check` to validate the project'

      // Provide specific hints for common errors
      if (errorMsg.includes('Static file not found')) {
        hint = 'This may be a packaging issue. Try reinstalling: pip install --force-reinstall dazzle'
      } else if (errorMsg.includes('ImportError') || errorMsg.includes('ModuleNotFoundError')) {
        hint = 'Missing dependency. Ensure dazzle_dnr_ui is installed: pip install dazzle[dnr]'
      }

      return error('BUILD_FAILED', errorMsg, hint)
    }

    progress({ type: 'progress', step: 3, total: 4, message: 'Building frontend...' }, ctx.output)
    progress({ type: 'progress', step: 4, total: 4, message: 'Done' }, ctx.output)

    const duration_ms = Date.now() - startTime

    return success(
      {
        output: result.data?.output_path || args.output,
        files: result.data?.files || [],
        docker: args.docker,
        next_steps: args.docker
          ? [`cd ${args.output}`, 'docker build -t my-app .', 'docker run -p 8000:8000 my-app']
          : [`cd ${args.output}`, 'python -m uvicorn main:app'],
      },
      { duration_ms }
    )
  },
}
