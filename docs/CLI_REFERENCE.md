# DAZZLE CLI Reference

**Version**: 0.2.x
**Last Updated**: 2025-12-01

Complete reference for all DAZZLE command-line commands.

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `dazzle init` | Initialize new project |
| `dazzle validate` | Parse and validate DSL |
| `dazzle lint` | Extended lint checks |
| `dazzle dnr serve` | Run the application |
| `dazzle build` | Generate code (optional) |
| `dazzle test run` | Run E2E tests |

---

## Global Options

```bash
dazzle --version        # Show version info
dazzle --help           # Show help
dazzle --install-completion  # Install shell completion
```

---

## Project Creation

### init

Initialize a new DAZZLE project.

```bash
# Initialize in current directory (if empty)
dazzle init

# Create new directory
dazzle init ./my-project

# Initialize from example
dazzle init --from simple_task
dazzle init ./my-app --from support_tickets

# List available examples
dazzle init --list

# Force init in non-empty directory
dazzle init --here

# Minimal setup (no git, no LLM files)
dazzle init --no-llm --no-git
```

**Options**:

| Option | Description |
|--------|-------------|
| `--from, -f` | Copy from example template |
| `--name, -n` | Project name (defaults to directory) |
| `--title, -t` | Project title |
| `--here` | Init in current directory even if not empty |
| `--list, -l` | List available examples |
| `--no-llm` | Skip LLM context files |
| `--no-git` | Skip git initialization |

**Creates**:
- `dazzle.toml` - Project manifest
- `dsl/` - DSL modules directory
- `README.md` - Getting started guide
- `.gitignore` - Git ignore file
- LLM context files (unless `--no-llm`)

---

## Validation & Analysis

### validate

Parse all DSL modules and validate the merged AppSpec.

```bash
# Basic validation
dazzle validate

# VS Code format for IDE integration
dazzle validate --format vscode

# Custom manifest location
dazzle validate -m path/to/dazzle.toml
```

**Options**:

| Option | Description |
|--------|-------------|
| `--manifest, -m` | Path to dazzle.toml |
| `--format, -f` | Output format: `human` (default) or `vscode` |

**Output formats**:
- `human`: Human-readable colored output
- `vscode`: Machine-readable `file:line:col: severity: message`

### lint

Run extended lint rules beyond basic validation.

```bash
# Basic lint
dazzle lint

# Treat warnings as errors
dazzle lint --strict
```

**Options**:

| Option | Description |
|--------|-------------|
| `--manifest, -m` | Path to dazzle.toml |
| `--strict` | Treat warnings as errors |

**Checks**:
- Naming conventions
- Dead modules
- Unused imports
- Style violations

### inspect

Inspect AppSpec structure, patterns, and types.

```bash
# Show all info
dazzle inspect

# Show specific aspects
dazzle inspect --no-interfaces
dazzle inspect --no-patterns
dazzle inspect --types
```

**Options**:

| Option | Description |
|--------|-------------|
| `--manifest, -m` | Path to dazzle.toml |
| `--interfaces/--no-interfaces` | Show module interfaces |
| `--patterns/--no-patterns` | Show detected patterns |
| `--types` | Show type catalog |

**Shows**:
- Module interfaces (exports/imports)
- Detected patterns (CRUD, integrations)
- Type catalog (field types used)

### layout-plan

Visualize workspace layout plans.

```bash
# Show all workspaces
dazzle layout-plan

# Specific workspace
dazzle layout-plan -w dashboard

# For specific persona
dazzle layout-plan -p admin

# Explain archetype selection
dazzle layout-plan --explain

# JSON output
dazzle layout-plan --json
```

**Options**:

| Option | Description |
|--------|-------------|
| `--manifest, -m` | Path to dazzle.toml |
| `--workspace, -w` | Specific workspace to show |
| `--persona, -p` | Persona to generate plan for |
| `--json` | Output as JSON |
| `--explain, -e` | Explain archetype selection |

**Shows**:
- Selected layout archetype
- Surface allocation
- Attention signal assignments
- Budget analysis and warnings

---

## Dazzle Native Runtime (DNR)

### dnr serve

Run the application with DNR.

```bash
# Default: split Docker containers
dazzle dnr serve

# Run with log streaming
dazzle dnr serve --attach

# Run locally without Docker
dazzle dnr serve --local

# Custom ports
dazzle dnr serve --port 4000 --api-port 9000

# Backend only (for separate frontend)
dazzle dnr serve --backend-only

# UI only (static files)
dazzle dnr serve --ui-only

# Enable E2E test endpoints
dazzle dnr serve --test-mode

# Custom database path
dazzle dnr serve --db ./my.db

# Force rebuild Docker image
dazzle dnr serve --rebuild

# Legacy single-container mode
dazzle dnr serve --single-container
```

**Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--manifest, -m` | Path to dazzle.toml | `dazzle.toml` |
| `--port, -p` | Frontend port | `3000` |
| `--api-port` | Backend API port | `8000` |
| `--host` | Host to bind to | `127.0.0.1` |
| `--ui-only` | Serve UI only (static) | |
| `--backend-only` | Serve API only | |
| `--db` | SQLite database path | `.dazzle/data.db` |
| `--test-mode` | Enable test endpoints | |
| `--local` | Run without Docker | |
| `--rebuild` | Force Docker rebuild | |
| `--attach, -a` | Stream logs to terminal | |
| `--single-container` | Legacy combined mode | |

**URLs** (default):
- UI: http://localhost:3000
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

### dnr build-ui

Generate DNR UI artifacts.

```bash
dazzle dnr build-ui
dazzle dnr build-ui -o ./dist
```

### dnr build-api

Generate OpenAPI spec from AppSpec.

```bash
dazzle dnr build-api
dazzle dnr build-api -o ./api-spec.json
```

### dnr info

Show DNR installation status and features.

```bash
dazzle dnr info
```

### dnr stop

Stop running DNR Docker container.

```bash
dazzle dnr stop
```

### dnr rebuild

Rebuild Docker image and restart.

```bash
dazzle dnr rebuild
```

### dnr logs

View logs from running container.

```bash
dazzle dnr logs
dazzle dnr logs -f  # Follow logs
```

### dnr status

Show container status.

```bash
dazzle dnr status
```

---

## E2E Testing

### test generate

Generate E2E test specification from AppSpec.

```bash
# Print to stdout
dazzle test generate

# Save to file
dazzle test generate -o testspec.json

# YAML format
dazzle test generate --format yaml

# Skip auto-generated flows
dazzle test generate --no-flows

# Skip auto-generated fixtures
dazzle test generate --no-fixtures
```

**Options**:

| Option | Description |
|--------|-------------|
| `--manifest, -m` | Path to dazzle.toml |
| `-o` | Output file path |
| `--format` | Output format: `json` (default) or `yaml` |
| `--no-flows` | Skip auto-generated flows |
| `--no-fixtures` | Skip auto-generated fixtures |

### test run

Run E2E tests using Playwright.

```bash
# Run all tests
dazzle test run

# Filter by priority
dazzle test run --priority high

# Filter by tag
dazzle test run --tag crud

# Run specific flow
dazzle test run --flow Task_create_valid

# Custom URLs
dazzle test run --base-url http://localhost:3000 --api-url http://localhost:8000

# Headed mode (show browser)
dazzle test run --headed

# Custom timeout
dazzle test run --timeout 30000

# Save results
dazzle test run -o results.json

# Verbose output
dazzle test run -v
```

**Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--priority` | Filter by priority | |
| `--tag` | Filter by tag | |
| `--flow` | Run specific flow ID | |
| `--base-url` | Frontend URL | `http://localhost:3000` |
| `--api-url` | Backend URL | `http://localhost:8000` |
| `--headed/--headless` | Browser mode | `headless` |
| `--timeout` | Default timeout (ms) | `5000` |
| `-o` | Save results to file | |
| `-v` | Verbose output | |

**Prerequisites**:
- App running with `--test-mode`
- Playwright: `pip install playwright && playwright install chromium`

### test list

List available test flows.

```bash
# List all flows
dazzle test list

# Filter by priority
dazzle test list --priority high

# Filter by tag
dazzle test list --tag validation
```

---

## Docker E2E Testing

### e2e run

Run Docker-based E2E tests for an example.

```bash
# Test an example
dazzle e2e run simple_task

# With coverage threshold
dazzle e2e run contact_manager -c 80

# Save screenshots
dazzle e2e run ops_dashboard --copy-screenshots
```

**Options**:

| Option | Description |
|--------|-------------|
| `-c` | Coverage threshold percentage |
| `--copy-screenshots` | Save test screenshots |

### e2e run-all

Test all example projects.

```bash
dazzle e2e run-all
dazzle e2e run-all --copy-screenshots
```

### e2e clean

Clean up Docker containers.

```bash
dazzle e2e clean
```

---

## Code Generation (Optional)

### build

Generate code from AppSpec using a stack.

```bash
# Use default stack
dazzle build

# Specific stack
dazzle build --stack docker

# Custom output directory
dazzle build -o ./output

# Incremental build
dazzle build --incremental

# Show changes without building
dazzle build --diff

# Force full rebuild
dazzle build --force
```

**Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--manifest, -m` | Path to dazzle.toml | `dazzle.toml` |
| `--stack, -s` | Stack to use | From manifest or `micro` |
| `--out, -o` | Output directory | `./build` |
| `--incremental, -i` | Incremental build | |
| `--force` | Force full rebuild | |
| `--diff` | Show changes only | |

**Note**: `--backend` and `--backends` flags are deprecated. Use `--stack`.

### stacks

List available stacks.

```bash
dazzle stacks
```

**Available stacks**:

| Stack | Status | Description |
|-------|--------|-------------|
| `base` | Active | Base builder for custom stacks |
| `docker` | Active | Docker Compose for DNR |
| `django_micro_modular` | Deprecated | Django web app |
| `django_api` | Deprecated | Django REST API |
| `express_micro` | Deprecated | Express.js app |
| `openapi` | Deprecated | OpenAPI spec |

---

## MCP Server

### mcp

Run the MCP server for Claude Code integration.

```bash
dazzle mcp
dazzle mcp --working-dir /path/to/project
```

### mcp-setup

Register MCP server with Claude Code.

```bash
dazzle mcp-setup
dazzle mcp-setup --force  # Re-register
```

### mcp-check

Check MCP server status.

```bash
dazzle mcp-check
```

---

## LLM Integration

### analyze-spec

Analyze natural language specification using LLM.

```bash
dazzle analyze-spec requirements.md
dazzle analyze-spec requirements.md --generate-dsl
```

---

## Vocabulary Management

### vocab

Manage app-local vocabulary (macros, aliases, patterns).

```bash
dazzle vocab list
dazzle vocab add <term> <definition>
dazzle vocab remove <term>
```

---

## Deprecated Commands

### infra

**Deprecated**: Use `dazzle build --stack` instead.

```bash
# Old way
dazzle infra docker

# New way
dazzle build --stack docker
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DAZZLE_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `DAZZLE_NO_COLOR` | Disable colored output |
| `ANTHROPIC_API_KEY` | API key for LLM features |
| `OPENAI_API_KEY` | Alternative LLM provider |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Validation error |
| 3 | Build error |

---

## Shell Completion

Install shell completion for better CLI experience:

```bash
# Install for current shell
dazzle --install-completion

# Show completion script
dazzle --show-completion
```

Supports: bash, zsh, fish, PowerShell

---

## Related Documentation

- [CAPABILITIES.md](CAPABILITIES.md) - Feature overview
- [E2E_TESTING.md](E2E_TESTING.md) - Testing guide
- [TOOLING.md](TOOLING.md) - MCP and IDE integration
- [dnr/CLI.md](dnr/CLI.md) - DNR-specific commands (legacy)
