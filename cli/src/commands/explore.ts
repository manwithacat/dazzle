/**
 * explore command - Interactive DSL explorer
 *
 * Provides a terminal UI for navigating entities and surfaces.
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'

const ExploreArgs = z.object({
  focus: z
    .enum(['entities', 'surfaces'])
    .optional()
    .describe('Start focused on entities or surfaces'),
})

interface EntityInfo {
  name: string
  label: string
  fields: Array<{
    name: string
    type: string
    required: boolean
  }>
}

interface SurfaceInfo {
  name: string
  label: string
  entity: string
  mode: string
}

interface ProjectInfo {
  name: string
  entities: EntityInfo[]
  surfaces: SurfaceInfo[]
}

export const explore: CommandDefinition<typeof ExploreArgs> = {
  name: 'explore',
  description: 'Interactive DSL explorer',
  help: `
Opens an interactive terminal UI for exploring your DSL.

Navigate with arrow keys or j/k, switch tabs with Tab, press Enter to
toggle details, and q to quit.
`,
  examples: [
    'dazzle explore',
    'dazzle explore --focus surfaces',
  ],
  args: ExploreArgs,

  async run(args, ctx) {
    // Check if we have a project
    if (!ctx.configPath) {
      return error(
        ErrorHints.NO_PROJECT.code,
        'No dazzle.toml found',
        ErrorHints.NO_PROJECT.hint
      )
    }

    // Load project data
    const result = await ctx.python<ProjectInfo>(
      'dazzle.core.cli_bridge',
      'get_project_info_json',
      {
        path: ctx.cwd,
        include_details: true,
      }
    )

    if (!result.success) {
      return error(
        ErrorHints.PYTHON_ERROR.code,
        result.error || 'Failed to load project',
        ErrorHints.PYTHON_ERROR.hint
      )
    }

    const data = result.data!

    // Transform to Explorer format
    const entities = data.entities.map((e: EntityInfo) => ({
      name: e.name,
      label: e.label || e.name,
      fields: e.fields || [],
    }))

    const surfaces = data.surfaces.map((s: SurfaceInfo) => ({
      name: s.name,
      label: s.label || s.name,
      entity: s.entity || '',
      mode: s.mode || 'view',
    }))

    // Check if TTY is available for interactive mode
    if (!process.stdin.isTTY) {
      // Non-interactive: just output the data
      return success({
        entities: entities.map(e => ({ name: e.name, label: e.label, fields: e.fields.length })),
        surfaces: surfaces.map(s => ({ name: s.name, label: s.label, entity: s.entity, mode: s.mode })),
        hint: 'Run in an interactive terminal for the full explorer UI',
      })
    }

    // Dynamic import to avoid loading React/Ink for non-interactive commands
    const { render } = await import('ink')
    const React = await import('react')
    const { Explorer } = await import('../ui/components/Explorer')

    // Render the explorer
    const { waitUntilExit } = render(
      React.createElement(Explorer, {
        entities,
        surfaces,
        initialTab: args.focus,
      })
    )

    await waitUntilExit()

    return success(
      { explored: true },
      { silent: true }
    )
  },
}
