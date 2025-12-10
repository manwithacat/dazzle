/**
 * Output handling for DAZZLE CLI
 *
 * Provides JSON and human-readable output formatting with agent hints.
 */

import type {
  CommandOutput,
  CommandError,
  OutputMeta,
  OutputOptions,
  ProgressEvent,
  StreamEvent,
} from '../types/output'

// ANSI color codes
const colors = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  gray: '\x1b[90m',
}

function c(color: keyof typeof colors, text: string, useColor: boolean): string {
  return useColor ? `${colors[color]}${text}${colors.reset}` : text
}

/**
 * Determine if output should be JSON based on environment
 */
export function detectOutputFormat(): 'json' | 'human' {
  // If stdout is not a TTY (piped), use JSON
  if (!process.stdout.isTTY) return 'json'
  // If DAZZLE_JSON env var is set, use JSON
  if (process.env.DAZZLE_JSON === '1') return 'json'
  // If NO_COLOR env var is set, still use human but without colors
  return 'human'
}

/**
 * Create default output options
 */
export function defaultOutputOptions(): OutputOptions {
  const format = detectOutputFormat()
  return {
    format,
    verbose: process.env.DAZZLE_VERBOSE === '1',
    quiet: process.env.DAZZLE_QUIET === '1',
    color: process.stdout.isTTY && !process.env.NO_COLOR,
  }
}

/**
 * Create a success result
 */
export function success<T>(data: T, meta?: Partial<OutputMeta>): CommandOutput<T> {
  return {
    success: true,
    data,
    meta: meta as OutputMeta,
  }
}

/**
 * Create an error result with agent hint
 */
export function error(
  code: string,
  message: string,
  agentHint?: string,
  context?: Record<string, unknown>
): CommandOutput<never> {
  const err: CommandError = {
    code,
    message,
  }
  if (agentHint) err.__agent_hint = agentHint
  if (context) err.context = context
  return {
    success: false,
    error: err,
  }
}

/**
 * Format output for display
 */
export function format<T>(output: CommandOutput<T>, options: OutputOptions): string {
  if (options.format === 'json' || (options.format === 'auto' && !process.stdout.isTTY)) {
    return JSON.stringify(output, null, 2)
  }
  return formatHuman(output, options)
}

/**
 * Format output as human-readable text
 */
function formatHuman<T>(output: CommandOutput<T>, options: OutputOptions): string {
  const lines: string[] = []
  const useColor = options.color

  if (output.success) {
    if (output.data !== undefined) {
      lines.push(formatData(output.data, useColor))
    }
    if (output.meta?.truncated) {
      lines.push('')
      lines.push(c('yellow', `... ${output.meta.remaining} more items`, useColor))
      if (output.meta.__agent_hint) {
        lines.push(c('gray', `Hint: ${output.meta.__agent_hint}`, useColor))
      }
    }
  } else if (output.error) {
    lines.push(c('red', `Error: ${output.error.message}`, useColor))
    if (options.verbose && output.error.stack) {
      lines.push('')
      lines.push(c('gray', output.error.stack, useColor))
    }
    if (output.error.__agent_hint) {
      lines.push('')
      lines.push(c('cyan', `Hint: ${output.error.__agent_hint}`, useColor))
    }
  }

  if (output.meta?.duration_ms !== undefined && options.verbose) {
    lines.push('')
    lines.push(c('dim', `Completed in ${output.meta.duration_ms}ms`, useColor))
  }

  return lines.join('\n')
}

/**
 * Format data based on type
 */
function formatData(data: unknown, useColor: boolean): string {
  if (data === null || data === undefined) return ''
  if (typeof data === 'string') return data
  if (typeof data === 'number' || typeof data === 'boolean') return String(data)
  if (Array.isArray(data)) return formatArray(data, useColor)
  if (typeof data === 'object') return formatObject(data as Record<string, unknown>, useColor)
  return String(data)
}

function formatArray(arr: unknown[], useColor: boolean): string {
  if (arr.length === 0) return c('dim', '(empty)', useColor)

  // Check if array contains simple values
  if (arr.every((item) => typeof item !== 'object' || item === null)) {
    return arr.map((item) => `  • ${item}`).join('\n')
  }

  // Array of objects - format as table-like output
  return arr.map((item, i) => `${c('dim', `[${i}]`, useColor)} ${formatData(item, useColor)}`).join('\n\n')
}

function formatObject(obj: Record<string, unknown>, useColor: boolean): string {
  const entries = Object.entries(obj)
  if (entries.length === 0) return c('dim', '(empty)', useColor)

  const maxKeyLen = Math.max(...entries.map(([k]) => k.length))
  return entries
    .map(([key, value]) => {
      const paddedKey = key.padEnd(maxKeyLen)
      const formattedValue =
        typeof value === 'object' && value !== null
          ? '\n' + formatData(value, useColor).split('\n').map((l) => '  ' + l).join('\n')
          : String(value)
      return `${c('cyan', paddedKey, useColor)}  ${formattedValue}`
    })
    .join('\n')
}

/**
 * Write output to stdout
 */
export function write<T>(output: CommandOutput<T>, options: OutputOptions): void {
  if (options.quiet && output.success) return
  console.log(format(output, options))
}

/**
 * Write a progress event
 */
export function progress(event: ProgressEvent, options: OutputOptions): void {
  if (options.quiet) return

  if (options.format === 'json') {
    console.log(JSON.stringify(event))
  } else {
    const pct = Math.round((event.step / event.total) * 100)
    const bar = '█'.repeat(Math.floor(pct / 5)) + '░'.repeat(20 - Math.floor(pct / 5))
    const msg = options.color
      ? `${colors.cyan}[${bar}]${colors.reset} ${event.message}`
      : `[${bar}] ${event.message}`
    // Use stderr for progress so stdout remains clean for piping
    process.stderr.write(`\r${msg}`)
    if (event.step === event.total) {
      process.stderr.write('\n')
    }
  }
}

/**
 * Common error codes and their agent hints
 */
export const ErrorHints = {
  NO_PROJECT: {
    code: 'NO_PROJECT',
    hint: 'Run this command from a directory containing dazzle.toml, or use `dazzle new` to create a project',
  },
  INVALID_DSL: {
    code: 'INVALID_DSL',
    hint: 'Check DSL syntax. Common issues: missing colons after block declarations, incorrect indentation',
  },
  PYTHON_ERROR: {
    code: 'PYTHON_ERROR',
    hint: 'Ensure Python 3.11+ is installed and the dazzle package is available',
  },
  NOT_FOUND: {
    code: 'NOT_FOUND',
    hint: 'Check the name spelling. Use `dazzle show entities` to list available entities',
  },
} as const
