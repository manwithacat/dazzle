# MCP CLI Commands Implementation Session

**Date**: 2025-11-27
**Duration**: ~2 hours
**Phase**: Phase 0 - MCP Server Distribution (Task 0.1)
**Status**: ✅ Task 0.1 Completed

---

## Objective

Implement CLI commands for managing the DAZZLE MCP server, enabling users to easily register, check status, and run the MCP server.

## Completed Work

### 1. Created `src/dazzle/mcp/setup.py` ✅

**Purpose**: MCP server setup and configuration utilities

**Key Functions**:
- `get_claude_config_path()` - Find Claude Code config directory
  - Tries multiple common locations: `~/.config/claude-code/`, `~/.claude/`, `~/Library/Application Support/Claude Code/`
  - Creates default directory if none exist

- `register_mcp_server(force=False)` - Register MCP server in Claude Code config
  - Detects Python executable automatically
  - Merges with existing MCP servers (doesn't overwrite)
  - Supports `--force` to overwrite existing config

- `check_mcp_server()` - Verify registration and availability
  - Returns status dict with registration status, config path, server command
  - Enumerates available tools

### 2. Updated `src/dazzle/mcp/tools.py` ✅

**Added**:
- `get_project_tools()` - Export function for setup module
- Returns list of tool names for status checking

### 3. Added Three New CLI Commands ✅

**File**: `src/dazzle/cli.py` (lines 2830-2931)

#### `dazzle mcp`
Run DAZZLE MCP server with optional working directory

**Usage**:
```bash
dazzle mcp                           # Current directory
dazzle mcp --working-dir /path/to/project
```

**Features**:
- Async server execution
- Graceful keyboard interrupt handling
- Error reporting

#### `dazzle mcp-setup`
Register DAZZLE MCP server with Claude Code

**Usage**:
```bash
dazzle mcp-setup          # Register
dazzle mcp-setup --force  # Overwrite existing
```

**Output**:
```
Registering MCP server at: ~/.claude/mcp_servers.json
✅ DAZZLE MCP server registered successfully

Next steps:
  1. Restart Claude Code
  2. Open a DAZZLE project
  3. Ask Claude: "What DAZZLE tools do you have access to?"
```

**Features**:
- Detects Claude Code config location
- Creates config if it doesn't exist
- Merges with existing servers
- Provides clear next steps

#### `dazzle mcp-check`
Check DAZZLE MCP server status

**Usage**:
```bash
dazzle mcp-check
```

**Output**:
```
DAZZLE MCP Server Status
==================================================
Status:        registered
Registered:    ✓ Yes
Config:        /Users/james/.claude/mcp_servers.json
Command:       /path/to/python -m dazzle.mcp

Available Tools (9):
  • analyze_patterns
  • build
  • find_examples
  • inspect_entity
  • inspect_surface
  • lint_project
  • list_modules
  • lookup_concept
  • validate_dsl
```

**Features**:
- Shows registration status
- Displays config location
- Lists server command
- Enumerates available tools
- Suggests `dazzle mcp-setup` if not registered

### 4. Updated `dazzle init` to Create `.claude/mcp.json` ✅

**File**: `src/dazzle/core/llm_context.py` (lines 618-631)

**Changes**:
- Modified `create_llm_instrumentation()` function
- Automatically creates `.claude/mcp.json` during project initialization
- Uses project-local MCP config format with `${projectDir}` variable

**Generated Config**:
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

### 5. Updated Example Project Templates ✅

**File**: `examples/simple_task/.claude/CLAUDE.md`

**Added**:
- MCP Server Integration section at top
- Automatic and manual setup instructions
- List of available MCP tools
- Suggestion to ask "What DAZZLE tools do you have access to?"

**Benefits**:
- New projects immediately inform Claude about MCP capabilities
- Users get clear setup instructions
- Fallback manual setup instructions provided

---

## Testing Results

### Test 1: `dazzle mcp-check` (Before Setup) ✅
```bash
$ python -m dazzle.cli mcp-check

DAZZLE MCP Server Status
==================================================
Status:        not_registered
Registered:    ✗ No
Config:        /Users/james/.claude/mcp_servers.json

💡 To register the MCP server, run: dazzle mcp-setup
```

**Result**: ✅ Correctly detects unregistered server

### Test 2: `dazzle mcp-setup` ✅
```bash
$ python -m dazzle.cli mcp-setup

Registering MCP server at: /Users/james/.claude/mcp_servers.json
✅ DAZZLE MCP server registered successfully

Next steps:
  1. Restart Claude Code
  2. Open a DAZZLE project
  3. Ask Claude: "What DAZZLE tools do you have access to?"
```

**Result**: ✅ Successfully registers server

**Verified Config**:
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/Users/james/.pyenv/versions/dazzle-dev/bin/python",
      "args": ["-m", "dazzle.mcp"],
      "env": {},
      "autoStart": true
    }
  }
}
```

### Test 3: `dazzle mcp-check` (After Setup) ✅
```bash
$ python -m dazzle.cli mcp-check

DAZZLE MCP Server Status
==================================================
Status:        registered
Registered:    ✓ Yes
Config:        /Users/james/.claude/mcp_servers.json
Command:       /Users/james/.pyenv/versions/dazzle-dev/bin/python -m dazzle.mcp

Available Tools (9):
  • analyze_patterns
  • build
  • find_examples
  • inspect_entity
  • inspect_surface
  • lint_project
  • list_modules
  • lookup_concept
  • validate_dsl
```

**Result**: ✅ Shows all tools correctly

### Test 4: `dazzle init` Creates MCP Config ✅
```bash
$ cd /tmp
$ dazzle init test-mcp-project --name test-project
$ ls -la test-mcp-project/.claude/

total 32
-rw-rw-rw-  CLAUDE.md
-rw-rw-rw-  mcp.json
-rw-rw-rw-  permissions.json
-rw-rw-rw-  PROJECT_CONTEXT.md
```

**Result**: ✅ `mcp.json` created successfully

**Verified Content**:
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

---

## Files Created/Modified

### New Files
1. `/Volumes/SSD/Dazzle/src/dazzle/mcp/setup.py` - MCP setup utilities
2. `/Volumes/SSD/Dazzle/dev_docs/mcp_distribution_strategy.md` - Complete strategy document
3. `/Volumes/SSD/Dazzle/dev_docs/roadmap_v0_3_0.md` - UI Semantic Layout roadmap
4. `/Volumes/SSD/Dazzle/dev_docs/sessions/2025-11-27_mcp_cli_implementation.md` - This file

### Modified Files
1. `/Volumes/SSD/Dazzle/src/dazzle/cli.py` - Added 3 MCP commands
2. `/Volumes/SSD/Dazzle/src/dazzle/mcp/tools.py` - Added `get_project_tools()` export
3. `/Volumes/SSD/Dazzle/src/dazzle/core/llm_context.py` - Added MCP config generation
4. `/Volumes/SSD/Dazzle/examples/simple_task/.claude/CLAUDE.md` - Added MCP section
5. `/Volumes/SSD/Dazzle/dev_docs/architecture/dazzle_ui_semantic_layout_spec_v1.md` - Enhanced with DAZZLE integration
6. `/Volumes/SSD/Dazzle/dev_docs/NEXT_STAGES_SPEC.md` - Added Phase 0 (MCP Distribution)

---

## Technical Decisions

### 1. Config Location Detection
**Decision**: Try multiple common locations in priority order
**Rationale**:
- Different OS versions and installations use different paths
- XDG standard on Linux: `~/.config/claude-code/`
- Legacy on Mac: `~/.claude/`
- Mac app: `~/Library/Application Support/Claude Code/`

### 2. Python Executable Detection
**Decision**: Use `sys.executable` to detect current Python
**Rationale**:
- Ensures MCP server uses same Python as CLI
- Works with virtualenvs, pyenv, and system Python
- No hardcoded paths

### 3. Config Merging Strategy
**Decision**: Merge with existing `mcpServers`, don't overwrite entire file
**Rationale**:
- Users may have other MCP servers registered
- Preserve existing configuration
- Require `--force` to overwrite DAZZLE-specific config

### 4. Project-Local vs Global Config
**Decision**: Support both with different use cases
**Rationale**:
- **Global** (`~/.claude/mcp_servers.json`): User runs `dazzle mcp-setup` once
- **Project-Local** (`.claude/mcp.json`): Auto-created by `dazzle init`, project-specific

### 5. `${projectDir}` Variable
**Decision**: Use `${projectDir}` placeholder in project-local config
**Rationale**:
- Claude Code substitutes this at runtime
- Makes config portable (project can be moved)
- No hardcoded absolute paths

---

## User Experience Flow

### First-Time User (Homebrew/pip install)

1. **Install DAZZLE**:
   ```bash
   brew install dazzle  # or pip install dazzle
   ```

2. **Register MCP Server** (one-time):
   ```bash
   dazzle mcp-setup
   ```

3. **Create Project**:
   ```bash
   dazzle init my-project
   cd my-project
   ```

4. **Open Claude Code**:
   - Claude Code automatically starts DAZZLE MCP server
   - Tools immediately available
   - `.claude/CLAUDE.md` informs Claude about capabilities

5. **Verify**:
   - Ask Claude: "What DAZZLE tools do you have access to?"
   - Or run: `dazzle mcp-check`

### Troubleshooting Flow

**Problem**: MCP tools not available

**Solution**:
1. Check registration: `dazzle mcp-check`
2. If not registered: `dazzle mcp-setup`
3. Restart Claude Code
4. If still issues: `dazzle mcp-setup --force`

---

## Remaining Work (Phase 0)

### Task 0.2: Update Project Initialization ⏭️
- ✅ COMPLETED as part of Task 0.1
- `.claude/mcp.json` now created automatically
- Example templates updated

### Task 0.3: Homebrew Post-Install Hook ⏭️
**Status**: Not started
**Estimate**: 2-3 hours

**Requirements**:
- Update `homebrew/dazzle.rb` with `post_install` hook
- Auto-register MCP server on `brew install`
- Add `post_uninstall` hook for cleanup
- Update caveats to mention MCP server

### Task 0.4: PyPI Post-Install Script ⏭️
**Status**: Not started
**Estimate**: 2-3 hours

**Requirements**:
- Create `scripts/post_install.py`
- Update `pyproject.toml` to run post-install
- Handle errors gracefully (don't fail installation)
- Test with pip, pipx, and uv

### Task 0.5: Documentation ⏭️
**Status**: Not started
**Estimate**: 1-2 hours

**Requirements**:
- Create `docs/MCP_INTEGRATION.md`
- Update `README.md` with MCP section
- Add troubleshooting guide
- Update `.claude/CLAUDE.md` template (✅ done in examples)

### Task 0.6: Add Tests ⏭️
**Status**: Not started (current task)
**Estimate**: 2-3 hours

**Requirements**:
- Unit tests for `setup.py` functions
- CLI command tests
- Integration tests for config generation
- Golden master tests for MCP config format

---

## Metrics

- **Lines of Code Added**: ~350
- **New Functions**: 3 (setup.py) + 3 (CLI commands)
- **New Files**: 4
- **Modified Files**: 6
- **Tests Passing**: Manual tests ✅ (unit tests pending)
- **Time Spent**: ~2 hours

---

## Next Steps

1. **Add Unit Tests** for MCP CLI commands (Task 0.6)
2. **Update Homebrew formula** with post-install hook (Task 0.3)
3. **Create PyPI post-install script** (Task 0.4)
4. **Write MCP integration documentation** (Task 0.5)
5. **Test end-to-end workflow** with fresh install

---

## Impact Assessment

### Developer Experience ⭐⭐⭐⭐⭐
- **Before**: Users had to manually configure MCP server (hidden feature)
- **After**: Automatic setup via `dazzle init`, one-command registration

### User Onboarding ⭐⭐⭐⭐⭐
- **Before**: No guidance on MCP capabilities
- **After**: `.claude/CLAUDE.md` immediately informs Claude about tools

### Discoverability ⭐⭐⭐⭐⭐
- **Before**: MCP server existed but users didn't know about it
- **After**: `dazzle mcp-check` shows status, `dazzle --help` lists commands

### Reliability ⭐⭐⭐⭐
- **Config Detection**: Robust multi-path detection
- **Error Handling**: Clear error messages
- **Graceful Degradation**: Manual setup always available

---

## Lessons Learned

1. **Multi-path config detection is essential** - Different OS/install methods use different paths
2. **Clear user feedback matters** - Commands show next steps and explain what they did
3. **Graceful degradation** - Manual setup instructions as fallback
4. **Testing as you go** - Manual testing caught issues early
5. **Documentation in code** - `.claude/CLAUDE.md` is perfect for informing AI assistants

---

## References

- **Roadmap**: `dev_docs/NEXT_STAGES_SPEC.md` (Phase 0, Task 0.1)
- **Strategy**: `dev_docs/mcp_distribution_strategy.md`
- **MCP SDK Docs**: https://github.com/anthropics/anthropic-mcp-sdk
- **Claude Code Config**: `~/.claude/mcp_servers.json`

---

**Session Complete**: Task 0.1 ✅
**Next Session**: Task 0.6 (Add Tests) or Task 0.3 (Homebrew)
