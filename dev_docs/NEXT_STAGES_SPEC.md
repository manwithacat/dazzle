# DAZZLE Next Development Stages - Detailed Specifications
**Date**: 2025-11-23
**Version**: Post v0.1.0
**Status**: Ready for Implementation

> **📍 Navigation**: This document provides detailed specifications for immediate post-v0.1.0 work.
> For the master roadmap and overall planning, see **`/ROADMAP.md`** (single source of truth).

---

## Overview

This document provides detailed specifications for the next development phases based on the comprehensive gap analysis. Work is organized into 5 phases with clear priorities and deliverables.

**Total Estimated Effort**: 31-41 hours
**Critical Path** (Phases 0-2): 20-27 hours

---

## Phase 0: MCP Server Distribution 🔴🔴

**Priority**: CRITICAL - Top Priority
**Estimated Time**: 10-14 hours
**Impact**: CRITICAL - Makes MCP server discoverable and usable by all users
**Reference**: See `dev_docs/mcp_distribution_strategy.md` for complete details

### Problem

When users create a new DAZZLE project using `dazzle init` or `dazzle clone`, and then open Claude Code in that directory, the DAZZLE MCP server is not automatically available. This creates a poor user experience where the powerful MCP integration is effectively hidden.

### Solution Overview

Multi-layered approach combining:
1. **CLI commands** for MCP server management
2. **Project initialization** to create MCP configs
3. **Post-install hooks** for Homebrew and PyPI
4. **Documentation** for manual setup and troubleshooting

### Task 0.1: Add MCP CLI Commands

**Time**: 3-4 hours
**Files**: `src/dazzle/cli.py`, `src/dazzle/mcp/setup.py` (NEW)

#### Implementation

**Add three new CLI commands**:

1. **`dazzle mcp`** - Run MCP server with working directory
   ```python
   @app.command()
   def mcp(
       working_dir: Path = typer.Option(
           Path.cwd(),
           "--working-dir",
           help="Project root directory"
       )
   ):
       """Run DAZZLE MCP server."""
       import asyncio
       from dazzle.mcp.server import run_server
       asyncio.run(run_server(working_dir.resolve()))
   ```

2. **`dazzle mcp-setup`** - Register MCP server with Claude Code
   ```python
   @app.command()
   def mcp_setup(
       force: bool = typer.Option(
           False,
           "--force",
           help="Overwrite existing MCP server config"
       )
   ):
       """Register DAZZLE MCP server with Claude Code."""
       from dazzle.mcp.setup import register_mcp_server

       success = register_mcp_server(force=force)
       if success:
           typer.echo("✅ DAZZLE MCP server registered successfully")
       else:
           typer.echo("❌ Failed to register MCP server", err=True)
           raise typer.Exit(1)
   ```

3. **`dazzle mcp-check`** - Verify MCP server status
   ```python
   @app.command()
   def mcp_check():
       """Verify MCP server configuration and availability."""
       from dazzle.mcp.setup import check_mcp_server

       status = check_mcp_server()

       typer.echo(f"MCP Server Status: {status['status']}")
       typer.echo(f"Registered: {status['registered']}")
       typer.echo(f"Config Location: {status['config_path']}")

       if status['tools']:
           typer.echo(f"\nAvailable Tools ({len(status['tools'])}):")
           for tool in status['tools']:
               typer.echo(f"  - {tool}")
   ```

**Create `src/dazzle/mcp/setup.py`** with functions:
- `get_claude_config_path()` - Find Claude Code config directory
- `register_mcp_server(force=False)` - Register in config
- `check_mcp_server()` - Verify registration and availability

See `dev_docs/mcp_distribution_strategy.md` for complete implementation.

#### Acceptance Criteria
- [ ] `dazzle mcp` command runs MCP server
- [ ] `dazzle mcp-setup` registers server in Claude Code config
- [ ] `dazzle mcp-check` shows current status
- [ ] Tests added for all commands
- [ ] Works on macOS and Linux

---

### Task 0.2: Update Project Initialization

**Time**: 2 hours
**Files**: `src/dazzle/cli.py` (init command), templates in examples/

#### Implementation

**Update `dazzle init` to create `.claude/mcp.json`**:

```python
def _create_claude_config(project_root: Path):
    """Create .claude/ configuration."""
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)

    # Existing CLAUDE.md creation...

    # NEW: Create mcp.json for project-local MCP server
    mcp_config = {
        "mcpServers": {
            "dazzle": {
                "command": "dazzle",
                "args": ["mcp", "--working-dir", "${projectDir}"],
                "env": {},
                "autoStart": True
            }
        }
    }

    mcp_config_path = claude_dir / "mcp.json"
    mcp_config_path.write_text(json.dumps(mcp_config, indent=2))

    print(f"✅ Created .claude/mcp.json")
```

**Update `.claude/CLAUDE.md` template** to include MCP setup instructions:

```markdown
# DAZZLE Project

This project uses the DAZZLE MCP server for enhanced tooling.

## MCP Server Setup

### Automatic (Recommended)
If you installed DAZZLE via Homebrew or pip, the MCP server should be automatically available.

### Manual Setup
If the MCP tools are not available, run:

```bash
dazzle mcp-setup
```

Or add this to your Claude Code config manually:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"]
    }
  }
}
```

### Verify MCP Server
Check if tools are available:

```bash
dazzle mcp-check
```

You should have access to these tools:
- `validate_dsl` - Validate project DSL files
- `build` - Generate code from DSL
- `inspect_entity` - Inspect entity definitions
- `lookup_concept` - Look up DSL concepts
- And more...

Try asking: "What DAZZLE tools do you have access to?"
```

#### Acceptance Criteria
- [ ] `dazzle init` creates `.claude/mcp.json`
- [ ] Template includes MCP setup instructions
- [ ] Works for both `init` and `clone` commands
- [ ] Documentation updated

---

### Task 0.3: Homebrew Post-Install Hook

**Time**: 2-3 hours
**Files**: `homebrew/dazzle.rb`

#### Implementation

**Add post-install hook to Homebrew formula**:

```ruby
def post_install
  require "json"

  # Find Claude Code config directory
  claude_dirs = [
    Pathname.new(ENV["HOME"]) / ".config" / "claude-code",
    Pathname.new(ENV["HOME"]) / ".claude",
    Pathname.new(ENV["HOME"]) / "Library" / "Application Support" / "Claude Code"
  ]

  config_path = nil
  claude_dirs.each do |dir|
    if dir.exist?
      config_path = dir / "mcp_servers.json"
      break
    end
  end

  # Default to ~/.claude/
  config_path ||= Pathname.new(ENV["HOME"]) / ".claude" / "mcp_servers.json"
  config_path.dirname.mkpath

  # MCP server config
  dazzle_server = {
    "command" => "#{opt_libexec}/bin/python",
    "args" => ["-m", "dazzle.mcp"],
    "env" => {},
    "autoStart" => true
  }

  # Merge with existing config
  if config_path.exist?
    config = JSON.parse(config_path.read)
  else
    config = { "mcpServers" => {} }
  end

  config["mcpServers"] ||= {}
  config["mcpServers"]["dazzle"] = dazzle_server

  config_path.write(JSON.pretty_generate(config))

  ohai "DAZZLE MCP server registered at #{config_path}"
  ohai "Restart Claude Code to enable DAZZLE tools"
end

def post_uninstall
  require "json"

  config_path = Pathname.new(ENV["HOME"]) / ".claude" / "mcp_servers.json"
  return unless config_path.exist?

  config = JSON.parse(config_path.read)
  config["mcpServers"]&.delete("dazzle")

  config_path.write(JSON.pretty_generate(config))
  ohai "DAZZLE MCP server unregistered"
end
```

**Update caveats**:

```ruby
def caveats
  <<~EOS
    DAZZLE has been installed!

    MCP Server: ✅ Registered with Claude Code
    Restart Claude Code to enable DAZZLE tools.

    Quick start:
      mkdir my-project && cd my-project
      dazzle init
      dazzle build

    Verify MCP server:
      dazzle mcp-check

    Documentation:
      https://github.com/manwithacat/dazzle
  EOS
end
```

#### Acceptance Criteria
- [ ] Post-install hook registers MCP server
- [ ] Merges with existing MCP servers (doesn't overwrite)
- [ ] Post-uninstall cleans up registration
- [ ] Caveats mention MCP server status
- [ ] Tested on fresh install

---

### Task 0.4: PyPI Post-Install Script

**Time**: 2-3 hours
**Files**: `scripts/post_install.py` (NEW), `pyproject.toml`

#### Implementation

**Create `scripts/post_install.py`**:

```python
"""Post-install script for PyPI/pip installations."""

import json
import sys
from pathlib import Path


def post_install():
    """Register DAZZLE MCP server after pip install."""
    home = Path.home()

    # Find Claude Code config
    candidates = [
        home / ".config" / "claude-code" / "mcp_servers.json",
        home / ".claude" / "mcp_servers.json",
    ]

    config_path = None
    for path in candidates:
        if path.parent.exists():
            config_path = path
            break

    if not config_path:
        config_path = home / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # MCP server config
    dazzle_server = {
        "command": sys.executable,
        "args": ["-m", "dazzle.mcp"],
        "env": {},
        "autoStart": True
    }

    # Merge with existing
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"mcpServers": {}}

    config.setdefault("mcpServers", {})["dazzle"] = dazzle_server

    config_path.write_text(json.dumps(config, indent=2))
    print(f"✅ DAZZLE MCP server registered at {config_path}")


if __name__ == "__main__":
    try:
        post_install()
    except Exception as e:
        print(f"⚠️  Could not auto-register MCP server: {e}")
        print("   Run 'dazzle mcp-setup' manually after installation")
        # Don't fail install on MCP registration errors
```

**Update `pyproject.toml`** to run post-install:

```toml
[project.scripts]
dazzle = "dazzle.cli:main"
dazzle-post-install = "scripts.post_install:post_install"
```

**Add to README.md**:

```markdown
## Installation

### Via pip/pipx

```bash
# Install DAZZLE
pip install dazzle

# MCP server is auto-registered during install
# If auto-registration failed, run manually:
dazzle mcp-setup
```
```

#### Acceptance Criteria
- [ ] Post-install script created
- [ ] Runs after pip install
- [ ] Gracefully handles errors (doesn't break install)
- [ ] Works with pip, pipx, and uv
- [ ] Tested in clean virtual environment

---

### Task 0.5: Documentation

**Time**: 1-2 hours
**Files**: `docs/MCP_INTEGRATION.md` (NEW), `README.md`, `.claude/CLAUDE.md` templates

#### Create `docs/MCP_INTEGRATION.md`

**Content**:

```markdown
# DAZZLE MCP Server Integration

The DAZZLE MCP (Model Context Protocol) server provides powerful tools for working with DAZZLE projects directly from Claude Code.

## Quick Start

### Automatic Setup (Recommended)

If you installed DAZZLE via Homebrew or pip, the MCP server should already be registered:

1. Create a new DAZZLE project:
   ```bash
   dazzle init my-project
   cd my-project
   ```

2. Open Claude Code in this directory

3. Ask Claude: "What DAZZLE tools do you have access to?"

You should see tools like `validate_dsl`, `build`, `inspect_entity`, etc.

### Manual Setup

If the MCP server isn't automatically available:

```bash
# Register MCP server
dazzle mcp-setup

# Verify registration
dazzle mcp-check
```

## Available Tools

### Project Validation
- `validate_dsl` - Validate all DSL files in the project
- `lint_project` - Run extended validation rules
- `list_modules` - Show all modules and their dependencies

### Code Inspection
- `inspect_entity <name>` - Show entity definition with fields and types
- `inspect_surface <name>` - Show surface configuration
- `analyze_patterns` - Detect CRUD and integration patterns

### Code Generation
- `build [--stacks <list>]` - Generate code for specified stacks

### Learning & Help
- `lookup_concept <term>` - Look up DSL concepts (persona, workspace, etc.)
- `find_examples [--features <list>]` - Find example projects by features

## Resources

The MCP server provides read-only access to:
- **DAZZLE Glossary** - Definitions of DSL v0.2 terms
- **DSL Reference** - Complete syntax reference
- **Semantic Index** - Structured concept definitions
- **Example Catalog** - Example projects with metadata
- **Project Manifest** - Your dazzle.toml configuration
- **DSL Files** - All .dsl files in your project

## Troubleshooting

### MCP Tools Not Showing Up

1. **Check registration**:
   ```bash
   dazzle mcp-check
   ```

2. **Re-register**:
   ```bash
   dazzle mcp-setup --force
   ```

3. **Restart Claude Code**

4. **Verify config** at `~/.claude/mcp_servers.json`:
   ```json
   {
     "mcpServers": {
       "dazzle": {
         "command": "dazzle",
         "args": ["mcp", "--working-dir", "${projectDir}"]
       }
     }
   }
   ```

### Wrong DAZZLE Version

If you have multiple DAZZLE installations:

```bash
# Check which version is registered
dazzle mcp-check

# Re-register current version
dazzle mcp-setup --force
```

### Permission Errors

If MCP setup fails due to permissions:

```bash
# Ensure config directory exists
mkdir -p ~/.claude

# Run setup again
dazzle mcp-setup
```

## Manual Configuration

If automatic setup doesn't work, add this to your Claude Code config:

**Global Config** (`~/.claude/mcp_servers.json`):
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/path/to/python",
      "args": ["-m", "dazzle.mcp"],
      "autoStart": true
    }
  }
}
```

**Project Config** (`.claude/mcp.json`):
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"],
      "autoStart": true
    }
  }
}
```

## Development Mode

When working in the DAZZLE repository itself, the MCP server automatically detects "dev mode" and provides additional tools for working with example projects.

## Advanced Usage

### Custom Working Directory

```bash
dazzle mcp --working-dir /path/to/project
```

### Testing MCP Server

```bash
# Start MCP server manually
dazzle mcp

# In another terminal, test with MCP inspector
npx @modelcontextprotocol/inspector dazzle mcp
```

## See Also

- [VS Code Extension Guide](vscode_extension_user_guide.md)
- [DAZZLE DSL Reference](DAZZLE_DSL_REFERENCE.md)
- [MCP Distribution Strategy](../dev_docs/mcp_distribution_strategy.md) (developers)
```

#### Update README.md

Add section after installation:

```markdown
## MCP Server Integration

DAZZLE includes an MCP (Model Context Protocol) server that integrates with Claude Code:

- 🛠️ **Tools**: Validate DSL, build projects, inspect definitions
- 📚 **Resources**: Access glossary, DSL reference, examples
- 🤖 **Context**: Claude understands your project structure

**Setup** (automatic with Homebrew/pip):
```bash
dazzle mcp-check  # Verify MCP server status
```

See [MCP Integration Guide](docs/MCP_INTEGRATION.md) for details.
```

#### Acceptance Criteria
- [ ] `docs/MCP_INTEGRATION.md` created
- [ ] README mentions MCP integration
- [ ] Template `.claude/CLAUDE.md` includes setup instructions
- [ ] Troubleshooting section covers common issues
- [ ] Cross-links updated

---

### Phase 0 Success Criteria

**This phase is complete when**:
- [ ] `dazzle mcp`, `dazzle mcp-setup`, `dazzle mcp-check` commands work
- [ ] `dazzle init` creates `.claude/mcp.json`
- [ ] Homebrew post-install registers MCP server
- [ ] PyPI post-install registers MCP server
- [ ] Documentation complete and accurate
- [ ] Fresh install → MCP tools available in <5 minutes
- [ ] Users discover MCP tools without reading docs

---

## Phase 1: Critical Documentation 🔴

**Priority**: IMMEDIATE
**Estimated Time**: 6-8 hours
**Impact**: CRITICAL - Fixes AI assistant guidance and contributor onboarding

### Task 1.1: Rewrite CLAUDE.md

**Time**: 3 hours
**Files**: `.claude/CLAUDE.md`

#### Current Problems
- Says IR "to be implemented" (it's 900+ lines, complete)
- Says parser "needs implementation" (it's 800+ lines, complete)
- Says backends "none implemented" (6 stacks exist)
- Lists wrong stages as incomplete

#### Specification

Create new CLAUDE.md with these sections:

**1. Project Overview** (Update existing)
```markdown
DAZZLE v0.1.0 - Complete DSL-to-Code Generation System

Released: November 2025
Status: Production-ready, actively maintained
Stacks: 6 implemented (Django, Express, OpenAPI, Docker, Terraform, + modular)
```

**2. What's Actually Implemented** (NEW)
```markdown
## Current Implementation Status (v0.1.0)

### ✅ Fully Complete
- **DSL Parser**: 800+ lines, handles all DSL constructs
- **Internal Representation (IR)**: 900+ lines, complete Pydantic models
- **Module System**: Dependency resolution, cycle detection, linking
- **Validation**: Comprehensive lint rules, type checking
- **Stack System**: 6 production stacks
- **LLM Integration**: Spec analysis, DSL generation, Q&A
- **LSP Server**: Real-time diagnostics, hover info, completions
- **VS Code Extension**: Full IDE integration
- **Test Suite**: 59 tests, integration coverage
- **CI/CD**: GitHub Actions, automated builds
- **Distribution**: Homebrew, PyPI-ready, multiple install methods

### 🚧 Partially Complete
- Integration actions/syncs parsing (uses stubs, functional but limited)
- OpenAPI security schemes (placeholder, manually addable)

### 📋 Planned
- Export declarations (v2.0)
- Advanced pattern detection (v2.0)
- Additional stacks (community-driven)
```

**3. Architecture** (Rewrite with actual structure)
```markdown
## Architecture

### Three-Layer Model (FULLY IMPLEMENTED)

1. **DSL Layer** → `dsl/` files
   Implemented in: `src/dazzle/core/dsl_parser.py` (800 lines)

2. **IR Layer** → Internal Representation
   Implemented in: `src/dazzle/core/ir.py` (900 lines)
   Complete Pydantic models, immutable, type-safe

3. **Stack Layer** → Code Generation
   Implemented in: `src/dazzle/stacks/`
   - django_micro_modular: Complete Django apps with admin
   - django_api: REST API with DRF
   - express_micro: Node.js/Express equivalent
   - openapi: OpenAPI 3.0 specs
   - docker: Docker Compose setups
   - terraform: AWS infrastructure as code
```

**4. Core Components** (Complete rewrite)
```markdown
## Core Components (All Implemented)

**CLI** (`src/dazzle/cli.py`):
- init, clone, demo: Project creation
- validate, lint: DSL validation
- build: Artifact generation
- inspect: NEW - Module interfaces and pattern analysis
- analyze-spec: LLM-powered spec analysis
- example: Build built-in examples

**Core Engine** (`src/dazzle/core/`):
- `manifest.py`: dazzle.toml loading
- `fileset.py`: DSL file discovery
- `dsl_parser.py`: Complete DSL parser
- `ir.py`: Full IR type system with Pydantic
- `linker.py` + `linker_impl.py`: Module merging and resolution
- `lint.py`: Comprehensive validation rules
- `errors.py`: Rich error types with context
- `patterns.py`: CRUD, integration, experience pattern detection

**Stacks** (`src/dazzle/stacks/`):
- Each stack is self-contained
- Base system provides common hooks and utilities
- Extensible plugin architecture

**LLM Integration** (`src/dazzle/llm/`):
- SpecAnalyzer: Parse natural language requirements
- DSLGenerator: Generate DSL from specs
- Interactive Q&A for clarifications
- Cost estimation and safety checks

**LSP Server** (`src/dazzle/lsp/`):
- Real-time diagnostics
- Hover information
- Go-to-definition
- Auto-completion
- Signature help
```

**5. Common Development Commands** (Update with new commands)
```bash
# NEW: Inspect module structure and patterns
dazzle inspect
dazzle inspect --patterns --types
dazzle inspect --no-interfaces  # Just patterns

# NEW: Analyze natural language specs
dazzle analyze-spec SPEC.md
dazzle analyze-spec SPEC.md --generate-dsl

# Project lifecycle (updated)
dazzle init                          # Or init --from simple_task
dazzle validate                      # Full validation with use checks
dazzle lint --strict                 # Extended lint rules
dazzle build --stack django_micro_modular
dazzle build --stack openapi,docker  # Multiple stacks
```

**6. Development Guidelines** (Add new section)
```markdown
## Development Guidelines

### Adding New Stacks
Each stack must:
1. Subclass BaseBackend
2. Implement generate(appspec, output_dir)
3. Provide StackCapabilities
4. Register in stacks/__init__.py
5. Add tests in tests/unit/test_backends.py
6. Document in docs/CAPABILITIES_MATRIX.md

### Extending the DSL
Changes require updates to:
1. docs/DAZZLE_DSL_REFERENCE_0_1.md
2. docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf
3. src/dazzle/core/dsl_parser.py
4. src/dazzle/core/ir.py (if new IR types)
5. Tests in tests/unit/test_parser.py

### Code Quality Standards
- All code uses ruff for linting/formatting
- Type hints enforced by mypy
- Tests required for new features
- Documentation updated with code
```

**7. Examples** (Update)
```markdown
## Examples

DAZZLE includes complete example projects:

**simple_task** (`examples/simple_task/`):
- Single entity (Task) with CRUD
- 4 surfaces (list, detail, create, edit)
- Perfect starter project
- Generates working Django or Express app

**support_tickets** (`examples/support_tickets/`):
- Multi-entity system (User, Ticket, Comment)
- Entity relationships (foreign keys)
- Multiple surfaces and experiences
- Integration examples
- Production-like complexity

Try them:
```bash
dazzle clone simple_task
dazzle clone support_tickets --stack django_next
```

**8. Documentation** (Update all links)
```markdown
## Documentation

**Core Documentation** (`docs/`):
- README.md: Project overview and quick start
- DAZZLE_DSL_REFERENCE_0_1.md: Complete DSL syntax
- DAZZLE_DSL_GRAMMAR_0_1.ebnf: Formal grammar
- DAZZLE_IR_0_1.md: IR structure and examples
- DAZZLE_EXAMPLES_0_1.dsl: Additional examples
- CAPABILITIES_MATRIX.md: What DAZZLE can do
- vscode_extension_user_guide.md: VS Code integration

**Development Documentation** (`dev_docs/`):
- development/stages/: Stage 1-7 completion reports
- releases/: Release summaries and notes
- features/: Feature specifications
- llm/: LLM integration documentation

**Testing** (`tests/`):
- unit/: Component tests (IR, parser, linker, stacks)
- integration/: End-to-end pipeline tests
- llm/: LLM integration tests
- fixtures/: Test data and examples
```

#### Acceptance Criteria
- [ ] No "to be implemented" language remains
- [ ] All actual features documented
- [ ] New commands (inspect, analyze-spec) included
- [ ] Accurate stage completion status
- [ ] Stack list complete and correct
- [ ] Code examples work as-is

---

### Task 1.2: Create CAPABILITIES_MATRIX.md

**Time**: 3 hours
**Files**: `docs/CAPABILITIES_MATRIX.md` (NEW)

#### Purpose
Single source of truth for "What can DAZZLE do?"

#### Structure

```markdown
# DAZZLE Capabilities Matrix

## DSL Constructs (What You Can Define)

### Entities ✅ Complete
**Status**: Fully implemented, production-ready
**Generates**: Database models, API endpoints, admin interfaces

**Supported Features**:
| Feature | Django | Express | OpenAPI | Terraform |
|---------|--------|---------|---------|-----------|
| Fields (str, int, etc.) | ✅ | ✅ | ✅ | N/A |
| Primary keys | ✅ | ✅ | ✅ | N/A |
| Foreign keys (ref) | ✅ | ✅ | ✅ | N/A |
| Unique constraints | ✅ | ✅ | ✅ | N/A |
| Indexes | ✅ | ✅ | ❌ | N/A |
| Auto timestamps | ✅ | ✅ | ✅ | N/A |
| Enum fields | ✅ | ✅ | ✅ | N/A |

**Example**:
```dsl
entity User "User":
  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  role: enum[admin,user]=user
  created_at: datetime auto_add
```

**Generates** (Django):
- `models.py` with User model
- Database migration
- Admin interface
- Serializers (if using django_api)
- CRUD views

### Surfaces ✅ Complete
[... continue for each DSL construct ...]

## Stack Comparison

### Django Micro Modular ✅
**Best For**: Rapid prototyping, MVPs, internal tools
**Output**: Complete Django project with SQLite
**Setup Time**: 5 minutes to running app
**Deployment**: Heroku, Railway, PythonAnywhere

**What You Get**:
- ✅ Django models (entities → models.py)
- ✅ Django admin (auto-configured)
- ✅ Forms and views (surfaces → forms.py, views.py)
- ✅ Templates (professional styling)
- ✅ URL routing
- ✅ settings.py (production-ready)
- ✅ requirements.txt
- ✅ README with setup instructions
- ✅ Management commands
- ✅ Tests (pytest + Django)
- ✅ Post-build hooks (DB migration, admin creation)

[... continue for each stack ...]

## Feature Availability Matrix

| Feature | v0.1.0 | v0.2.0 | v2.0.0 |
|---------|--------|--------|--------|
| Core DSL Parsing | ✅ | ✅ | ✅ |
| Module System | ✅ | ✅ | ✅ |
| Type Validation | ✅ | ✅ | ✅ |
| Pattern Detection | ✅ | ✅ | ✅ |
| Django Stack | ✅ | ✅ | ✅ |
| Express Stack | ✅ | ✅ | ✅ |
| OpenAPI Stack | ✅ | ✅ | ✅ |
| Docker Stack | ✅ | ✅ | ✅ |
| Terraform Stack | ✅ | ✅ | ✅ |
| LLM Integration | ✅ | ✅ | ✅ |
| VS Code Extension | ✅ | ✅ | ✅ |
| Integration Actions | ⚠️ | ✅ | ✅ |
| Integration Syncs | ⚠️ | ✅ | ✅ |
| Export Control | ❌ | ❌ | ✅ |
| Port-Based Composition | ❌ | ❌ | ✅ |
| Formal Verification | ❌ | ❌ | ✅ |

Legend:
- ✅ Fully implemented
- ⚠️ Partial (functional but uses stubs)
- ❌ Not implemented
```

#### Content Sections
1. **DSL Constructs** - Every keyword with examples and stack support
2. **Stack Comparison** - Detailed feature matrix per stack
3. **Integration Features** - LLM, LSP, testing capabilities
4. **Version Roadmap** - What's in each version
5. **Limitations** - What DAZZLE can't do (yet)

#### Acceptance Criteria
- [ ] All 6 stacks documented
- [ ] All DSL constructs covered
- [ ] Accurate feature availability
- [ ] Examples for each feature
- [ ] Limitations clearly stated

---

### Task 1.3: Integrate VS Code Documentation

**Time**: 1 hour
**Files**: `README.md`, `docs/IDE_INTEGRATION.md` (NEW)

#### Changes to README.md

Add section after "Quick Start":

```markdown
## IDE Integration

### VS Code Extension

DAZZLE has a full-featured VS Code extension with real-time diagnostics:

```bash
# Install from VS Code Marketplace
code --install-extension dazzle.dazzle-vscode
```

**Features**:
- 🔴 Real-time error highlighting
- 💡 Hover documentation
- ⚡ Auto-completion
- 🔍 Go-to-definition
- ✨ Signature help
- 📊 Pattern detection warnings

See [VS Code Extension Guide](docs/vscode_extension_user_guide.md) for details.

### Language Server Protocol (LSP)

DAZZLE includes an LSP server that works with any LSP-compatible editor:

```bash
# LSP server installed automatically with dazzle
# Configure your editor to use: dazzle lsp
```

Supported editors: VS Code, Neovim, Emacs, Sublime Text

See [IDE Integration Guide](docs/IDE_INTEGRATION.md) for setup instructions.
```

#### Create docs/IDE_INTEGRATION.md

**Content**:
- LSP architecture overview
- VS Code extension features
- Configuration for other editors
- Troubleshooting
- Contributing to editor integrations

#### Acceptance Criteria
- [ ] README mentions VS Code extension
- [ ] IDE_INTEGRATION.md created
- [ ] Cross-links updated
- [ ] Installation instructions clear

---

### Task 1.4: Complete DAZZLE_IR_0_1.md

**Time**: 2 hours
**Files**: `docs/DAZZLE_IR_0_1.md`

#### Current State
11KB stub with high-level concepts only

#### Required Content

**1. Introduction** (existing, update)
- What the IR is
- Why it exists
- How it's used

**2. Type Hierarchy** (NEW - generate from ir.py)

For each IR type, document:
- Purpose
- Pydantic definition
- Field descriptions
- Example JSON
- Used by (parser, linker, stacks)

Example format:
```markdown
### FieldSpec

**Location**: `src/dazzle/core/ir.py:80-115`

**Purpose**: Represents a single field in an entity or foreign model

**Definition**:
```python
class FieldSpec(BaseModel):
    name: str
    type: FieldType
    modifiers: List[FieldModifier] = Field(default_factory=list)
    default: Optional[Union[str, int, float, bool]] = None

    class Config:
        frozen = True
```

**Fields**:
- `name`: Field identifier (snake_case)
- `type`: Field type specification (FieldType)
- `modifiers`: List of modifiers (required, pk, unique, etc.)
- `default`: Optional default value

**Properties**:
- `is_required`: Check if field is required
- `is_primary_key`: Check if field is primary key
- `is_unique`: Check if field has unique constraint

**Example JSON**:
```json
{
  "name": "email",
  "type": {
    "kind": "email"
  },
  "modifiers": ["required", "unique"],
  "default": null
}
```

**Used By**:
- Parser: Creates from DSL field declarations
- Linker: Validates field types and references
- Stacks: Maps to target language types
```

**3. IR Flow** (NEW)
```markdown
## IR Flow Through DAZZLE

1. **DSL Files** → Parser
   - `dsl_parser.py` reads .dsl files
   - Creates ModuleFragment per file

2. **ModuleFragment** → Linker
   - `linker.py` merges fragments
   - Resolves dependencies
   - Validates references

3. **AppSpec** → Stacks
   - Complete, validated application specification
   - Passed to stack generators
   - Immutable (frozen=True)

4. **AppSpec** → Generated Code
   - Each stack interprets IR
   - Generates framework-specific code
   - No re-parsing needed
```

**4. Immutability** (NEW)
```markdown
## Why IR is Immutable

All IR types use `frozen=True` in Pydantic config:

**Benefits**:
- Thread-safe (can parallelize stack generation)
- Cacheable (hash-based deduplication)
- Predictable (no accidental mutations)
- Debuggable (state doesn't change)

**Implications**:
- Create new instances instead of modifying
- Use `model_copy(update={...})` for variations
- Linker creates new AppSpec, doesn't mutate fragments
```

#### Generation Strategy
1. Extract type definitions from ir.py
2. Generate markdown per type (can be scripted)
3. Add examples and usage notes manually
4. Add diagrams (optional but nice)

#### Acceptance Criteria
- [ ] All IR types documented
- [ ] JSON examples for each type
- [ ] Flow diagrams
- [ ] Immutability explained
- [ ] Cross-referenced with actual code

---

## Phase 2: Fix Test Suite 🟡

**Priority**: Before v0.2 Development
**Estimated Time**: 4-5 hours
**Impact**: HIGH - Enables confident development

### Task 2.1: Fix Test Collection Errors

**Time**: 2 hours
**Files**: Multiple test files, possibly `pyproject.toml` or `setup.py`

#### Current Problem
```bash
$ pytest tests/ --collect-only
============================= test session starts ==============================
collected 59 items / 3 errors
```

#### Investigation Steps
1. Run pytest with verbose errors:
   ```bash
   pytest tests/ --collect-only -vv
   ```

2. Identify which 3 tests are failing to collect

3. Check for common causes:
   - Pydantic v2 migration (class-based Config → ConfigDict)
   - Missing dependencies
   - Import errors
   - Circular dependencies

#### Expected Fixes

**If Pydantic v2 issue**:
```python
# Old (deprecated):
class MyModel(BaseModel):
    class Config:
        frozen = True

# New:
from pydantic import BaseModel, ConfigDict

class MyModel(BaseModel):
    model_config = ConfigDict(frozen=True)
```

**If dependency issue**:
- Pin versions in requirements.txt or pyproject.toml
- Check for conflicting versions

**If import issue**:
- Fix circular imports
- Update __init__.py files
- Check relative vs absolute imports

#### Acceptance Criteria
- [ ] All tests collect successfully
- [ ] `pytest tests/ --collect-only` shows 0 errors
- [ ] Test count matches expected (59+)
- [ ] CI passes

---

### Task 2.2: Move Quick Wins Tests

**Time**: 15 minutes
**Files**: `dev_docs/test_quick_wins.py` → `tests/unit/test_quick_wins.py`

#### Steps
1. Move file to proper location
2. Update imports if needed
3. Integrate with pytest
4. Add to test discovery

#### Changes Required

**File Location**:
```bash
mv dev_docs/test_quick_wins.py tests/unit/test_quick_wins.py
```

**Update Shebang** (remove or comment):
```python
#!/usr/bin/env python3  # Remove this
```

**Update Imports**:
```python
# Old:
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# New (if needed):
# pytest handles paths automatically
```

**Update Main Block**:
```python
# Old:
if __name__ == "__main__":
    sys.exit(main())

# New (pytest style):
# Tests discovered automatically, no main() needed
```

#### Acceptance Criteria
- [ ] File in tests/unit/
- [ ] Pytest discovers tests
- [ ] All 3 tests pass
- [ ] Integrated with CI

---

### Task 2.3: Add Missing Test Coverage

**Time**: 2 hours
**Files**: `tests/unit/test_cli.py`, `tests/unit/test_linker.py`

#### 2.3.1: Test `inspect` Command

**Add to**: `tests/unit/test_cli.py`

```python
def test_inspect_command_interfaces(runner, tmp_project):
    """Test inspect command shows module interfaces."""
    result = runner.invoke(app, ["inspect", "--no-patterns"])
    assert result.exit_code == 0
    assert "Module Interfaces" in result.output
    assert "module:" in result.output
    assert "exports:" in result.output


def test_inspect_command_patterns(runner, tmp_project):
    """Test inspect command shows detected patterns."""
    result = runner.invoke(app, ["inspect", "--no-interfaces"])
    assert result.exit_code == 0
    assert "CRUD Patterns" in result.output
    assert "Integration Patterns" in result.output


def test_inspect_command_types(runner, tmp_project):
    """Test inspect command shows type catalog."""
    result = runner.invoke(app, ["inspect", "--types"])
    assert result.exit_code == 0
    assert "Type Catalog" in result.output


def test_inspect_command_all(runner, tmp_project):
    """Test inspect command shows all information."""
    result = runner.invoke(app, ["inspect"])
    assert result.exit_code == 0
    # Should have all sections
    assert "Module Interfaces" in result.output
    assert "CRUD Patterns" in result.output
```

#### 2.3.2: Test Module Access Validation

**Add to**: `tests/unit/test_linker.py`

```python
def test_module_access_validation_enforces_use():
    """Test that modules must declare dependencies via use."""
    # Module 1 defines User
    module1 = ir.ModuleIR(
        name="app.users",
        file=Path("users.dsl"),
        fragment=ir.ModuleFragment(
            entities=[ir.EntitySpec(name="User", fields=[])]
        )
    )

    # Module 2 references User without using app.users
    module2 = ir.ModuleIR(
        name="app.posts",
        file=Path("posts.dsl"),
        uses=[],  # Missing: "app.users"
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="Post",
                    fields=[
                        ir.FieldSpec(
                            name="author",
                            type=ir.FieldType(
                                kind=ir.FieldTypeKind.REF,
                                ref_entity="User"
                            )
                        )
                    ]
                )
            ]
        )
    )

    symbols = build_symbol_table([module1, module2])
    errors = validate_module_access([module1, module2], symbols)

    assert len(errors) > 0
    assert "app.posts" in errors[0]
    assert "User" in errors[0]
    assert "app.users" in errors[0]
    assert "use app.users" in errors[0]


def test_module_access_validation_allows_declared_use():
    """Test that declared use statements are respected."""
    module1 = ir.ModuleIR(
        name="app.users",
        file=Path("users.dsl"),
        fragment=ir.ModuleFragment(
            entities=[ir.EntitySpec(name="User", fields=[])]
        )
    )

    module2 = ir.ModuleIR(
        name="app.posts",
        file=Path("posts.dsl"),
        uses=["app.users"],  # Properly declared
        fragment=ir.ModuleFragment(
            entities=[
                ir.EntitySpec(
                    name="Post",
                    fields=[
                        ir.FieldSpec(
                            name="author",
                            type=ir.FieldType(
                                kind=ir.FieldTypeKind.REF,
                                ref_entity="User"
                            )
                        )
                    ]
                )
            ]
        )
    )

    symbols = build_symbol_table([module1, module2])
    errors = validate_module_access([module1, module2], symbols)

    assert len(errors) == 0  # Should pass validation
```

#### Acceptance Criteria
- [ ] inspect command tests added (4 tests)
- [ ] Module access validation tests added (2+ tests)
- [ ] All tests pass
- [ ] Test coverage report updated

---

## Phase 3: Implementation Polish 🟡

**Priority**: v0.2 Development
**Estimated Time**: 8-10 hours
**Impact**: MEDIUM - Improves real-world usage

### Task 3.1: Complete Integration Parsing

**Time**: 5 hours
**Files**: `src/dazzle/core/dsl_parser.py`, `tests/unit/test_parser.py`

#### Current Problem
Lines 580-611 create stub actions and syncs:
```python
action = ir.IntegrationAction(
    name=f"action_{len(actions)}",
    when_surface="stub",
    call_service="stub",
    call_operation="stub",
)
```

#### Required Implementation

**Parse action blocks**:
```dsl
integration agent_lookup:
  uses service agent_directory
  uses foreign AgentInfo

  action lookup_agent:
    when surface invoice_create
    call service agent_directory
    call operation /agents/search
    call mapping:
      vrn → form.vrn
    response foreign AgentInfo
    response entity Invoice
    response mapping:
      agent_id → entity.agent_id
      agent_name → entity.agent_name
```

**Parser should extract**:
- Action name
- when_surface
- call_service, call_operation
- call_mapping rules
- response_foreign_model, response_entity
- response_mapping rules

**Parse sync blocks**:
```dsl
  sync import_agents:
    mode: scheduled "0 2 * * *"
    from service agent_directory
    from operation /agents/list
    from foreign AgentInfo
    into entity Agent
    match rules:
      agent_id ↔ id
      name ↔ name
```

**Parser should extract**:
- Sync name
- mode (scheduled or event_driven)
- schedule (cron expression if scheduled)
- from_service, from_operation, from_foreign_model
- into_entity
- match_rules (bidirectional mappings)

#### Implementation Strategy

1. **Update integration block parser** (lines 560-650)
   - Parse action: blocks
   - Parse sync: blocks
   - Extract mappings
   - Create proper IR objects (not stubs)

2. **Add mapping parser** (new function)
   ```python
   def _parse_mapping_rules(lines: List[str]) -> List[ir.MappingRule]:
       """Parse mapping rules like 'vrn → form.vrn'."""
       ...
   ```

3. **Add match rules parser** (new function)
   ```python
   def _parse_match_rules(lines: List[str]) -> List[ir.MatchRule]:
       """Parse match rules like 'agent_id ↔ id'."""
       ...
   ```

4. **Update tests**
   - Add test DSL files with full integration blocks
   - Test action parsing
   - Test sync parsing
   - Test mapping extraction

#### Acceptance Criteria
- [ ] Actions parse correctly (no stubs)
- [ ] Syncs parse correctly (no stubs)
- [ ] Mappings extracted accurately
- [ ] Match rules parsed
- [ ] Tests cover all cases
- [ ] Example integration blocks work end-to-end

---

### Task 3.2: Fix Code Quality Issues

**Time**: 2 hours
**Files**: Various generator files, deployment configs

#### 3.2.1: Remove/Implement TODOs in Generated Tests

**Files**: `src/dazzle/stacks/django_micro_modular/generators/tests.py`

**Options**:
1. **Remove TODOs** - Just delete the comment lines
2. **Implement tests** - Generate actual test code

**Recommendation**: Remove TODOs for v0.2
- Generated tests are basic but functional
- Users can add advanced tests themselves
- TODOs confuse users ("is this broken?")

**Changes**:
```python
# Remove lines like:
'# TODO: Implement comprehensive form tests'
'# TODO: Implement comprehensive admin tests'

# Just generate basic test or remove entirely
```

#### 3.2.2: Change DEBUG Defaults

**Files**:
- `src/dazzle/stacks/django_api.py`
- `src/dazzle/stacks/django_micro_modular/generators/settings.py`
- `src/dazzle/stacks/docker.py`
- `src/dazzle/stacks/base/common_hooks.py`

**Changes**:
```python
# Old:
DEBUG = True
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# New:
DEBUG = False  # Production default
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
```

**Update Documentation**:
Add to generated README.md:
```markdown
## Development vs Production

### Development Mode
Set `DEBUG=True` in settings.py or environment:
```bash
export DEBUG=True
python manage.py runserver
```

### Production Mode (default)
DEBUG is False by default. Do not change in production!
```

#### 3.2.3: OpenAPI Security Schemes

**File**: `src/dazzle/stacks/openapi.py`

**Current**:
```python
def _build_security_schemes(self, spec: ir.AppSpec) -> Dict[str, Any]:
    """Build OpenAPI security schemes (placeholder for now)."""
    return {}
```

**New**:
```python
def _build_security_schemes(self, spec: ir.AppSpec) -> Dict[str, Any]:
    """Build OpenAPI security schemes from service auth profiles."""
    schemes = {}

    for service in spec.services:
        auth = service.auth_profile

        if auth.kind == ir.AuthKind.API_KEY_HEADER:
            schemes[f"{service.name}_api_key"] = {
                "type": "apiKey",
                "name": auth.options.get("header_name", "X-API-Key"),
                "in": "header"
            }

        elif auth.kind == ir.AuthKind.OAUTH2_PKCE:
            schemes[f"{service.name}_oauth2"] = {
                "type": "oauth2",
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": auth.options.get("auth_url"),
                        "tokenUrl": auth.options.get("token_url"),
                        "scopes": self._parse_scopes(auth.options.get("scopes", ""))
                    }
                }
            }

        # Add other auth types as needed

    return schemes


def _parse_scopes(self, scopes_str: str) -> Dict[str, str]:
    """Parse space-separated scopes into OpenAPI format."""
    if not scopes_str:
        return {}

    scopes = {}
    for scope in scopes_str.split():
        # Simple format: scope_name or scope_name:description
        if ":" in scope:
            name, desc = scope.split(":", 1)
            scopes[name] = desc
        else:
            scopes[scope] = f"Access to {scope}"

    return scopes
```

#### Acceptance Criteria
- [ ] No TODO comments in generated code
- [ ] DEBUG defaults to False
- [ ] Security schemes generated from auth profiles
- [ ] Documentation updated
- [ ] Tests pass

---

### Task 3.3: Add --version Flag

**Time**: 30 minutes
**Files**: `src/dazzle/cli.py`

#### Implementation

**Add version callback**:
```python
import platform
from importlib.metadata import version

def version_callback(value: bool) -> None:
    """Display version and environment information."""
    if value:
        dazzle_version = version("dazzle")
        python_version = platform.python_version()

        typer.echo(f"DAZZLE version {dazzle_version}")
        typer.echo(f"Python {python_version}")

        raise typer.Exit()


app = typer.Typer(
    help="DAZZLE – DSL-first app generator",
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit"
    ),
) -> None:
    """DAZZLE CLI main callback for global options."""
    pass
```

#### Test

**Add to** `tests/unit/test_cli.py`:
```python
def test_version_flag(runner):
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "DAZZLE version" in result.output
    assert "Python" in result.output
```

#### Acceptance Criteria
- [ ] `dazzle --version` works
- [ ] `dazzle -v` works
- [ ] Shows version and Python version
- [ ] Test added
- [ ] Documentation updated

---

## Phase 4: Developer Experience 🟢

**Priority**: When Convenient
**Estimated Time**: 3-4 hours
**Impact**: LOW but Professional

### Task 4.1: Add pyproject.toml

**Time**: 1 hour
**Files**: `pyproject.toml` (NEW)

#### Specification

**Create** `pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dazzle"
version = "0.1.0"
description = "Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Your Name", email = "you@example.com"},
]
keywords = ["dsl", "code-generation", "llm", "openapi"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "typer>=0.9.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "jinja2>=3.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-xdist>=3.3.0",
    "mypy>=1.5.0",
    "ruff>=0.1.0",
]

llm = [
    "anthropic>=0.25.0",
    "openai>=1.0.0",
]

lsp = [
    "pygls>=1.1.0",
]

[project.scripts]
dazzle = "dazzle.cli:main"

[project.urls]
Homepage = "https://github.com/manwithacat/dazzle"
Documentation = "https://github.com/manwithacat/dazzle/tree/main/docs"
Repository = "https://github.com/manwithacat/dazzle"
Issues = "https://github.com/manwithacat/dazzle/issues"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
dazzle = ["**/*.j2", "**/*.yaml", "**/*.toml"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]  # Line too long (handled by formatter)
```

#### Migration Steps
1. Create pyproject.toml
2. Update setup.py to use pyproject.toml
3. Test installation: `pip install -e .`
4. Update documentation
5. Update CI/CD if needed

#### Acceptance Criteria
- [ ] pyproject.toml created
- [ ] `pip install -e .` works
- [ ] All dependencies specified
- [ ] Tool configurations included
- [ ] Compatible with existing setup.py

---

### Task 4.2: Add Pre-commit Hooks

**Time**: 30 minutes
**Files**: `.pre-commit-config.yaml` (NEW)

#### Specification

**Create** `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-PyYAML, types-toml]

  - repo: local
    hooks:
      - id: pytest-fast
        name: pytest-fast
        entry: pytest tests/unit -x
        language: system
        pass_filenames: false
        always_run: true
```

#### Installation Instructions

**Add to CONTRIBUTING.md**:
```markdown
## Pre-commit Hooks

We use pre-commit hooks to maintain code quality:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Hooks run automatically before each commit.
```

#### Acceptance Criteria
- [ ] `.pre-commit-config.yaml` created
- [ ] Hooks run successfully
- [ ] Documentation updated
- [ ] CI also runs same checks

---

### Task 4.3: Create CONTRIBUTING.md

**Time**: 1 hour
**Files**: `CONTRIBUTING.md` (NEW)

#### Structure

```markdown
# Contributing to DAZZLE

Thank you for your interest in contributing to DAZZLE!

## Development Setup

### Prerequisites
- Python 3.11 or later
- Git

### Clone and Install
```bash
git clone https://github.com/manwithacat/dazzle.git
cd dazzle
pip install -e ".[dev,llm,lsp]"
```

### Verify Setup
```bash
dazzle --version
pytest tests/
```

## Code Style

We use:
- **ruff** for linting and formatting
- **mypy** for type checking
- **pytest** for testing

### Format Code
```bash
ruff format src/ tests/
ruff check src/ tests/ --fix
```

### Type Check
```bash
mypy src/dazzle
```

### Run Tests
```bash
# All tests
pytest tests/

# Specific test
pytest tests/unit/test_parser.py

# With coverage
pytest tests/ --cov=dazzle --cov-report=html
```

## Making Changes

### 1. Create a Branch
```bash
git checkout -b feature/my-feature
```

### 2. Make Changes
- Write code
- Add tests
- Update documentation
- Run tests and linting

### 3. Commit
```bash
git add .
git commit -m "feat: add my feature"
```

We follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Tests
- `refactor`: Code refactoring
- `chore`: Maintenance

### 4. Submit PR
- Push to your fork
- Open PR on GitHub
- Describe changes
- Wait for review

## Adding New Features

### New Stack
See `docs/STACK_DEVELOPMENT.md` (to be created)

### New DSL Construct
1. Update `docs/DAZZLE_DSL_REFERENCE_0_1.md`
2. Update `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf`
3. Update `src/dazzle/core/dsl_parser.py`
4. Update `src/dazzle/core/ir.py` if needed
5. Add tests
6. Update stacks to support new construct

### Bug Fixes
1. Add failing test
2. Fix bug
3. Verify test passes
4. Submit PR

## Testing Guidelines

- All new code must have tests
- Tests should be in `tests/unit/` or `tests/integration/`
- Use fixtures from `tests/conftest.py`
- Aim for >80% coverage

## Documentation

- Update README.md for user-facing changes
- Update docs/ for detailed documentation
- Add docstrings to all public functions
- Include examples in docstrings

## Questions?

- Open an issue for discussion
- Check existing issues first
- Join discussions on GitHub

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
```

#### Acceptance Criteria
- [ ] CONTRIBUTING.md created
- [ ] Clear setup instructions
- [ ] Code style documented
- [ ] PR process explained
- [ ] Linked from README.md

---

### Task 4.4: Build Homebrew Bottles

**Time**: 1 hour (mostly waiting)
**Files**: Homebrew tap repository

#### Process

1. **Use GitHub Actions** (already created):
   - Workflow in `homebrew-tap/.github/workflows/bottle-build.yml`
   - Triggers on release
   - Builds for arm64 and x86_64

2. **Manual Process** (if needed):
   ```bash
   # On Mac (arm64)
   brew install --build-bottle dazzle
   brew bottle dazzle

   # Repeat on Intel Mac or use Docker
   ```

3. **Update Formula**:
   - Add bottle stanzas
   - Update SHA256s
   - Test installation

4. **Verify**:
   ```bash
   brew reinstall dazzle
   # Should take 30 seconds, not 15 minutes
   ```

#### Acceptance Criteria
- [ ] Bottles built for both architectures
- [ ] Formula updated with bottle info
- [ ] Installation time reduced to ~30 seconds
- [ ] Documented in release notes

---

## Summary Timeline

### Immediate (This Week)
- **Day 1-2**: Phase 1 (Documentation) - 6-8 hours
  - Rewrite CLAUDE.md
  - Create CAPABILITIES_MATRIX.md
  - Integrate VS Code docs
  - Complete DAZZLE_IR_0_1.md

### Before v0.2 (Next Week)
- **Day 3-4**: Phase 2 (Tests) - 4-5 hours
  - Fix test collection errors
  - Move quick wins tests
  - Add missing test coverage

### v0.2 Development (Following Weeks)
- **Week 2**: Phase 3 (Implementation) - 8-10 hours
  - Complete integration parsing
  - Fix code quality issues
  - Add --version flag

### Polish (As Time Permits)
- **Week 3**: Phase 4 (Dev Experience) - 3-4 hours
  - Add pyproject.toml
  - Add pre-commit hooks
  - Create CONTRIBUTING.md
  - Build Homebrew bottles

---

## Success Metrics

### Phase 1 Complete When:
- [ ] AI assistants get accurate information from CLAUDE.md
- [ ] New contributors understand capabilities
- [ ] VS Code features discoverable
- [ ] IR fully documented

### Phase 2 Complete When:
- [ ] All tests collect successfully
- [ ] Test coverage includes new features
- [ ] CI consistently green

### Phase 3 Complete When:
- [ ] Integration blocks fully parse
- [ ] No stub implementations
- [ ] Generated code production-ready
- [ ] --version works

### Phase 4 Complete When:
- [ ] Modern Python tooling supported
- [ ] Contributing process clear
- [ ] Code quality automated
- [ ] Homebrew install fast

---

**End of Specifications**
