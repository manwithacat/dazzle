/**
 * Command types for DAZZLE CLI
 */

import type { z } from 'zod'
import type { OutputOptions, CommandOutput } from './output'

export interface CommandContext {
  /** Current working directory */
  cwd: string
  /** Output options */
  output: OutputOptions
  /** Call Python module function */
  python: <T>(module: string, fn: string, args: Record<string, unknown>) => Promise<PythonResult<T>>
  /** Path to dazzle.toml if found */
  configPath?: string
  /** Parsed dazzle.toml config */
  config?: DazzleConfig
}

export interface PythonResult<T> {
  success: boolean
  data?: T
  error?: string
  stderr?: string
}

export interface DazzleConfig {
  name: string
  version: string
  modules?: string[]
  [key: string]: unknown
}

export interface CommandDefinition<TArgs extends z.ZodType = z.ZodType> {
  name: string
  description: string
  /** Long description shown in help */
  help?: string
  /** Example usages */
  examples?: string[]
  /** Zod schema for arguments */
  args: TArgs
  /** Command handler */
  run: (args: z.infer<TArgs>, ctx: CommandContext) => Promise<CommandOutput>
}

export type Command = CommandDefinition<z.ZodType>
