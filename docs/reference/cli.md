# CLI Reference

Complete reference for the `dazzle` command-line interface.

## Commands Overview

### Project Creation

| Command | Description |
|---------|-------------|
| `dazzle init` | Create a new project (optionally from an example) |
| `dazzle example` | Create a project from a built-in example |

### Project Operations

| Command | Description |
|---------|-------------|
| `dazzle validate` | Parse and validate all DSL modules |
| `dazzle lint` | Extended validation with style checks |
| `dazzle inspect` | Inspect entities, surfaces, and structure |
| `dazzle layout-plan` | Show workspace layout plan |
| `dazzle analyze-spec` | LLM-assisted DSL generation from a spec file |
| `dazzle info` | Show runtime installation status |
| `dazzle doctor` | Run environment health checks |
| `dazzle clean snapshots` | Remove local `.dazzle/spec_snapshots` (gitignored) |
| `dazzle schema` | Inspect generated app structure |



### Local cleanup

| Command | Description |
|---------|-------------|
| `dazzle clean snapshots` | Delete local `.dazzle/spec_snapshots` trees (gitignored) |
| `dazzle clean snapshots --dry-run` | List what would be removed |
| `dazzle clean snapshots --all` | Remove the entire snapshots directory (use after nested explosion) |
| `dazzle clean snapshots --keep N` | Keep the N newest top-level snapshot dirs (mtime); default 10 |

**Why:** historical ops rollback mirrors and accidental full-tree copies under
`.dazzle/spec_snapshots/` can nest prior snapshots and produce millions of paths
(rsync backups stall). The product writer was retired with ADR-0051; residual
trees are safe to delete. Prefer `--all` when doctor warns about nesting.

**Backup tip:** exclude `.dazzle/spec_snapshots/`, `.venv/`, `node_modules/`,
and `*cache*` when rsyncing the monorepo — durable state is source + `.git`.

See also: `dazzle.core.local_snapshots` (shared copy-ignore for any future writer).

### Runtime

| Command | Description |
|---------|-------------|
| `dazzle serve` | Start the full-stack app (API + UI) |
| `dazzle stop` | Stop the running Docker container |
| `dazzle rebuild` | Rebuild Docker image and restart |
| `dazzle logs` | View container logs |
| `dazzle status` | Show container status |
| `dazzle build` | Build a production deployment bundle |
| `dazzle build-ui` | Generate UI artifacts from AppSpec |
| `dazzle build-api` | Generate API spec from AppSpec |

### Database & Auth

| Command | Description |
|---------|-------------|
| `dazzle db` | Database migration commands (Alembic) |
| `dazzle migrate` | Run database migrations for production |
| `dazzle auth` | Manage authentication users and sessions |

### Testing

| Command | Description |
|---------|-------------|
| `dazzle test` | Multi-tier test runner (API, Playwright, LLM agent) |
| `dazzle check` | Run tests for a Dazzle application |
| `dazzle e2e` | Docker-based E2E testing with UX coverage |
| `dazzle story` | Story-driven test generation |

### API Specifications

| Command | Description |
|---------|-------------|
| `dazzle specs openapi` | Generate OpenAPI specification |
| `dazzle specs asyncapi` | Generate AsyncAPI specification |

### Events & Processes

| Command | Description |
|---------|-------------|
| `dazzle events` | Event system commands |
| `dazzle dlq` | Dead letter queue commands |
| `dazzle outbox` | Event outbox commands |
| `dazzle process-migrate` | Safe DSL version deployment migrations |
| `dazzle overrides` | Template override management (scan, check, list) |

### Infrastructure

| Command | Description |
|---------|-------------|
| `dazzle deploy` | Plan infrastructure + generate buildpack (Heroku) deploy files |
| `dazzle pitch` | Generate investor pitch materials from DSL |

### Vocabulary & Stubs

| Command | Description |
|---------|-------------|
| `dazzle vocab` | Manage app-local vocabulary (macros, aliases, patterns) |
| `dazzle stubs` | Manage domain service stubs |

### Monitoring

| Command | Description |
|---------|-------------|

### Tooling

| Command | Description |
|---------|-------------|
| `dazzle lsp` | Language Server Protocol commands |
| `dazzle mcp` | MCP (Model Context Protocol) server commands |
| `dazzle kg` | Knowledge graph management |

---

## Command Groups

Every registered command group (sub-app). Run `dazzle <group> --help` for its
subcommands, or `dazzle commands` / `dazzle search <keyword>` to discover commands
interactively. This table is drift-gated against the CLI registration in
`src/dazzle/cli/__init__.py` (`tests/unit/test_docs_drift.py`) — adding a group
there requires a row here.

| Group | Purpose |
|-------|---------|
| `dazzle agent` | Agent-first development commands |
| `dazzle analytics` | Analytics, consent, and privacy tooling |
| `dazzle api-pack` | API pack management — generate DSL, scaffold packs, inspect infrastructure |
| `dazzle auth` | Manage authentication users and sessions |
| `dazzle backup` | Backup and restore project data |
| `dazzle capability` | Manage opt-in feature capabilities |
| `dazzle clean` | Local hygiene — reclaim gitignored snapshot trees |
| `dazzle compliance` | Compliance documentation tools (ISO 27001 / SOC 2) |
| `dazzle composition` | Visual composition analysis for Dazzle apps |
| `dazzle conformance` | DSL conformance testing |
| `dazzle contribution` | Community contribution packaging — create, validate, share |
| `dazzle db` | Database migration commands (Alembic) |
| `dazzle demo` | Demo data management commands |
| `dazzle deploy` | Plan infrastructure + generate buildpack (Heroku) deploy files |
| `dazzle discovery` | App discovery and coherence analysis |
| `dazzle domain` | Agent-audience domain brief — extract/gaps/research/promote before DSL |
| `dazzle dlq` | Dead letter queue commands |
| `dazzle docs` | Documentation generation, validation, and maintenance |
| `dazzle events` | Event system commands |
| `dazzle feedback` | Feedback reports — list, triage, resolve |
| `dazzle fitness` | Agent-Led Fitness Methodology queries and triage |
| `dazzle guide` | Inspect onboarding guides declared in the project DSL |
| `dazzle inspect` | Introspect framework extension points and the public API surface |
| `dazzle kg` | Knowledge graph management |
| `dazzle lsp` | Language Server Protocol (LSP) commands |
| `dazzle mcp` | MCP (Model Context Protocol) server commands |
| `dazzle mock` | Vendor mock server management |
| `dazzle nightly` | Run quality checks in parallel (faster pipeline) |
| `dazzle outbox` | Event outbox commands |
| `dazzle param` | Runtime parameter management |
| `dazzle perf` | On-demand local OpenTelemetry tracing |
| `dazzle pipeline` | Run the deterministic quality pipeline |
| `dazzle pitch` | Generate investor pitch materials from DSL |
| `dazzle process` | Process proposal, storage, and diagramming |
| `dazzle process-migrate` | Process migration commands for safe DSL version deployments |
| `dazzle prove` | Static story binding evidence (agent closed loop #1605) + representation prove (#1617) |
| `dazzle pulse` | Project health pulse checks |
| `dazzle qa` | QA toolkit — visual quality evaluation and screenshot capture |
| `dazzle quality` | Quality pipeline scaffolding |
| `dazzle rbac` | RBAC verification and compliance |
| `dazzle representation` | Data-representation judgement — patterns, decide, classify (#1617) |
| `dazzle rhythm` | Rhythm analysis and lifecycle management |
| `dazzle scaffold` | Scaffold domain artefacts from agent closed-loop maps (#1605) |
| `dazzle sentinel` | SaaS Sentinel — failure-mode detection for Dazzle applications |
| `dazzle signing` | Provision the native document signing primitive |
| `dazzle spec` | Compare narrative product spec against DSL state — drift detection |
| `dazzle specs` | Generate API specifications (OpenAPI / AsyncAPI) |
| `dazzle story` | Story-driven test generation |
| `dazzle stubs` | Manage domain service stubs |
| `dazzle sweep` | Run unified health checks across example apps |
| `dazzle tenant` | Multi-tenant schema management |
| `dazzle test` | Multi-tier test runner (dsl-run / playwright / agent) |
| `dazzle test-design` | Test design proposal, persistence, and coverage analysis |
| `dazzle theme` | Inspect and manage app-shell themes |
| `dazzle ux` | UX verification — deterministic interaction testing |
| `dazzle vocab` | Manage app-local vocabulary (macros, aliases, patterns) |
| `dazzle worker` | Background-job worker + scheduler |

---

## Key Commands

### dazzle init

Create a new project.

```bash
dazzle init [PATH] [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--from` | `-f` | Copy from a built-in example |
| `--name` | `-n` | Project name (defaults to directory name) |
| `--title` | `-t` | Project title |
| `--here` | | Initialize in current directory even if not empty |
| `--list` | `-l` | List available examples |
| `--no-llm` | | Skip LLM instrumentation files |
| `--no-git` | | Skip git repository initialization |

```bash
# Create new project
dazzle init my_app

# Create from example
dazzle init my_app --from simple_task

# List available examples
dazzle init --list
```

---

### dazzle validate

Parse all DSL modules, resolve dependencies, and validate the merged AppSpec.

```bash
dazzle validate [OPTIONS]
```

```bash
dazzle validate
dazzle validate --verbose
```

---

### dazzle lint

Run extended lint checks (validation plus additional style warnings).

```bash
dazzle lint [OPTIONS]
```

---

### dazzle serve

Start the full-stack application (FastAPI backend + HTMX frontend).

```bash
dazzle serve [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--manifest` | `-m` | `dazzle.toml` | Path to manifest file |
| `--port` | `-p` | auto | Frontend port (default 3000) |
| `--api-port` | | auto | Backend API port (default 8000) |
| `--host` | | `127.0.0.1` | Host to bind to |
| `--local` | | | Run locally without Docker |
| `--watch` | `-w` | | Hot reload on DSL changes |
| `--watch-source` | `-W` | | Also watch framework source files |
| `--ui-only` | | | Serve static UI only (no API) |
| `--backend-only` | | | Serve API only (no frontend) |
| `--graphql` | | | Enable GraphQL endpoint at `/graphql` |
| `--rebuild` | | | Force Docker image rebuild |
| `--attach` | `-a` | | Stream Docker logs to terminal |
| `--database-url` | | | PostgreSQL URL (also reads `DATABASE_URL` env) |
| `--test-mode` | | | Enable E2E test endpoints |
| `--dev-mode` | | | Enable dev control plane |

```bash
# Docker mode (default)
dazzle serve

# Local mode with hot reload
dazzle serve --watch

# API server only
dazzle serve --backend-only

# Custom ports
dazzle serve --port 4000 --api-port 9000

# With GraphQL
dazzle serve --graphql
```

**Endpoints:**

| Endpoint | Description |
|----------|-------------|
| `http://localhost:3000` | UI |
| `http://localhost:8000/api/` | REST API |
| `http://localhost:8000/docs` | Interactive API docs (Swagger) |
| `http://localhost:8000/redoc` | Alternative API docs |
| `http://localhost:8000/graphql` | GraphQL (if `--graphql` enabled) |

---

### dazzle test

Multi-tier testing framework.

```bash
dazzle test COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `generate` | Generate E2E test spec from AppSpec |
| `run` | Run Playwright tests |
| `list` | List available test flows |
| `walk` | Scene walks list/validate/run/pack-dry-run (#1638) |
| `docs claims` | Job claim registry check (#1638 PR3) |
| `dsl-generate` | Generate tests from DSL definitions |
| `dsl-run` | **Tier 1**: Run API-based tests against a server |
| `tier2-generate` | **Tier 2**: Generate Playwright tests from surfaces |
| `agent` | **Tier 3**: Run LLM-agent-powered E2E tests |
| `populate` | Auto-populate stories and test designs from DSL |
| `run-all` | Run tests across all tiers |
| `create-sessions` | Create authenticated sessions for DSL personas |
| `diff-personas` | Compare route responses across personas |
| `feedback` | Track regressions and corrections |

```bash
# Run API-level tests
dazzle test dsl-run --base-url http://localhost:8000

# Run all tiers
dazzle test run-all

# Generate tests from DSL
dazzle test dsl-generate
```

---

### dazzle auth

Manage authentication users and sessions.

```bash
dazzle auth COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `create-user` | Create a new user |
| `list-users` | List users |
| `get-user` | Get user details |
| `update-user` | Update user properties |
| `reset-password` | Reset a user's password |
| `deactivate` | Soft-delete a user |
| `list-sessions` | List active sessions |
| `cleanup-sessions` | Remove expired sessions |
| `config` | Show auth system configuration |

```bash
dazzle auth create-user --email admin@example.com --roles admin
dazzle auth list-users
```

---

### dazzle deploy

Plan an app's infrastructure and generate buildpack deploy files.

```bash
dazzle deploy COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `plan` | Show the infrastructure an app needs (target-agnostic) |
| `heroku` | Generate Heroku/uv-buildpack deploy files |

See [Deployment](deployment.md) for the full guide.

---

### dazzle db

Database migration commands (Alembic).

```bash
dazzle db COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `revision` | Generate a new migration |
| `upgrade` | Apply pending migrations |
| `downgrade` | Rollback migrations |
| `current` | Show current revision |
| `history` | Show migration history |

---

### dazzle lsp

Language Server Protocol commands for IDE integration.

```bash
dazzle lsp COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `run` | Start the LSP server (diagnostics, hover, completion, go-to-definition) |
| `check` | Verify LSP dependencies are installed |
| `grammar-path` | Print path to bundled TextMate grammar |

---

### dazzle mcp

MCP (Model Context Protocol) server for AI assistants.

```bash
dazzle mcp COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `run` | Run the MCP server |
| `setup` | Register with Claude Code |
| `check` | Check MCP server status |

See [MCP Server](../architecture/mcp-server.md) for the full tool reference.

---

### dazzle specs

Generate API specifications.

```bash
dazzle specs COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `openapi` | Generate OpenAPI specification |
| `asyncapi` | Generate AsyncAPI specification |

```bash
dazzle specs openapi -o openapi.json
dazzle specs asyncapi -f yaml
```

---

### dazzle story

Story-driven test generation.

```bash
dazzle story COMMAND [OPTIONS]
```

| Subcommand | Description |
|------------|-------------|
| `propose` | Propose behavioural stories from DSL |
| `list` | List stories by status |
| `generate-tests` | Generate test designs from accepted stories |

---

## Common Workflows

### Development

```bash
# Validate, then serve with hot reload
dazzle validate && dazzle serve --watch
```

### Testing

```bash
# Run API tests against a running server
dazzle serve &
dazzle test dsl-run

# Run full test suite
dazzle test run-all
```

### CI/CD

```yaml
steps:
  - name: Validate DSL
    run: dazzle validate

  - name: Lint
    run: dazzle lint

  - name: Run API tests
    run: |
      dazzle serve --test-mode &
      sleep 5
      dazzle test dsl-run --base-url http://localhost:8000
```

### Deployment

```bash
# Discover the app's infrastructure requirements, then generate buildpack files
dazzle deploy plan
dazzle deploy heroku
```
