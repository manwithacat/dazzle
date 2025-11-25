# Phase 2 Complete: CLI Integration & Diagnostics

## 🎉 Summary

Phase 2 of the DAZZLE VSCode extension is now complete! The extension now provides full CLI integration with real-time validation and diagnostics.

## ✅ What Was Implemented

### Python CLI Updates

**File**: `/Volumes/SSD/Dazzle/src/dazzle/cli.py`

1. **Added `--format` flag to `validate` command**
   - Format options: `human` (default), `vscode`
   - VSCode format outputs: `file:line:col: severity: message`

2. **Helper functions for formatting**
   - `_print_human_diagnostics()` - Human-readable output
   - `_print_vscode_diagnostics()` - Machine-readable output
   - `_print_vscode_parse_error()` - Parse errors with location info

3. **Error handling**
   - ParseError exceptions show exact file/line/column
   - Validation errors show in structured format
   - Exit codes properly set for CI/CD integration

### VSCode Extension Updates

**Files Created/Updated**:
- `src/diagnostics.ts` - Diagnostics provider
- `src/commands.ts` - Command implementations
- `src/extension.ts` - Main extension with file watchers
- `package.json` - Problem matcher and task definitions

#### Features Implemented

1. **Diagnostics Provider** (`diagnostics.ts`)
   - Runs `dazzle validate --format vscode`
   - Parses output into VSCode Diagnostic objects
   - Displays in Problems panel with file/line/column navigation
   - Output channel for detailed validation logs

2. **Commands** (`commands.ts`)
   - `dazzle.validate` - Run validation with progress notification
   - `dazzle.build` - Open terminal and run build
   - `dazzle.lint` - Open terminal and run linter

3. **File Watchers** (`extension.ts`)
   - Watch `.dsl` and `dazzle.toml` files
   - Auto-validate on file save (configurable)
   - Auto-validate on file create/change/delete
   - Initial validation on workspace open

4. **Problem Matcher** (`package.json`)
   - Regex pattern: `^(.+):(\d+):(\d+):\s+(error|warning):\s+(.*)$`
   - Extracts file, line, column, severity, message
   - Enables click-to-navigate in Problems panel

## 🧪 Testing Guide

### Test 1: Syntax Error Detection

1. Create a test project:
   ```bash
   cd /tmp
   mkdir test_vscode && cd test_vscode
   python3 -m dazzle.cli init .
   ```

2. Open in VS Code:
   ```bash
   code .
   ```

3. Introduce an error in `dsl/app.dsl`:
   ```dsl
   # Remove the colon after "Task"
   entity Task "Task"
     id: uuid pk
   ```

4. Save the file (`Ctrl+S` / `Cmd+S`)

5. **Expected Result**:
   - Error appears in Problems panel
   - Red squiggly underline in editor
   - Click on error navigates to exact location

### Test 2: Validation Command

1. Open Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Type "DAZZLE: Validate"
3. Select "DAZZLE: Validate Project"

**Expected Result**:
- Progress notification appears
- Validation runs
- Results show in Problems panel
- Output channel shows detailed logs

### Test 3: Auto-Validation on Save

1. Fix the error in `dsl/app.dsl`:
   ```dsl
   entity Task "Task":  # Add the colon back
     id: uuid pk
   ```

2. Save the file

**Expected Result**:
- Error disappears from Problems panel
- Green checkmark or no issues shown

### Test 4: Build Command

1. Open Command Palette
2. Run "DAZZLE: Build Project"

**Expected Result**:
- Integrated terminal opens
- Build command runs
- Output shows in terminal

### Test 5: CLI Format Flag

Test the CLI directly:

```bash
cd /tmp/test_vscode

# Human format (default)
python3 -m dazzle.cli validate

# VSCode format
python3 -m dazzle.cli validate --format vscode
```

**Expected VSCode format output**:
```
dsl/app.dsl:6:19: error: Expected :, got NEWLINE
```

## 📊 Configuration Options

All settings accessible via `Preferences: Open Settings (UI)` → search "DAZZLE":

| Setting | Default | Description |
|---------|---------|-------------|
| `dazzle.cliPath` | `"dazzle"` | Path to DAZZLE CLI (e.g., `"python3 -m dazzle.cli"`) |
| `dazzle.manifest` | `"dazzle.toml"` | Name of manifest file |
| `dazzle.validateOnSave` | `true` | Auto-validate on file save |

## 🔧 Troubleshooting

### Extension Not Validating

1. Check Output panel: `View` → `Output` → Select "DAZZLE"
2. Verify CLI path in settings
3. Test CLI manually: `dazzle validate --format vscode`

### CLI Not Found

Update `dazzle.cliPath` setting:
- Absolute path: `"/usr/local/bin/dazzle"`
- Python module: `"python3 -m dazzle.cli"`
- Virtual env: `"./venv/bin/dazzle"`

### Diagnostics Not Clearing

1. Run "DAZZLE: Validate Project" manually
2. Restart extension: `Developer: Reload Window`

## 📦 Files Changed

### Python
- `/Volumes/SSD/Dazzle/src/dazzle/cli.py` - Added `--format` flag and formatting functions

### TypeScript/VSCode Extension
- `/Volumes/SSD/Dazzle/extensions/vscode/src/diagnostics.ts` - New file
- `/Volumes/SSD/Dazzle/extensions/vscode/src/commands.ts` - New file
- `/Volumes/SSD/Dazzle/extensions/vscode/src/extension.ts` - Updated
- `/Volumes/SSD/Dazzle/extensions/vscode/package.json` - Updated (v0.2.0)
- `/Volumes/SSD/Dazzle/extensions/vscode/CHANGELOG.md` - Updated
- `/Volumes/SSD/Dazzle/extensions/vscode/README.md` - Updated

## 🎯 Next Steps: Phase 3

Phase 3 will implement LSP (Language Server Protocol) features:

1. **Python LSP Server**
   - Create `/Volumes/SSD/Dazzle/src/dazzle/lsp/` package
   - Use `pygls` library
   - Entrypoint: `python -m dazzle.lsp`

2. **LSP Features**
   - Go-to-definition (entities, surfaces, fields)
   - Hover documentation
   - Autocomplete (entity names, field types)
   - Document symbols (outline view)
   - Find references
   - Rename refactoring

3. **VS Code LSP Client**
   - Install `vscode-languageclient` dependency
   - Create `src/lspClient.ts`
   - Spawn Python LSP server on activation
   - Connect via stdio

## ✨ Achievement Unlocked

**v0.2.0: CLI Integration & Diagnostics** is now complete! 🎉

Users can now:
- ✅ See errors and warnings in real-time
- ✅ Click to navigate to error locations
- ✅ Run DAZZLE commands from VS Code
- ✅ Auto-validate on save
- ✅ View detailed validation logs

The extension is now significantly more useful for DAZZLE development!
