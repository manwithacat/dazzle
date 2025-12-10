# Change Log

All notable changes to the "dazzle-dsl" extension will be documented in this file.

## [0.8.0] - 2024-12-10

### Major Changes
- **50x faster CLI** - Extension now integrates with the new Bun-compiled DAZZLE CLI
- **Complete v0.7 DSL support** - Syntax highlighting for all DSL v0.7 features

### New Syntax Highlighting
- **State machines**: `transitions:`, `->`, `requires`, `role()`, `auto after`, `manual`
- **Computed fields**: `computed` keyword
- **Entity metadata**: `intent:`, `domain:`, `patterns:`, `extends:`
- **Invariants**: `invariant:`, `and`, `or`
- **Access rules**: `access:`, `read:`, `write:`, `owner`, `tenant`
- **Relationship semantics**: `has_many`, `has_one`, `belongs_to`, `embeds`
- **Delete behaviors**: `cascade`, `restrict`, `nullify`, `readonly`
- **Archetypes**: `archetype` keyword
- **Examples block**: `examples:`
- **UX block**: `ux:`, `purpose:`, `show:`, `filter:`, `search:`, `empty:`
- **Attention signals**: `attention`, `critical`, `warning`, `notice`, `info`
- **Workspaces**: `workspace` keyword
- **Domain services**: `kind:`, `input:`, `output:`, `guarantees:`, `stub:`
- **Flow tests**: `flow`, `navigate`, `fill`, `click`, `wait`, `assert`, `snapshot`, `expect`
- **Aggregate functions**: `count`, `sum`, `avg`, `max`, `min`, `days_until`, `days_since`

### New Commands
- **DAZZLE: Start Dev Server** (`dazzle dev`) - Start development server with hot reload
- **DAZZLE: Run Tests** (`dazzle test`) - Run E2E tests
- **DAZZLE: Eject to Standalone Code** (`dazzle eject`) - Generate standalone FastAPI + React code

### Changed
- Diagnostics now use `dazzle check --json` (v0.8.0 CLI) instead of `dazzle validate --format vscode`
- Lint command now uses `dazzle check --strict`
- Updated Claude integration prompts for v0.8.0 CLI commands
- JSON-based validation output parsing with backwards-compatible legacy fallback

### Technical
- Improved diagnostic error reporting with full line highlighting
- Better error handling when CLI commands fail
- Updated problem matcher for JSON output format

## [0.5.0] - 2024-11-22

### Added
- **Claude Code integration** - Simplified workflow with clipboard-based prompts
- Status bar item for SPEC.md detection
- SPEC → App workflow prompts for Claude

## [0.3.0] - 2024-11-21

### Added
- **LSP (Language Server Protocol) features** - Full IDE features powered by Python-based DAZZLE LSP server
- **Go-to-definition** - Navigate to entity and surface declarations
- **Hover documentation** - View entity/surface details on hover
- **Autocomplete** - Suggestions for:
  - Entity names
  - Surface names
  - Field types (uuid, str, int, float, bool, date, datetime, time, text, json, ref, enum)
  - Field modifiers (required, unique, pk, auto_add, auto_update)
- **Document symbols** - Hierarchical outline view of entities and fields
- Automatic LSP server detection and startup
- Graceful degradation when LSP server is unavailable

### Python LSP Server
- New `dazzle.lsp` package with pygls 2.0 integration
- Server entry point: `python -m dazzle.lsp`
- Loads DAZZLE projects and builds AppSpec for IDE features
- Document lifecycle management (open, change, save, close)
- Real-time project reloading on file changes

### VSCode LSP Client
- New `vscode-languageclient` integration
- Spawns Python LSP server via stdio transport
- Automatic Python interpreter detection (Python extension, env var, fallback)
- LSP server availability checking
- Enhanced status messages for LSP features

### Changed
- Extension activation is now async to support LSP startup
- Updated welcome message to indicate LSP feature status
- Extension now provides rich IDE features beyond syntax highlighting

## [0.2.0] - 2024-11-21

### Added
- CLI integration with DAZZLE commands
- Real-time validation diagnostics in Problems panel
- Automatic validation on file save
- File watchers for `.dsl` and `dazzle.toml` files
- Problem matcher for structured error display
- Functional commands:
  - **DAZZLE: Validate Project** - Runs validation and displays errors/warnings
  - **DAZZLE: Build Project** - Opens terminal and runs build
  - **DAZZLE: Lint Project** - Opens terminal and runs linter
- Output channel for validation feedback
- Progress notifications during validation

### Changed
- Updated extension activation to run validation on startup
- Enhanced welcome message to mention validation features
- Improved configuration options documentation

### Python CLI Updates
- Added `--format` flag to `dazzle validate` command
- New output format: `vscode` for machine-readable diagnostics
- Structured error output: `file:line:col: severity: message`
- Better error location tracking for parse errors

## [0.1.0] - 2024-11-21

### Added
- Initial release with basic syntax highlighting
- Language registration for `.dsl` and `.dazzle` files
- TextMate grammar for DAZZLE DSL
- Syntax highlighting for:
  - Keywords (module, app, entity, surface, etc.)
  - Type annotations (uuid, str, int, datetime, enum, ref)
  - Field modifiers (required, unique, pk, auto_add, auto_update)
  - Comments, strings, and numbers
  - Operators and identifiers
- Language configuration with:
  - Comment toggle support
  - Auto-closing brackets and quotes
  - Smart indentation
- Placeholder commands for future CLI integration
- Extension configuration options

### Coming Soon
- CLI integration (validate, build, lint commands)
- Live diagnostics and error reporting
- File watchers for automatic validation
- Problem matcher for DAZZLE errors
- LSP features (go-to-definition, hover, autocomplete)

## [Unreleased]

### Planned for v0.2
- CLI integration with DAZZLE commands
- Real-time validation on file save
- Problem matcher for structured error display
- File watchers for `.dsl` and `dazzle.toml` files
- Workspace detection and initialization

### Planned for v0.3
- LSP server implementation in Python
- Go-to-definition for entities, surfaces, and services
- Hover documentation
- Autocomplete for entity names and field types
- Document symbols and outline view
