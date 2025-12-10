# DAZZLE CLI v2 Architecture

## Overview

Complete rewrite of the DAZZLE CLI using Bun for dramatically faster startup and better developer experience. This is a breaking change - no backward compatibility with v0.7 CLI vocabulary.

## Goals

1. **Performance**: <100ms cold start (current: ~500ms due to Python import overhead)
2. **LLM-First Design**: Built for AI coding agents from the ground up
3. **Simplified UX**: Flatten command hierarchy, remove legacy cruft
4. **Type Safety**: Full TypeScript with Zod validation
5. **Machine-Readable Output**: JSON output mode for all commands

## Research Summary

### Bun Advantages
- 6ms startup vs 170ms for npm/Node (source: [Bun docs](https://bun.com/))
- Native TypeScript execution without build step
- Single binary distribution possible
- Built-in test runner, bundler, package manager

### LLM Integration Patterns (from [Rethinking CLI for AI](https://www.notcheckmark.com/2025/07/rethinking-cli-interfaces-for-ai/))
- **Structured output**: JSON by default, human-readable opt-in
- **Context preservation**: Report truncation, remaining counts
- **Agent-friendly errors**: Include remediation hints in error messages
- **High-level commands**: Prefer "do what I mean" over composable primitives

## Current State Analysis

### Pain Points
1. **Startup latency**: Python import chain takes ~500ms
2. **Command sprawl**: 26 commands across multiple subgroups
3. **Inconsistent output**: Mix of human/machine formats
4. **Legacy baggage**: `cli_legacy.py` still in use, dead code paths
5. **Deep nesting**: `dazzle dnr serve`, `dazzle test run`, etc.

### Current Commands (26 total)
```
# Top-level
init, validate, lint, inspect, layout-plan, analyze-spec, example

# Groups
dnr: serve, stop, rebuild, logs, status, build, build-ui, build-api, migrate, info, inspect, test
test: generate, run, list
eject: run, status, adapters, openapi, verify
vocab: show, add, remove
stubs: generate, list
mcp: (server mode), mcp-setup, mcp-check
e2e: run, report
```

## New Design

### Philosophy
- **Flat over nested**: Most commands at top level
- **JSON-first**: `--human` flag for human output (default for TTY)
- **Agent hints**: Error messages include `__agent_hint` field
- **Streaming awareness**: Commands report progress for long operations

### New Command Structure

```
dazzle <command> [options]

Core Commands:
  dev          Start development server (replaces: dnr serve)
  build        Build for production (replaces: dnr build)
  new          Create new project (replaces: init)

Inspection:
  check        Validate and lint (replaces: validate + lint)
  show         Inspect entities/surfaces/spec (replaces: inspect)

Generation:
  eject        Generate standalone code
  stubs        Generate service stubs

Testing:
  test         Run tests (replaces: dnr test, test run)

Database:
  db           Database commands
    migrate    Run migrations
    seed       Seed test data
    reset      Reset database

Server Management:
  ps           Show running servers (replaces: dnr status)
  stop         Stop server (replaces: dnr stop)
  logs         View logs (replaces: dnr logs)

Meta:
  help         Show help (with examples)
  version      Show version info
  doctor       Check installation health
  mcp          Start MCP server
```

### Output Modes

All commands support:
```typescript
interface OutputOptions {
  format: 'json' | 'human' | 'auto'  // auto = json if piped, human if TTY
  verbose: boolean
  quiet: boolean
}
```

JSON output structure:
```typescript
interface CommandOutput<T> {
  success: boolean
  data?: T
  error?: {
    code: string
    message: string
    __agent_hint?: string  // Remediation hint for AI agents
  }
  meta?: {
    duration_ms: number
    truncated?: boolean
    remaining?: number
  }
}
```

### Agent-Friendly Features

1. **Structured errors with hints**:
```json
{
  "success": false,
  "error": {
    "code": "INVALID_DSL",
    "message": "Syntax error at line 42: unexpected token 'foo'",
    "__agent_hint": "Check for missing colons after block declarations. Common fix: add ':' after 'entity Task'"
  }
}
```

2. **Progress streaming**:
```json
{"type": "progress", "step": 1, "total": 5, "message": "Parsing DSL..."}
{"type": "progress", "step": 2, "total": 5, "message": "Validating entities..."}
{"type": "result", "success": true, "data": {...}}
```

3. **Context-aware truncation**:
```json
{
  "data": [...first 100 items...],
  "meta": {
    "truncated": true,
    "remaining": 1234,
    "__agent_hint": "Use --limit to fetch more, or --all to fetch everything"
  }
}
```

## Architecture

### Project Structure
```
cli/
├── src/
│   ├── index.ts          # Entry point
│   ├── cli.ts            # Command router
│   ├── commands/
│   │   ├── dev.ts
│   │   ├── build.ts
│   │   ├── new.ts
│   │   ├── check.ts
│   │   ├── show.ts
│   │   ├── test.ts
│   │   ├── db.ts
│   │   ├── eject.ts
│   │   └── ...
│   ├── lib/
│   │   ├── output.ts     # JSON/human output handling
│   │   ├── python.ts     # Python subprocess wrapper
│   │   ├── config.ts     # Config loading (dazzle.toml)
│   │   └── errors.ts     # Error types with agent hints
│   └── types/
│       ├── commands.ts
│       └── output.ts
├── package.json
├── tsconfig.json
└── bunfig.toml
```

### Python Bridge

The CLI shell handles argument parsing and output formatting, but delegates to Python for:
- DSL parsing (core/dsl_parser.py)
- AppSpec manipulation (core/ir/)
- DNR runtime (dazzle_dnr_back/, dazzle_dnr_ui/)
- Code generation (eject/)

```typescript
// lib/python.ts
import { spawn } from 'bun'

interface PythonResult<T> {
  success: boolean
  data?: T
  error?: string
}

async function callPython<T>(
  module: string,
  fn: string,
  args: Record<string, unknown>
): Promise<PythonResult<T>> {
  const proc = spawn([
    'python', '-c',
    `import json; from ${module} import ${fn}; print(json.dumps(${fn}(**json.loads('${JSON.stringify(args)}'))))`
  ])
  // ...
}
```

### Command Implementation Pattern

```typescript
// commands/check.ts
import { z } from 'zod'
import { command, output } from '../lib'

const CheckArgs = z.object({
  path: z.string().optional(),
  strict: z.boolean().default(false),
})

export const check = command({
  name: 'check',
  description: 'Validate DSL files and check for issues',
  args: CheckArgs,

  async run(args, ctx) {
    const result = await ctx.python('dazzle.core', 'validate_project', {
      path: args.path ?? process.cwd(),
      strict: args.strict,
    })

    if (!result.success) {
      return output.error({
        code: 'VALIDATION_FAILED',
        message: result.error,
        __agent_hint: 'Run `dazzle show errors` to see detailed error locations',
      })
    }

    return output.success({
      modules: result.data.modules,
      entities: result.data.entities,
      warnings: result.data.warnings,
    })
  }
})
```

## Migration Strategy

### Phase 1: Bun CLI Shell (Week 1-2)
- Set up Bun project in `cli/` directory
- Implement core infrastructure (output, python bridge, config)
- Implement `dev`, `check`, `show` commands
- Test with existing Python backend

### Phase 2: Core Commands (Week 2-3)
- `new`, `build`, `test`, `db` commands
- `eject`, `stubs` commands
- Deprecate old entry point

### Phase 3: Distribution (Week 3-4)
- Single binary compilation
- Homebrew formula update
- npm package
- Documentation update

### Phase 4: MCP Integration (Week 4)
- Update MCP server to use new CLI
- Improve tool descriptions with agent hints
- Add streaming support

## Success Criteria

1. `dazzle --version` completes in <100ms
2. All commands produce valid JSON with `--json` flag
3. Error messages include `__agent_hint` for common failures
4. No Python import on CLI startup (lazy load only when needed)
5. Single binary distribution via `bun build --compile`

## Open Questions

1. **Python version management**: Should CLI manage Python virtualenv?
2. **Watch mode**: Should `dazzle dev` include file watching by default?
3. **Interactive mode**: Should we support a REPL for exploration?
4. **Plugin system**: Should commands be extensible?

## References

- [Bun Documentation](https://bun.com/docs)
- [BunCLI-Kit](https://github.com/sebastien-timoner/BunCLI-Kit)
- [Rethinking CLI for AI](https://www.notcheckmark.com/2025/07/rethinking-cli-interfaces-for-ai/)
- [Martin Fowler: Building CLI Coding Agents](https://martinfowler.com/articles/build-own-coding-agent.html)
