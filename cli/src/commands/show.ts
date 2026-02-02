/**
 * show command - Inspect project structure
 *
 * Replaces: dazzle inspect, dazzle schema
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success, error, ErrorHints } from '../lib/output'

const ShowArgs = z.object({
  what: z
    .enum(['entities', 'surfaces', 'workspaces', 'services', 'all'])
    .default('all')
    .describe('What to show'),
  name: z.string().optional().describe('Specific item name to inspect'),
  verbose: z.boolean().default(false).describe('Show detailed information'),
})

interface EntityInfo {
  name: string
  description?: string
  fields: Array<{
    name: string
    type: string
    required: boolean
  }>
  relationships: Array<{
    name: string
    target: string
    kind: string
  }>
}

interface SurfaceInfo {
  name: string
  description?: string
  entity: string
  mode: string
  sections: string[]
}

interface ProjectInfo {
  name: string
  version: string
  entities: EntityInfo[]
  surfaces: SurfaceInfo[]
  workspaces: string[]
  services: string[]
}

export const show: CommandDefinition<typeof ShowArgs> = {
  name: 'show',
  description: 'Inspect project structure',
  help: `
Shows information about the project's entities, surfaces, workspaces, and services.

Use --name to inspect a specific item in detail.
Use --verbose for additional metadata.
`,
  examples: [
    'dazzle show',
    'dazzle show entities',
    'dazzle show entities --name Task',
    'dazzle show surfaces --verbose',
  ],
  args: ShowArgs,

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

    // Call Python to get project info
    const result = await ctx.python<ProjectInfo>(
      'dazzle.core.cli_bridge',
      'get_project_info_json',
      {
        path: ctx.cwd,
        include_details: args.verbose || !!args.name,
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
    const duration_ms = Date.now() - startTime

    // If specific name requested, find and return just that item
    if (args.name) {
      const entity = data.entities.find((e) => e.name === args.name)
      if (entity) {
        return success(entity, { duration_ms })
      }

      const surface = data.surfaces.find((s) => s.name === args.name)
      if (surface) {
        return success(surface, { duration_ms })
      }

      return error(
        ErrorHints.NOT_FOUND.code,
        `No entity or surface named '${args.name}'`,
        ErrorHints.NOT_FOUND.hint,
        {
          available_entities: data.entities.map((e) => e.name),
          available_surfaces: data.surfaces.map((s) => s.name),
        }
      )
    }

    // Filter based on what was requested
    switch (args.what) {
      case 'entities':
        return success(
          args.verbose ? data.entities : data.entities.map((e) => e.name),
          { duration_ms }
        )

      case 'surfaces':
        return success(
          args.verbose ? data.surfaces : data.surfaces.map((s) => s.name),
          { duration_ms }
        )

      case 'workspaces':
        return success(data.workspaces, { duration_ms })

      case 'services':
        return success(data.services, { duration_ms })

      case 'all':
      default:
        return success(
          {
            name: data.name,
            version: data.version,
            entities: data.entities.length,
            surfaces: data.surfaces.length,
            workspaces: data.workspaces.length,
            services: data.services.length,
            ...(args.verbose
              ? {
                  entity_names: data.entities.map((e) => e.name),
                  surface_names: data.surfaces.map((s) => s.name),
                }
              : {}),
          },
          { duration_ms }
        )
    }
  },
}
