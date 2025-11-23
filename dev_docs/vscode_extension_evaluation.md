# VS Code Extension Evaluation & Migration Plan

**Date**: 2025-11-23
**Status**: Evaluation Complete, Migration In Progress

## Current State Assessment

### What Works Well ✅

1. **Syntax Highlighting** (v0.1)
   - Complete TextMate grammar for `.dsl` and `.dazzle` files
   - Covers all DSL keywords, types, modifiers, comments
   - File: `extensions/vscode/syntaxes/dazzle.tmLanguage.json`

2. **CLI Integration** (v0.2)
   - Commands: validate, build, lint
   - Real-time diagnostics with file watchers
   - Problem matcher for structured error display
   - Output channel for detailed logs

3. **LSP Features** (v0.3)
   - Hover documentation
   - Go-to-definition
   - Autocomplete
   - Document symbols
   - Graceful degradation when LSP unavailable

4. **LLM Features** (v0.4)
   - Spec analysis with AI
   - State machine detection
   - CRUD completeness checking
   - Interactive Q&A

5. **Configuration**
   - Customizable CLI path
   - Python path override
   - Validate-on-save toggle
   - LLM provider settings

### Issues Found ❌

#### 1. **Hardcoded Development Paths**
- **File**: `src/lspClient.ts:31, 55`
- **Problem**: References `/Volumes/SSD/Dazzle` explicitly
- **Impact**: Won't work for other users or installations
```typescript
// Line 31: Error message
`1. Install dazzle: pip install -e /Volumes/SSD/Dazzle\n` +

// Line 55: PYTHONPATH
PYTHONPATH: `/Volumes/SSD/Dazzle/src${...}`
```

#### 2. **CLI Command Format**
- **File**: `src/diagnostics.ts:44-58`
- **Problem**: Complex parsing for `python -m dazzle.cli` format
- **Impact**: Assumes non-standard CLI usage
- **Should be**: Simple `dazzle` command

#### 3. **Python Path Detection Complexity**
- **File**: `src/lspClient.ts:118-142`
- **Problem**: Overly complex logic for development mode
- **Impact**: Confusing for production use
- **Better**: Simpler detection with clear fallback

#### 4. **Missing CLI Validation**
- **Problem**: No check if `dazzle` command exists
- **Impact**: Cryptic errors if not installed
- **Should**: Provide clear installation instructions

#### 5. **Validate Command Format**
- **File**: `src/diagnostics.ts:44`
- **Problem**: Assumes `--format vscode` flag exists
- **Impact**: May fail with different CLI versions
- **Need**: Verify this flag is implemented in CLI

#### 6. **Documentation Assumptions**
- **Problem**: README assumes development setup
- **Impact**: Users installing via pip/homebrew confused
- **Need**: Separate production vs development docs

## Migration to Homebrew Installation

### Goals

1. ✅ Use `dazzle` command directly (not `python -m dazzle.cli`)
2. ✅ Remove all hardcoded development paths
3. ✅ Simplify Python detection for LSP server
4. ✅ Better error handling and user guidance
5. ✅ Support both development and production installs
6. ✅ Update documentation for clarity

### Changes Required

#### 1. Update `commands.ts`
- Default `cliPath` to `"dazzle"` (already correct in package.json)
- Remove python-specific command parsing
- Simplify command execution

#### 2. Update `diagnostics.ts`
- Use `dazzle` command directly
- Remove complex python command parsing (lines 46-58)
- Improve error messages

#### 3. Update `lspClient.ts`
- Remove hardcoded `/Volumes/SSD/Dazzle` paths
- Simplify Python path detection
- Better error messages for LSP unavailable
- Remove development-specific PYTHONPATH manipulation

#### 4. Update `package.json`
- Default `dazzle.cliPath` is already `"dazzle"` ✅
- Consider adding `dazzle.installType` setting (dev vs prod)

#### 5. Update `README.md`
- Add production installation instructions
- Separate dev setup from user setup
- Document both installation types

### Testing Plan

1. ✅ Verify `dazzle` CLI is in PATH
2. ⬜ Test validate command with installed CLI
3. ⬜ Test build command
4. ⬜ Test lint command
5. ⬜ Test LSP features with installed version
6. ⬜ Test with no installation (error handling)
7. ⬜ Test in clean environment

## Implementation Priority

### High Priority (Breaking Issues)
1. Remove hardcoded paths from `lspClient.ts`
2. Simplify CLI command execution in `diagnostics.ts`
3. Update error messages to guide users

### Medium Priority (Improvements)
1. Add installation type detection
2. Improve documentation
3. Add better error handling

### Low Priority (Nice to Have)
1. Add installation wizard
2. Better LSP server detection
3. Auto-download/install helper

## CLI Verification

```bash
$ which dazzle
/Users/james/.pyenv/shims/dazzle

$ dazzle --help
# Works! Shows all commands including validate, build, lint

$ python3 -c "import dazzle.lsp.server; print('LSP available')"
# LSP server available ✅
```

## Next Steps

1. ✅ Complete this evaluation document
2. ⬜ Update `lspClient.ts` to remove hardcoded paths
3. ⬜ Simplify `diagnostics.ts` command execution
4. ⬜ Update documentation
5. ⬜ Test all features with installed version
6. ⬜ Create migration guide for developers

## Notes

- Extension version: 0.4.0
- Requires VS Code 1.80.0+
- Python 3.11+ required for DAZZLE runtime
- LSP server uses `pygls` library
