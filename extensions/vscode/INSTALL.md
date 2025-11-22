# Installation and Testing Guide

## Quick Start

### 1. Install Dependencies

```bash
cd /Volumes/SSD/Dazzle/extensions/vscode
npm install
```

### 2. Compile TypeScript

```bash
npm run compile
```

### 3. Test in VS Code

#### Option A: Launch from VS Code
1. Open the `extensions/vscode` folder in VS Code
2. Press `F5` to launch Extension Development Host
3. In the new window, open `test/sample.dsl`
4. You should see syntax highlighting applied

#### Option B: Install Locally
```bash
# Package the extension
npm install -g @vscode/vsce
vsce package

# This creates dazzle-dsl-0.1.0.vsix
# Install it in VS Code:
code --install-extension dazzle-dsl-0.1.0.vsix
```

## Verify Installation

1. Open any `.dsl` file in VS Code
2. Check the language mode in bottom-right corner - should show "DAZZLE"
3. Verify syntax highlighting is active:
   - Keywords like `module`, `entity`, `surface` should be colored
   - Type annotations like `uuid`, `str`, `datetime` should be distinct
   - Comments starting with `#` should be grayed out
   - Strings should be highlighted

## Testing Features

### Syntax Highlighting

Open `test/sample.dsl` and verify:
- [x] Module declarations are highlighted
- [x] Entity and surface declarations stand out
- [x] Field types (uuid, str, int, etc.) are colored
- [x] Modifiers (required, unique, pk) are highlighted
- [x] Comments are distinguishable
- [x] Strings are properly colored

### Commands (Placeholder)

1. Open Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Type "DAZZLE"
3. You should see:
   - DAZZLE: Validate Project
   - DAZZLE: Build Project
   - DAZZLE: Lint Project

These show placeholder messages in v0.1 and will be functional in v0.2.

### Configuration

1. Open Settings (`Ctrl+,` / `Cmd+,`)
2. Search for "dazzle"
3. You should see:
   - DAZZLE: Cli Path
   - DAZZLE: Manifest
   - DAZZLE: Validate On Save

## Troubleshooting

### Extension Not Loading

1. Check the Extension Development Host console for errors
2. Verify `out/extension.js` was created: `ls out/`
3. Recompile: `npm run compile`

### No Syntax Highlighting

1. Check file extension is `.dsl` or `.dazzle`
2. Check language mode in status bar
3. Force language mode: Click language indicator → Select "DAZZLE"

### TypeScript Errors

1. Ensure TypeScript version: `npx tsc --version` (should be 5.0+)
2. Clean and rebuild:
   ```bash
   rm -rf out node_modules
   npm install
   npm run compile
   ```

## Development Workflow

### Watch Mode

For active development with auto-recompilation:

```bash
npm run watch
```

Then press `F5` in VS Code to launch with hot reload.

### Making Changes

1. Edit `src/extension.ts` or grammar files
2. Run `npm run compile`
3. Reload extension window (`Ctrl+R` / `Cmd+R` in Extension Development Host)

## Next Steps (Phase 2)

- [ ] Implement CLI integration
- [ ] Add diagnostics provider
- [ ] Set up file watchers
- [ ] Add problem matcher

See `devdocs/DAZZLE_VSCODE_SPEC.md` for full roadmap.
