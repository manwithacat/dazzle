/**
 * DAZZLE CLI Router
 *
 * Parses arguments and routes to command handlers.
 */

import { z } from 'zod'
import type { Command, CommandContext, CommandOutput } from './types'
import { defaultOutputOptions, write, error, ErrorHints } from './lib/output'
import { callPython } from './lib/python'
import { findConfigPath, loadConfig, getProjectRoot } from './lib/config'

// Import commands
import { check, dev, show, version, new_, build, test, db, eject } from './commands'

// Command registry
const commands: Record<string, Command> = {
  check,
  dev,
  show,
  version,
  new: new_,
  build,
  test,
  db,
  eject,
}

// Global options schema
const GlobalOptions = z.object({
  help: z.boolean().default(false),
  json: z.boolean().default(false),
  verbose: z.boolean().default(false),
  quiet: z.boolean().default(false),
})

/**
 * Parse command line arguments
 */
function parseArgs(argv: string[]): {
  command: string | null
  args: Record<string, unknown>
  globalOpts: z.infer<typeof GlobalOptions>
} {
  const args: Record<string, unknown> = {}
  const globalOpts: Record<string, boolean> = {
    help: false,
    json: false,
    verbose: false,
    quiet: false,
  }

  let command: string | null = null
  let i = 0

  while (i < argv.length) {
    const arg = argv[i]

    // Global flags (before command)
    if (arg === '--help' || arg === '-h') {
      globalOpts.help = true
      i++
      continue
    }
    if (arg === '--json') {
      globalOpts.json = true
      i++
      continue
    }
    if (arg === '--verbose' || arg === '-v') {
      globalOpts.verbose = true
      i++
      continue
    }
    if (arg === '--quiet' || arg === '-q') {
      globalOpts.quiet = true
      i++
      continue
    }

    // Command name
    if (!arg.startsWith('-') && !command) {
      command = arg
      i++
      continue
    }

    // Command arguments
    if (arg.startsWith('--')) {
      const key = arg.slice(2)
      const nextArg = argv[i + 1]

      // Boolean flag or value
      if (!nextArg || nextArg.startsWith('-')) {
        args[key] = true
        i++
      } else {
        // Try to parse as number
        const numValue = Number(nextArg)
        args[key] = isNaN(numValue) ? nextArg : numValue
        i += 2
      }
      continue
    }

    // Positional argument (for commands that take a path, etc.)
    if (!arg.startsWith('-')) {
      if (!args.path) {
        args.path = arg
      }
      i++
      continue
    }

    i++
  }

  return {
    command,
    args,
    globalOpts: GlobalOptions.parse(globalOpts),
  }
}

/**
 * Show help message
 */
function showHelp(commandName?: string): void {
  if (commandName && commands[commandName]) {
    const cmd = commands[commandName]
    console.log(`
${cmd.name} - ${cmd.description}
${cmd.help || ''}

Examples:
${(cmd.examples || []).map((e) => `  ${e}`).join('\n')}
`)
    return
  }

  console.log(`
dazzle - Fast, LLM-friendly CLI for DAZZLE projects

Usage: dazzle <command> [options]

Commands:
  new        Create a new project
  dev        Start development server
  build      Build for production
  check      Validate DSL files
  show       Inspect project structure
  test       Run E2E tests
  db         Database operations
  eject      Generate standalone code
  version    Show version info

Global Options:
  --help, -h     Show help
  --json         Output as JSON
  --verbose, -v  Verbose output
  --quiet, -q    Suppress output

Examples:
  dazzle new my-app             # Create new project
  dazzle dev                    # Start dev server
  dazzle check                  # Validate project
  dazzle show entities          # List entities
  dazzle build                  # Build for production
  dazzle eject                  # Generate standalone code

Run 'dazzle <command> --help' for command-specific help.
`)
}

/**
 * Create command context
 */
async function createContext(
  globalOpts: z.infer<typeof GlobalOptions>
): Promise<CommandContext> {
  const outputOpts = defaultOutputOptions()

  if (globalOpts.json) outputOpts.format = 'json'
  if (globalOpts.verbose) outputOpts.verbose = true
  if (globalOpts.quiet) outputOpts.quiet = true

  const configPath = await findConfigPath()
  const config = configPath ? await loadConfig(configPath) : undefined

  return {
    cwd: configPath ? getProjectRoot(configPath) : process.cwd(),
    output: outputOpts,
    python: callPython,
    configPath: configPath ?? undefined,
    config: config ?? undefined,
  }
}

/**
 * Run the CLI
 */
export async function run(argv: string[] = process.argv.slice(2)): Promise<void> {
  const { command, args, globalOpts } = parseArgs(argv)

  // Show help if requested or no command
  if (globalOpts.help || !command) {
    showHelp(command ?? undefined)
    process.exit(command ? 0 : 1)
  }

  // Find command
  const cmd = commands[command]
  if (!cmd) {
    const ctx = await createContext(globalOpts)
    const output = error(
      'UNKNOWN_COMMAND',
      `Unknown command: ${command}`,
      `Available commands: ${Object.keys(commands).join(', ')}`,
      { command }
    )
    write(output, ctx.output)
    process.exit(1)
  }

  // Create context
  const ctx = await createContext(globalOpts)

  try {
    // Parse and validate command arguments
    const parsedArgs = cmd.args.safeParse(args)
    if (!parsedArgs.success) {
      const issues = parsedArgs.error.issues
      const output = error(
        'INVALID_ARGS',
        `Invalid arguments: ${issues.map((i) => i.message).join(', ')}`,
        `Run 'dazzle ${command} --help' for usage`,
        { issues }
      )
      write(output, ctx.output)
      process.exit(1)
    }

    // Run command
    const result = await cmd.run(parsedArgs.data, ctx)

    // Write output
    write(result, ctx.output)

    // Exit with appropriate code
    process.exit(result.success ? 0 : 1)
  } catch (err) {
    const output = error(
      'INTERNAL_ERROR',
      err instanceof Error ? err.message : String(err),
      'This is a bug in the CLI. Please report it.',
      { stack: err instanceof Error ? err.stack : undefined }
    )
    write(output, ctx.output)
    process.exit(1)
  }
}
