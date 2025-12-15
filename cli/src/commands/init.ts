/**
 * init command - Interactive project initialization
 *
 * Provides a guided setup experience for new projects.
 */

import { z } from 'zod'
import * as p from '@clack/prompts'
import pc from 'picocolors'
import type { CommandDefinition } from '../types/commands'
import { success, error } from '../lib/output'
import { runInitWizard, showProgress, showSuccess, showError } from '../ui/prompts/init-wizard'

const InitArgs = z.object({
  name: z.string().optional().describe('Project name'),
  template: z.string().optional().describe('Template to use'),
  interactive: z.boolean().default(false).describe('Run interactive wizard'),
  i: z.boolean().default(false).describe('Shorthand for --interactive'),
})

export const init: CommandDefinition<typeof InitArgs> = {
  name: 'init',
  description: 'Create a new DAZZLE project (interactive)',
  help: `
Creates a new DAZZLE project with guided setup.

By default, runs in interactive mode with a beautiful wizard.
Use --no-interactive or provide all options for scripted usage.

Templates:
  blank            - Empty project with SPEC.md (default)
  simple_task      - Basic task management app
  contact_manager  - Contact management with categories
  saas             - Multi-tenant SaaS starter

Features (for blank template):
  auth             - User authentication
  api              - External API integrations
  queue            - Background job processing
  email            - Transactional email
`,
  examples: [
    'dazzle init                     # Interactive wizard',
    'dazzle init my-app              # Quick create with name',
    'dazzle init --template saas     # Use specific template',
    'dazzle init -i                  # Force interactive mode',
  ],
  args: InitArgs,

  async run(args, ctx) {
    const startTime = Date.now()
    const isInteractive = args.interactive || args.i || (!args.name && !args.template)

    if (isInteractive) {
      // Run interactive wizard
      const result = await runInitWizard(args.name)

      if (!result) {
        // User cancelled
        process.exit(0)
      }

      // Create project with wizard results
      const targetPath = `./${result.name}`

      // Check if directory exists
      try {
        const exists = await Bun.file(`${targetPath}/dazzle.toml`).exists()
        if (exists) {
          showError(`Project already exists at ${targetPath}`)
          process.exit(1)
        }
      } catch {
        // Directory doesn't exist, good
      }

      // Show progress spinner
      await showProgress([
        {
          label: 'Creating project structure',
          task: async () => {
            const createResult = await ctx.python<{ path: string }>(
              'dazzle.core.cli_bridge',
              'init_project_json',
              {
                name: result.name,
                template: result.template,
                path: targetPath,
                description: result.description,
                features: result.features,
              }
            )
            if (!createResult.success) {
              throw new Error(createResult.error || 'Failed to create project')
            }
          },
        },
        ...(result.git
          ? [
              {
                label: 'Initializing git repository',
                task: async () => {
                  const proc = Bun.spawn(['git', 'init'], {
                    cwd: targetPath,
                    stdout: 'ignore',
                    stderr: 'ignore',
                  })
                  await proc.exited
                },
              },
            ]
          : []),
      ])

      showSuccess(result.name, targetPath)

      const duration_ms = Date.now() - startTime
      return success(
        {
          name: result.name,
          path: targetPath,
          template: result.template,
          features: result.features,
          interactive: true,
        },
        { duration_ms }
      )
    }

    // Non-interactive mode - just create project
    const projectName = args.name || 'my-dazzle-app'
    const template = args.template || 'blank'
    const targetPath = `./${projectName}`

    // Check if directory exists
    try {
      const exists = await Bun.file(`${targetPath}/dazzle.toml`).exists()
      if (exists) {
        return error(
          'PROJECT_EXISTS',
          `Project already exists at ${targetPath}`,
          'Choose a different name or delete the existing project'
        )
      }
    } catch {
      // Good, doesn't exist
    }

    const createResult = await ctx.python<{ path: string; name: string }>(
      'dazzle.core.cli_bridge',
      'init_project_json',
      {
        name: projectName,
        template,
        path: targetPath,
      }
    )

    if (!createResult.success) {
      return error(
        'CREATE_FAILED',
        createResult.error || 'Failed to create project',
        'Check that the template exists and the target directory is writable'
      )
    }

    const duration_ms = Date.now() - startTime

    return success(
      {
        name: projectName,
        path: targetPath,
        template,
        next_steps: [`cd ${projectName}`, 'dazzle dev'],
      },
      { duration_ms }
    )
  },
}
