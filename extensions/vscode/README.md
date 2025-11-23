# DAZZLE DSL for Visual Studio Code

Language support for DAZZLE DSL - the DSL-first application development framework.

## Features

### ✨ Syntax Highlighting (v0.1)

- **Keywords**: `module`, `app`, `entity`, `surface`, `experience`, `service`
- **Type annotations**: `uuid`, `str`, `int`, `datetime`, `enum`, `ref`
- **Field modifiers**: `required`, `unique`, `pk`, `auto_add`, `auto_update`
- **Comments**: `#` line comments
- **Strings and numbers**: Full lexical highlighting

### 🔍 CLI Integration & Diagnostics (v0.2)

- **Real-time Validation**: Errors and warnings appear in Problems panel as you edit
- **Auto-validation on Save**: Automatic validation when you save `.dsl` or `dazzle.toml` files
- **CLI Commands**: Run DAZZLE commands directly from VS Code
  - `DAZZLE: Validate Project` - Check for errors and warnings
  - `DAZZLE: Build Project` - Generate artifacts
  - `DAZZLE: Lint Project` - Run extended linter
- **File Watchers**: Monitors DSL files for changes
- **Output Channel**: View detailed validation output
- **Problem Matcher**: Structured error display with file/line/column navigation

### 🤖 LLM-Assisted Spec Analysis (v0.4)

- **Analyze Specification**: Use AI to extract structure from natural language specs
- **State Machine Detection**: Automatically identify state machines and transitions
- **CRUD Completeness**: Find missing operations and suggest surfaces
- **Interactive Q&A**: Answer clarifying questions to complete your specification
- **DSL Generation**: Generate DAZZLE DSL from analyzed specs (coming soon)

### 🚀 Coming Soon

- **DSL Generation**: Auto-generate complete DSL from spec analysis
- **Code Actions**: Quick fixes for common errors
- **Refactoring**: Rename entities across files

## Installation

### Prerequisites

Install the DAZZLE CLI first:

```bash
# Using pip (recommended)
pip install dazzle

# Or for development
git clone https://github.com/dazzle/dazzle
cd dazzle
pip install -e .
```

Verify installation:
```bash
dazzle --help
```

### Extension Installation

#### Option 1: From Marketplace (Coming Soon)

Install directly from the VS Code Marketplace.

#### Option 2: From Source (Development)

1. Clone the DAZZLE repository
2. Navigate to `extensions/vscode/`
3. Run:
   ```bash
   npm install
   npm run compile
   ```
4. Press F5 in VS Code to launch Extension Development Host

#### Option 3: Manual Installation

1. Build the extension package:
   ```bash
   cd extensions/vscode
   npm install
   npm run package
   ```
2. Install the generated `.vsix` file:
   ```bash
   code --install-extension dazzle-dsl-0.4.0.vsix
   ```

## Usage

### Basic Syntax Highlighting

Simply open any `.dsl` or `.dazzle` file to see syntax highlighting automatically applied.

### Example DSL

```dsl
# Define your application
module myapp.core

app myapp "My Application"

# Create entities
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  created_at: datetime auto_add
  updated_at: datetime auto_update

# Define surfaces (UI/API views)
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"
```

## Configuration

Access settings via `Preferences: Open Settings (UI)` and search for "DAZZLE":

### General Settings
- **`dazzle.cliPath`**: Path to DAZZLE CLI (default: `"dazzle"`)
  - Use `"dazzle"` if installed via pip/homebrew
  - Use absolute path for custom installation locations
  - Examples: `"dazzle"`, `"/usr/local/bin/dazzle"`, `"python3 -m dazzle.cli"`
- **`dazzle.manifest`**: Manifest filename (default: `"dazzle.toml"`)
- **`dazzle.validateOnSave`**: Auto-validate on save (default: `true`)
- **`dazzle.pythonPath`**: Python interpreter for LSP server (default: auto-detect)
  - Leave empty to auto-detect from environment
  - Set explicitly if LSP features don't work: `"/usr/bin/python3"`

### LLM Settings (v0.4+)
- **`dazzle.llm.provider`**: LLM provider for spec analysis (default: `"anthropic"`)
  - Options: `"anthropic"` or `"openai"`
- **`dazzle.llm.model`**: Model to use (default: `"claude-3-5-sonnet-20241022"`)
- **`dazzle.llm.maxCostPerAnalysis`**: Max cost per analysis in USD (default: `1.0`)

### LLM Setup

To use LLM-assisted spec analysis:

1. Install LLM dependencies:
   ```bash
   pip install "dazzle[llm]"
   ```

2. Set your API key:
   ```bash
   # For Anthropic (recommended)
   export ANTHROPIC_API_KEY=sk-ant-...

   # Or for OpenAI
   export OPENAI_API_KEY=sk-...
   ```

3. Open a specification file (e.g., `SPEC.md`)

4. Run: `Cmd+Shift+P` → "DAZZLE: Analyze Specification"

## Commands

Access via Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`):

### DSL Project Commands
- **DAZZLE: Validate Project** - Run validation and show errors/warnings in Problems panel
- **DAZZLE: Build Project** - Generate artifacts (opens integrated terminal)
- **DAZZLE: Lint Project** - Run extended linter (opens integrated terminal)

### LLM-Assisted Commands (v0.4+)
- **DAZZLE: Analyze Specification** - Analyze natural language spec with AI
  - Extracts state machines, CRUD operations, business rules
  - Generates clarifying questions
  - Shows coverage statistics
  - Interactive Q&A to complete specification

All commands are now fully functional!

## Requirements

- VS Code 1.80.0 or higher
- DAZZLE CLI installed and accessible in PATH (`pip install dazzle`)
- Python 3.11+ (for DAZZLE runtime and LSP server)

### Troubleshooting

**Command 'dazzle' not found**:
- Ensure DAZZLE is installed: `pip install dazzle`
- Check PATH: `which dazzle` or `where dazzle` (Windows)
- Configure `dazzle.cliPath` in settings with absolute path

**LSP features not working** (no hover, completion, etc.):
- Install DAZZLE in Python environment: `pip install dazzle`
- Verify: `python3 -c "import dazzle.lsp.server"`
- Configure `dazzle.pythonPath` if using custom Python installation
- Check "DAZZLE LSP" output channel for errors

**Validation not showing errors**:
- Ensure `dazzle.toml` exists in workspace root
- Check "DAZZLE" output channel for validation logs
- Try running `dazzle validate` in terminal to verify CLI works

## Extension Development

### Structure

```
vscode/
├── package.json              # Extension manifest
├── tsconfig.json             # TypeScript config
├── src/
│   └── extension.ts          # Main extension code
├── syntaxes/
│   └── dazzle.tmLanguage.json  # TextMate grammar
└── language-configuration.json # Language config
```

### Building

```bash
npm install
npm run compile
```

### Testing

Press F5 in VS Code to launch the Extension Development Host with the extension loaded.

### Packaging

```bash
npm install -g @vscode/vsce
vsce package
```

## Roadmap

- [x] **v0.1**: Basic syntax highlighting ✓
- [x] **v0.2**: CLI integration, diagnostics, file watchers ✓
- [x] **v0.3**: LSP server with go-to-definition, hover, autocomplete ✓
- [x] **v0.4**: LLM-assisted spec analysis and Q&A ✓
- [ ] **v0.5**: DSL generation from analyzed specs
- [ ] **v1.0**: Stable release with full feature set

## Contributing

Contributions are welcome! Please see the main DAZZLE repository for contribution guidelines.

## License

MIT License - See LICENSE file for details

## Links

- [DAZZLE Documentation](https://github.com/dazzle/dazzle)
- [Report Issues](https://github.com/dazzle/dazzle/issues)
- [VS Code Extension Guidelines](https://code.visualstudio.com/api)

---

**Enjoy using DAZZLE DSL!** 🎉
