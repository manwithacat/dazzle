/**
 * Output types for DAZZLE CLI
 *
 * All commands produce structured output that can be rendered as JSON or human-readable.
 */

export interface CommandOutput<T = unknown> {
  success: boolean
  data?: T
  error?: CommandError
  meta?: OutputMeta
}

export interface CommandError {
  code: string
  message: string
  /** Hint for AI coding agents on how to fix the issue */
  __agent_hint?: string
  /** Stack trace (only in verbose mode) */
  stack?: string
  /** Additional context */
  context?: Record<string, unknown>
}

export interface OutputMeta {
  /** Command execution time in milliseconds */
  duration_ms: number
  /** Whether output was truncated */
  truncated?: boolean
  /** Number of remaining items if truncated */
  remaining?: number
  /** Hint for agents about truncation */
  __agent_hint?: string
}

export interface ProgressEvent {
  type: 'progress'
  step: number
  total: number
  message: string
}

export interface ResultEvent<T> {
  type: 'result'
  success: boolean
  data?: T
  error?: CommandError
}

export type StreamEvent<T> = ProgressEvent | ResultEvent<T>

export type OutputFormat = 'json' | 'human' | 'auto'

export interface OutputOptions {
  format: OutputFormat
  verbose: boolean
  quiet: boolean
  color: boolean
}
