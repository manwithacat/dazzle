/**
 * version command - Show version info
 */

import { z } from 'zod'
import type { CommandDefinition } from '../types/commands'
import { success } from '../lib/output'
import { checkPythonDazzle } from '../lib/python'

const VersionArgs = z.object({
  full: z.boolean().default(false).describe('Include Python package info'),
})

export const version: CommandDefinition<typeof VersionArgs> = {
  name: 'version',
  description: 'Show version information',
  args: VersionArgs,

  async run(args, _ctx) {
    const cliVersion = '0.8.0'
    const bunVersion = Bun.version

    // Fast path - no Python check
    if (!args.full) {
      return success({
        cli: cliVersion,
        runtime: 'bun',
        runtime_version: bunVersion,
        platform: process.platform,
        arch: process.arch,
      })
    }

    // Full mode - check Python dazzle package
    const pythonCheck = await checkPythonDazzle()

    return success({
      cli: cliVersion,
      runtime: 'bun',
      runtime_version: bunVersion,
      python_available: pythonCheck.available,
      python_dazzle_version: pythonCheck.version,
      platform: process.platform,
      arch: process.arch,
    })
  },
}
