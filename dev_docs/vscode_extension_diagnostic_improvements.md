# VS Code Extension Diagnostic Improvements

**Date**: 2025-11-23
**Version**: 0.4.0 → 0.4.1
**Status**: Complete

## Problem

User reported that the DAZZLE VS Code extension was not showing output channels ("DAZZLE" or "DAZZLE LSP") and LSP features (hover, go-to-definition) were not working.

## Root Cause Analysis

The extension was creating output channels but:
1. **Not showing them proactively** - Channels were created but never explicitly shown
2. **Limited error visibility** - LSP startup errors were logged to console but not visible to users
3. **No status indicators** - No way for users to know if LSP was running or why it failed
4. **Insufficient diagnostics** - Hard to troubleshoot LSP connection issues

## Changes Made

### 1. Enhanced LSP Client Logging (`src/lspClient.ts`)

**Before**: Minimal logging, output channel created but never shown
**After**:
- Comprehensive startup logging with timestamps
- Detailed error messages with troubleshooting steps
- Proactive channel display on errors
- Clear success/failure indicators (✅/❌)
- Step-by-step diagnostics

**Key improvements**:
```typescript
// Created persistent output channel
let outputChannel: vscode.OutputChannel | undefined;

function getOutputChannel(): vscode.OutputChannel {
    if (!outputChannel) {
        outputChannel = vscode.window.createOutputChannel('DAZZLE LSP');
    }
    return outputChannel;
}
```

**Logging additions**:
- Startup banner with separator
- Python path detection logging
- LSP availability check results
- Server launch command display
- Feature availability confirmation
- Detailed error troubleshooting

### 2. LSP Status Bar Item (`src/extension.ts`)

**New feature**: Added clickable status bar item showing LSP status

**States**:
- `$(loading~spin) DAZZLE LSP` - Initializing
- `$(check) DAZZLE LSP` - Active and running
- `$(warning) DAZZLE LSP` - Error during startup
- `$(x) DAZZLE LSP` - LSP server not available

**Behavior**:
- Click to open DAZZLE LSP output panel
- Color-coded backgrounds (green/yellow/red)
- Tooltip with status details and install instructions
- Always visible when extension is active

### 3. Show LSP Output Command

**New command**: `dazzle.showLspOutput`
- Registered command to open output panel
- Linked to status bar item
- Accessible from error dialogs
- Makes troubleshooting easier

### 4. Improved Error Dialogs

**Before**: Generic error messages
**After**:
- Contextual error messages
- "Show Output" button to view detailed logs
- "Show Setup Guide" button for installation help
- Links to documentation

### 5. Testing Infrastructure

**Added**:
- `src/test/extension.test.ts` - Basic extension tests
- `src/test/runTest.ts` - Test runner configuration
- `src/test/suite/index.ts` - Test suite setup
- `.vscode/launch.json` - Debug configurations for extension and tests

**Test coverage**:
- Extension presence verification
- Activation tests
- Command registration checks
- Language registration validation

**Dependencies added**:
- `@types/glob`: Type definitions for glob
- `@types/mocha`: Type definitions for Mocha test framework
- `@vscode/vsce`: VS Code extension packaging tool
- `glob`: File pattern matching
- `mocha`: Test framework

### 6. Better Welcome Experience

**Before**: Generic welcome message
**After**:
- Clear LSP status in welcome message
- "Show LSP Status" button to view output
- Installation instructions if LSP unavailable
- Links to documentation

## Files Modified

1. **`extensions/vscode/src/lspClient.ts`**
   - Added comprehensive logging
   - Enhanced error handling
   - Proactive output channel display
   - Detailed troubleshooting info

2. **`extensions/vscode/src/extension.ts`**
   - Added LSP status bar item
   - Registered show output command
   - Enhanced activation flow
   - Better error visibility

3. **`extensions/vscode/package.json`**
   - Version bump: 0.4.0 → 0.4.1
   - Added test dependencies
   - Updated dev dependencies

## Files Created

1. **`extensions/vscode/src/test/extension.test.ts`** - Extension tests
2. **`extensions/vscode/src/test/runTest.ts`** - Test runner
3. **`extensions/vscode/src/test/suite/index.ts`** - Test suite
4. **`extensions/vscode/.vscode/launch.json`** - Debug configurations

## Testing

### Build Verification
```bash
cd extensions/vscode
npm install       # ✅ Dependencies installed (324 packages)
npm run compile   # ✅ TypeScript compiled successfully
npm run package   # ✅ Extension packaged as dazzle-dsl-0.4.1.vsix
```

### Package Contents
- Extension size: 43.13 KB (22 files)
- Includes compiled JavaScript in `out/`
- Includes test infrastructure
- Syntax highlighting and language config

## User Installation

```bash
# From VS Code
1. Open VS Code
2. View → Extensions
3. Click "..." menu → Install from VSIX
4. Select: extensions/vscode/dazzle-dsl-0.4.1.vsix

# Or command line
code --install-extension extensions/vscode/dazzle-dsl-0.4.1.vsix
```

## Verification Steps

After installing the new extension:

1. **Check Status Bar** - Should see LSP status item in bottom right
2. **Open DAZZLE Project** - Extension should activate
3. **Check Output Panel** - "DAZZLE LSP" should appear in dropdown
4. **Click Status Bar Item** - Should open output panel with logs
5. **Open .dsl file** - Should get syntax highlighting
6. **Hover over entity** - Should see hover information (if LSP running)
7. **Cmd/Ctrl + Click** - Should go to definition (if LSP running)

## Troubleshooting

### If LSP shows error (⚠️ or ❌):

1. **Click status bar item** to view detailed logs
2. **Check Python installation**:
   ```bash
   python3 -c "import dazzle.lsp.server"
   ```
3. **Verify dazzle installed**:
   ```bash
   pip list | grep dazzle
   ```
4. **Set Python path** (if needed):
   - VS Code Settings → "dazzle.pythonPath"
   - Set to your Python interpreter with dazzle installed

### If output channels not visible:

1. Open output panel: View → Output
2. Select "DAZZLE LSP" from dropdown
3. Click status bar item (bottom right)

## What Users Should See Now

### On Extension Activation:
- Status bar item appears (bottom right)
- Welcome notification with LSP status
- Output panel available in View → Output

### When Opening .dsl File:
- Syntax highlighting active
- Diagnostics on save (if validation enabled)
- LSP features (hover, go-to-def) if LSP running

### If LSP Not Available:
- Clear error message
- Status bar shows ❌ with install instructions
- Output panel has detailed troubleshooting
- Links to documentation

## Future Improvements

1. **Auto-detect Python environments** (pyenv, conda, venv)
2. **LSP restart command** without reloading window
3. **More granular LSP settings** (enable/disable features)
4. **LSP performance metrics** in output panel
5. **Diagnostic quick fixes** for common errors
6. **Integration tests** with actual .dsl files

## Notes

- All logging now uses structured format with clear indicators (✅/❌)
- Output channels are persistent and reused
- Status bar provides quick glance at system health
- Error messages guide users to solutions
- Tests provide foundation for CI/CD

## Success Criteria

✅ Extension builds and packages successfully
✅ Output channels created and accessible
✅ Status bar item shows LSP status
✅ Detailed logging for troubleshooting
✅ Error messages include actionable steps
✅ Test infrastructure in place
✅ Version bumped to 0.4.1

## Related Documentation

- Main README: `extensions/vscode/README.md`
- Troubleshooting: `extensions/vscode/TROUBLESHOOTING.md`
- Installation: `extensions/vscode/INSTALL.md`
- User Guide: `docs/vscode_extension_user_guide.md`
