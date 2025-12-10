/**
 * new command - Create a new DAZZLE project
 *
 * Replaces: dazzle init
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error } from '../lib/output'

const NewArgs = z.object({
  name: z.string().optional().describe('Project name'),
  template: z.string().default('simple_task').describe('Template to use'),
  path: z.string().optional().describe('Directory to create project in'),
})

export const newCommand: CommandDefinition<typeof NewArgs> = {
  name: 'new',
  description: 'Create a new DAZZLE project',
  help: `
Creates a new DAZZLE project from a template.

Available templates:
  simple_task      - Basic task management app (default)
  contact_manager  - Contact management with categories
  uptime_monitor   - Service monitoring dashboard
  ops_dashboard    - Operations dashboard with metrics
`,
  examples: [
    'dazzle new my-app',
    'dazzle new --template contact_manager',
    'dazzle new my-app --path ./projects',
  ],
  args: NewArgs,

  async run(args, ctx) {
    const startTime = Date.now()
    const projectName = args.name || 'my-dazzle-app'
    const targetPath = args.path ? `${args.path}/${projectName}` : `./${projectName}`

    // Check if directory already exists
    const dir = Bun.file(targetPath)
    try {
      const stat = await Bun.file(`${targetPath}/dazzle.toml`).exists()
      if (stat) {
        return error(
          'PROJECT_EXISTS',
          `Project already exists at ${targetPath}`,
          'Choose a different name or path, or delete the existing project'
        )
      }
    } catch {
      // Directory doesn't exist, which is what we want
    }

    // Call Python to create project
    const result = await ctx.python<{ path: string; name: string }>(
      'dazzle.core.cli_bridge',
      'init_project_json',
      {
        name: projectName,
        template: args.template,
        path: targetPath,
      }
    )

    if (!result.success) {
      return error(
        'CREATE_FAILED',
        result.error || 'Failed to create project',
        'Check that the template exists and the target directory is writable'
      )
    }

    const duration_ms = Date.now() - startTime

    return success(
      {
        name: projectName,
        path: targetPath,
        template: args.template,
        next_steps: [
          `cd ${projectName}`,
          'dazzle dev',
        ],
      },
      { duration_ms }
    )
  },
}

// Export as 'new' would be a reserved word issue in some contexts
export { newCommand as new_ }
