# DAZZLE MCP Server Distribution Strategy

**Created**: 2025-11-27
**Status**: Planning
**Priority**: High

## Problem Statement

When users create a new DAZZLE project using `dazzle init` or `dazzle clone`, and then open Claude Code in that directory, the DAZZLE MCP server is not automatically available. This creates a poor user experience where:

1. MCP tools are not discoverable
2. Users must manually configure each project
3. No consistent workflow across projects
4. The powerful MCP integration is effectively hidden

## Current State

### What We Have

1. **MCP Server Implementation** (`src/dazzle/mcp/`)
   - Complete server with tools, resources, and prompts
   - Dev mode detection (Dazzle repo vs user project)
   - Project-specific tools (validate, build, inspect, etc.)
   - Documentation resources (glossary, DSL reference, etc.)
   - Entry point: `python -m dazzle.mcp`

2. **Distribution Channels**
   - Homebrew formula (production)
   - PyPI package (ready)
   - Development install (`pip install -e .`)

3. **Project Scaffolding** (`dazzle init`)
   - Creates `dazzle.toml`
   - Creates `dsl/` directory
   - Creates `.claude/CLAUDE.md` with instructions
   - Does NOT configure MCP server

### What's Missing

1. **No MCP server registration** in Claude Code config
2. **No auto-discovery mechanism** for new projects
3. **No CLI command** to setup MCP integration
4. **No Homebrew post-install hooks** to register MCP server
5. **No project-local MCP config** generation

## Proposed Solution: Multi-Layered Approach

### Layer 1: Global MCP Server Registration (Homebrew/PyPI Install)

**Goal**: Register DAZZLE MCP server globally when installed via Homebrew or pip.

**Implementation**:

1. **Post-Install Hook** (Homebrew formula)
   ```ruby
   def post_install
     # Generate MCP server config for Claude Code
     mcp_config = {
       "mcpServers" => {
         "dazzle" => {
           "command" => "#{opt_libexec}/bin/python",
           "args" => ["-m", "dazzle.mcp"],
           "env" => {}
         }
       }
     }

     # Write to Claude Code config directory
     claude_config = Pathname.new(ENV["HOME"]) / ".claude" / "mcp_servers.json"
     claude_config.dirname.mkpath

     # Merge with existing config if present
     existing = claude_config.exist? ? JSON.parse(claude_config.read) : {}
     existing["mcpServers"] ||= {}
     existing["mcpServers"]["dazzle"] = mcp_config["mcpServers"]["dazzle"]

     claude_config.write(JSON.pretty_generate(existing))

     ohai "DAZZLE MCP server registered with Claude Code"
   end
   ```

2. **Python Post-Install Script** (PyPI/pip install)
   - Create `scripts/post_install.py`
   - Run via setuptools `post_install` hook
   - Register MCP server in `~/.claude/mcp_servers.json`

3. **CLI Command**: `dazzle mcp-setup`
   - Manually register/update MCP server config
   - Useful for troubleshooting or custom installs
   - Shows current MCP server status

**Pros**:
- One-time setup
- Works globally for all DAZZLE projects
- Transparent to users

**Cons**:
- Requires Claude Code to support global MCP server registry
- May need coordination with Anthropic on config location

### Layer 2: Project-Local MCP Configuration

**Goal**: Each DAZZLE project can have project-specific MCP configuration.

**Implementation**:

1. **Update `dazzle init`** to create `.claude/mcp.json`:
   ```json
   {
     "mcpServers": {
       "dazzle": {
         "command": "dazzle",
         "args": ["mcp", "--working-dir", "${projectDir}"],
         "env": {}
       }
     }
   }
   ```

2. **New CLI Subcommand**: `dazzle mcp`
   - Runs MCP server with optional `--working-dir`
   - Wrapper around `python -m dazzle.mcp`
   - Example: `dazzle mcp --working-dir /path/to/project`

3. **Update CLI entry point** (`pyproject.toml`):
   ```toml
   [project.scripts]
   dazzle = "dazzle.cli:main"
   dazzle-mcp = "dazzle.mcp.__main__:main"
   ```

**Pros**:
- Project-specific configuration
- Works with Claude Code's project-scoped MCP server support
- No global state modifications

**Cons**:
- Requires Claude Code to support `.claude/mcp.json`
- Every project needs config file

### Layer 3: Dynamic Discovery via .claude/CLAUDE.md

**Goal**: Instruct Claude Code to use MCP server via instructions in CLAUDE.md.

**Implementation**:

Update `.claude/CLAUDE.md` template in `dazzle init`:

```markdown
# DAZZLE Project

This project uses the DAZZLE MCP server for enhanced tooling.

## MCP Server Setup

### Automatic (Recommended)
If you installed DAZZLE via Homebrew or pip, the MCP server should be automatically available.

### Manual Setup
If the MCP tools are not available, add this to your Claude Code config:

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
You should have access to these tools:
- `validate_dsl` - Validate project DSL files
- `build` - Generate code from DSL
- `inspect_entity` - Inspect entity definitions
- `lookup_concept` - Look up DSL concepts
- And more...

Try asking: "What DAZZLE tools do you have access to?"
```

**Pros**:
- Works immediately
- No infrastructure changes needed
- Provides fallback instructions

**Cons**:
- Requires user awareness
- Not truly automatic

### Layer 4: MCP Server as Separate Package

**Goal**: Distribute MCP server as standalone package for easy installation.

**Implementation**:

1. **Create `dazzle-mcp` package**:
   ```
   dazzle-mcp/
   ├── pyproject.toml
   ├── src/
   │   └── dazzle_mcp/
   │       ├── __init__.py
   │       ├── __main__.py  # MCP server entry point
   │       └── server.py     # Import from dazzle.mcp
   └── scripts/
       └── install_mcp.py    # Auto-register with Claude Code
   ```

2. **Installation**:
   ```bash
   # Install MCP server globally
   pip install dazzle-mcp

   # Or via pipx for isolated install
   pipx install dazzle-mcp

   # Auto-registers with Claude Code during install
   ```

3. **Update Homebrew formula** to include MCP setup:
   ```ruby
   resource "dazzle-mcp" do
     # Include MCP server dependencies
   end
   ```

**Pros**:
- Clean separation of concerns
- Easy to install just MCP server
- Can version independently

**Cons**:
- Additional package to maintain
- May duplicate code

## Recommended Implementation Plan

### Phase 1: Quick Win (1-2 days)

**Goal**: Get MCP server working for existing users immediately.

1. **Add `dazzle mcp` CLI command**
   - Wrapper around `python -m dazzle.mcp`
   - Accepts `--working-dir` argument
   - Entry point: `dazzle-mcp = "dazzle.mcp.__main__:main"`

2. **Update `dazzle init` template**
   - Add `.claude/mcp.json` with project-local MCP config
   - Update `.claude/CLAUDE.md` with MCP instructions
   - Include verification steps

3. **Add `dazzle mcp-setup` command**
   - Manually register MCP server in user's Claude Code config
   - Detect config location (`~/.claude/`, `~/.config/claude-code/`)
   - Merge with existing MCP servers

4. **Documentation**
   - Update README with MCP setup instructions
   - Add MCP server user guide
   - Include troubleshooting section

**Deliverables**:
- ✅ `dazzle mcp` command
- ✅ `dazzle mcp-setup` command
- ✅ Updated `dazzle init` templates
- ✅ MCP server documentation

### Phase 2: Homebrew Integration (3-5 days)

**Goal**: Auto-register MCP server on Homebrew install.

1. **Update Homebrew formula**
   - Add `post_install` hook
   - Register MCP server in `~/.claude/mcp_servers.json`
   - Merge with existing servers

2. **Add uninstall hook**
   - Clean up MCP server registration
   - Optional: preserve user customizations

3. **Test installation flow**
   - Fresh install
   - Upgrade from previous version
   - Uninstall

4. **Update caveats**
   - Show MCP server status in install message
   - Provide manual setup instructions if auto-setup fails

**Deliverables**:
- ✅ Updated Homebrew formula with post-install
- ✅ Uninstall cleanup
- ✅ Installation testing

### Phase 3: PyPI Integration (2-3 days)

**Goal**: Auto-register MCP server on pip/pipx install.

1. **Add setup.py entry point** (if not using pyproject.toml)
   - Or use setuptools post-install hook

2. **Create post-install script**
   - Detect Claude Code config location
   - Register MCP server
   - Handle errors gracefully

3. **Test with different install methods**
   - `pip install dazzle`
   - `pipx install dazzle`
   - `uv pip install dazzle`
   - `pip install -e .` (dev mode)

4. **Documentation**
   - Update PyPI description
   - Include MCP setup in README

**Deliverables**:
- ✅ PyPI post-install script
- ✅ Multi-install-method testing
- ✅ Updated PyPI metadata

### Phase 4: Enhanced Developer Experience (Ongoing)

**Goal**: Make MCP integration seamless and delightful.

1. **Project initialization wizard**
   - Interactive `dazzle init --interactive`
   - Ask about MCP setup preferences
   - Configure Claude Code integration

2. **MCP server health check**
   - `dazzle mcp-check` - Verify MCP server is accessible
   - Show available tools and resources
   - Diagnose common issues

3. **Auto-update mechanism**
   - Detect when MCP server version doesn't match CLI
   - Prompt to re-register MCP server
   - Handle breaking changes gracefully

4. **IDE integration**
   - VS Code extension auto-registers MCP server
   - JetBrains plugin support
   - Generic editor instructions

**Deliverables**:
- ✅ `dazzle init --interactive`
- ✅ `dazzle mcp-check`
- ✅ Auto-update detection
- ✅ IDE integration guides

## Technical Implementation Details

### File Locations

**Claude Code Config Locations** (in priority order):
1. `~/.config/claude-code/mcp_servers.json` (Linux/Mac XDG)
2. `~/.claude/mcp_servers.json` (Mac/Unix legacy)
3. `~/Library/Application Support/Claude Code/mcp_servers.json` (Mac app)
4. `%APPDATA%\Claude Code\mcp_servers.json` (Windows)

**Project-Local Config**:
- `.claude/mcp.json` (project-specific MCP servers)
- `.claude/CLAUDE.md` (instructions and context)

### MCP Server Config Format

**Global Registration** (`~/.claude/mcp_servers.json`):
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/opt/homebrew/opt/dazzle/libexec/bin/python",
      "args": ["-m", "dazzle.mcp"],
      "env": {},
      "autoStart": true
    }
  }
}
```

**Project-Local Config** (`.claude/mcp.json`):
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"],
      "env": {},
      "autoStart": true
    }
  }
}
```

### CLI Command Structure

```python
# src/dazzle/cli.py

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

### Setup Module

```python
# src/dazzle/mcp/setup.py

import json
from pathlib import Path
from typing import Any


def get_claude_config_path() -> Path | None:
    """Find Claude Code config directory."""
    home = Path.home()

    # Try common locations
    candidates = [
        home / ".config" / "claude-code" / "mcp_servers.json",
        home / ".claude" / "mcp_servers.json",
        home / "Library" / "Application Support" / "Claude Code" / "mcp_servers.json",
    ]

    for path in candidates:
        if path.parent.exists():
            return path

    # Default to ~/.claude/
    default = home / ".claude" / "mcp_servers.json"
    default.parent.mkdir(parents=True, exist_ok=True)
    return default


def register_mcp_server(force: bool = False) -> bool:
    """Register DAZZLE MCP server in Claude Code config."""
    config_path = get_claude_config_path()
    if not config_path:
        return False

    # Detect Python executable
    import sys
    python_path = sys.executable

    # New MCP server config
    dazzle_config = {
        "command": python_path,
        "args": ["-m", "dazzle.mcp"],
        "env": {},
        "autoStart": True
    }

    # Load existing config
    if config_path.exists():
        existing = json.loads(config_path.read_text())
        if "dazzle" in existing.get("mcpServers", {}) and not force:
            print("DAZZLE MCP server already registered (use --force to overwrite)")
            return True
    else:
        existing = {"mcpServers": {}}

    # Add/update DAZZLE server
    existing.setdefault("mcpServers", {})["dazzle"] = dazzle_config

    # Write back
    config_path.write_text(json.dumps(existing, indent=2))
    return True


def check_mcp_server() -> dict[str, Any]:
    """Check MCP server registration and availability."""
    config_path = get_claude_config_path()

    status = {
        "status": "not_registered",
        "registered": False,
        "config_path": str(config_path) if config_path else None,
        "tools": []
    }

    if not config_path or not config_path.exists():
        return status

    config = json.loads(config_path.read_text())
    if "dazzle" in config.get("mcpServers", {}):
        status["registered"] = True
        status["status"] = "registered"

        # Try to enumerate tools (if possible)
        try:
            from dazzle.mcp.tools import get_tool_list
            status["tools"] = get_tool_list()
        except Exception:
            pass

    return status
```

### Project Init Template Updates

```python
# src/dazzle/cli.py - init command

def _create_claude_config(project_root: Path):
    """Create .claude/ configuration."""
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)

    # Create CLAUDE.md with instructions
    # (existing code)

    # Create mcp.json for project-local MCP server
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

## Testing Strategy

### Unit Tests

1. **Config Detection**
   - Test `get_claude_config_path()` on different platforms
   - Mock file system for different scenarios

2. **Config Merging**
   - Test merging with existing MCP servers
   - Test overwrite with `--force`

3. **CLI Commands**
   - Test `dazzle mcp` with different working directories
   - Test `dazzle mcp-setup` with various config states
   - Test `dazzle mcp-check` output

### Integration Tests

1. **Fresh Install**
   - Install via Homebrew
   - Verify MCP server registration
   - Create new project
   - Verify Claude Code can connect

2. **Upgrade Path**
   - Install old version
   - Upgrade to new version with MCP support
   - Verify config is updated

3. **Multi-Project**
   - Create multiple DAZZLE projects
   - Verify each has correct project-local config
   - Verify global config works for all

### Manual Testing

1. **User Journey**
   - Fresh user installs DAZZLE
   - Runs `dazzle init my-project`
   - Opens Claude Code
   - Verifies MCP tools available
   - Uses tools to validate/build project

2. **Error Cases**
   - No write permissions to config directory
   - Conflicting MCP server names
   - Claude Code not installed
   - Multiple Claude Code installations

## Documentation Requirements

### User-Facing Docs

1. **README.md Updates**
   - Add "MCP Server Integration" section
   - Quick start with MCP
   - Troubleshooting

2. **MCP User Guide** (`docs/MCP_INTEGRATION.md`)
   - What is MCP?
   - Available tools and resources
   - Setup instructions (automatic and manual)
   - Using MCP tools with Claude Code
   - Advanced configuration

3. **FAQ**
   - "MCP tools not showing up"
   - "How to update MCP server config"
   - "Can I customize MCP server behavior?"

### Developer Docs

1. **MCP Architecture** (`dev_docs/mcp_architecture.md`)
   - Server implementation details
   - Tool registration system
   - Resource providers
   - Prompt templates

2. **MCP Development Guide** (`dev_docs/mcp_development.md`)
   - Adding new tools
   - Adding new resources
   - Testing MCP server
   - Debugging MCP connections

## Success Metrics

### Quantitative

- **Installation Success Rate**: >95% of users have MCP server auto-registered
- **First-Use Success**: >90% of users can use MCP tools immediately after install
- **Support Tickets**: <5% of tickets related to MCP setup issues

### Qualitative

- Users discover MCP tools without reading docs
- MCP integration feels "magical" and seamless
- Zero friction from install to first MCP tool use
- Consistent experience across installation methods

## Risks and Mitigations

### Risk 1: Claude Code Config Location Changes

**Probability**: Medium
**Impact**: High

**Mitigation**:
- Support multiple config locations
- Version detection for Claude Code
- Fallback to documented manual setup

### Risk 2: Permission Issues Writing Config

**Probability**: Low
**Impact**: Medium

**Mitigation**:
- Detect permission errors early
- Provide clear error messages
- Offer alternative setup methods

### Risk 3: MCP Server Version Mismatch

**Probability**: Medium
**Impact**: Medium

**Mitigation**:
- Version the MCP server protocol
- Auto-detect version mismatches
- Prompt users to update

### Risk 4: Breaking Changes in MCP Protocol

**Probability**: Low
**Impact**: High

**Mitigation**:
- Stay updated with MCP SDK changes
- Test against MCP SDK releases
- Version our MCP server implementation

## Future Enhancements

### 1. MCP Server Marketplace Integration

If Claude Code adds an MCP server marketplace, publish DAZZLE there.

### 2. Project Templates with MCP Configs

Include MCP configs in all example projects and templates.

### 3. MCP Server Analytics

Track which MCP tools are most used (privacy-preserving).

### 4. Custom MCP Tool Registry

Allow users to add project-specific MCP tools via DSL:

```dsl
mcp_tool generate_migration:
  description: "Generate database migration from entity changes"
  parameters:
    entity: str required
  implementation: scripts/generate_migration.py
```

## Appendix

### A. Example Homebrew Post-Install

```ruby
def post_install
  require "json"

  # Paths to try
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

### B. PyPI setup.py Post-Install

```python
# setup.py or scripts/post_install.py

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
    post_install()
```

## Conclusion

This strategy provides a comprehensive, multi-layered approach to MCP server distribution that:

1. **Works immediately** (Layer 3 - documentation)
2. **Scales to automation** (Layers 1-2 - installation hooks)
3. **Provides manual fallbacks** (CLI commands)
4. **Future-proofs** (separate package option)

The recommended implementation plan starts with quick wins and progressively adds automation, ensuring users have a great experience at every stage.
