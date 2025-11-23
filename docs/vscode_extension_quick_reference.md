# DAZZLE VS Code Extension - Quick Reference

**Version**: 0.4.0
**Last Updated**: 2025-11-23

---

## Installation (Quick Start)

```bash
# 1. Install DAZZLE CLI
pip install dazzle

# 2. Verify installation
dazzle --help

# 3. Install VS Code extension
# (From marketplace or .vsix file)

# 4. Create project
dazzle init

# 5. Open in VS Code
code .
```

---

## Keyboard Shortcuts

| Action | Mac | Windows/Linux |
|--------|-----|---------------|
| **Command Palette** | `Cmd+Shift+P` | `Ctrl+Shift+P` |
| **Go to Definition** | `Cmd+Click` or `F12` | `Ctrl+Click` or `F12` |
| **Trigger Autocomplete** | `Ctrl+Space` | `Ctrl+Space` |
| **Problems Panel** | `Cmd+Shift+M` | `Ctrl+Shift+M` |
| **Symbol Search** | `Cmd+Shift+O` | `Ctrl+Shift+O` |
| **Settings** | `Cmd+,` | `Ctrl+,` |
| **Save & Validate** | `Cmd+S` | `Ctrl+S` |

---

## Commands

Access via Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`):

| Command | Description |
|---------|-------------|
| **DAZZLE: Validate Project** | Check DSL files for errors |
| **DAZZLE: Build Project** | Generate code from DSL |
| **DAZZLE: Lint Project** | Run extended linter |
| **DAZZLE: Analyze Specification** | AI-powered spec analysis |

---

## DSL Syntax Cheat Sheet

### Module & App

```dsl
module myapp.modulename

app myapp "My Application"
```

### Entity (Basic)

```dsl
entity EntityName "Display Name":
  id: uuid pk
  name: str(200) required
  created_at: datetime auto_add
```

### Field Types

| Type | Example | Description |
|------|---------|-------------|
| `uuid` | `id: uuid pk` | UUID primary key |
| `str(n)` | `name: str(100)` | String with max length |
| `text` | `description: text` | Long text |
| `int` | `count: int` | Integer |
| `float` | `price: float` | Decimal number |
| `bool` | `active: bool` | True/False |
| `datetime` | `created_at: datetime` | Date + time |
| `date` | `birthday: date` | Date only |
| `time` | `start_time: time` | Time only |
| `enum[...]` | `status: enum[a,b,c]` | Fixed choices |
| `ref Entity` | `owner: ref User` | Foreign key |

### Field Modifiers

| Modifier | Example | Description |
|----------|---------|-------------|
| `pk` | `id: uuid pk` | Primary key |
| `required` | `name: str required` | Not nullable |
| `unique` | `email: str unique` | Unique constraint |
| `indexed` | `code: str indexed` | Database index |
| `default=X` | `active: bool default=true` | Default value |
| `auto_add` | `created_at: datetime auto_add` | Set on create |
| `auto_update` | `updated_at: datetime auto_update` | Update timestamp |

### Surface (List)

```dsl
surface entity_list "Entity List":
  uses entity EntityName
  mode: list

  section main "Section Title":
    field field1 "Label 1"
    field field2 "Label 2"
```

### Surface (Detail)

```dsl
surface entity_detail "Entity Detail":
  uses entity EntityName
  mode: detail

  section main "Main Info":
    field field1 "Label 1"
    field field2 "Label 2"

  section metadata "Metadata":
    field created_at "Created"
    field updated_at "Updated"
```

### Surface (Form)

```dsl
surface entity_form "Create/Edit":
  uses entity EntityName
  mode: form

  section inputs "Input Fields":
    field field1 "Label 1"
    field field2 "Label 2"
```

### Using Modules

```dsl
module myapp.surfaces

use myapp.core  # Import another module

surface user_list "Users":
  uses entity User  # From myapp.core
  mode: list
```

---

## Common Workflows

### 1. Create New Entity

```dsl
# In dsl/core.dsl
entity NewEntity "Display Name":
  id: uuid pk
  name: str(200) required
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

**Save** → Auto-validates → Check Problems panel

### 2. Add Surface for Entity

```dsl
# In dsl/surfaces.dsl
surface new_entity_list "New Entity List":
  uses entity NewEntity
  mode: list

  section main "Items":
    field name "Name"
    field created_at "Created"
```

**Save** → Auto-validates

### 3. Validate Manually

1. `Cmd+Shift+P` / `Ctrl+Shift+P`
2. Type "validate"
3. Select "DAZZLE: Validate Project"
4. Check Problems panel

### 4. Build Project

1. `Cmd+Shift+P` / `Ctrl+Shift+P`
2. Type "build"
3. Select "DAZZLE: Build Project"
4. Select stack (if prompted)
5. Check terminal output

### 5. Fix Validation Error

1. **See error** in Problems panel
2. **Click error** to jump to location
3. **Read error message**
4. **Fix issue** (e.g., fix entity name)
5. **Save file** → Error disappears

### 6. Navigate to Definition

1. **Cmd+Click** (Mac) or **Ctrl+Click** (Windows) on entity reference
2. Editor jumps to definition

Or:
1. Place cursor on entity name
2. Press **F12**

### 7. Use Autocomplete

1. Start typing: `st`
2. Autocomplete appears: `str`, `status`, etc.
3. Use **↑↓** arrows to select
4. Press **Enter** or **Tab** to accept

### 8. Analyze Specification

1. Open `.md` file with requirements
2. `Cmd+Shift+P` / `Ctrl+Shift+P`
3. Type "analyze"
4. Select "DAZZLE: Analyze Specification"
5. View results in panel

---

## Troubleshooting (Quick Fixes)

### Problem: "Command 'dazzle' not found"

```bash
# Install DAZZLE
pip install dazzle

# Verify
dazzle --help

# If still fails, set explicit path in Settings:
# dazzle.cliPath: "/path/to/dazzle"
```

### Problem: LSP not working (no hover, autocomplete)

```bash
# Install DAZZLE Python package
pip install dazzle

# Verify LSP available
python3 -c "import dazzle.lsp.server"

# Check "DAZZLE LSP" output channel for errors
```

### Problem: Validation not running

1. Check `dazzle.toml` exists in workspace root
2. Enable auto-validation:
   - Settings → Search "dazzle validate"
   - Check "Validate On Save"
3. Check "DAZZLE" output channel for errors

### Problem: No syntax highlighting

1. Check file extension is `.dsl` or `.dazzle`
2. Check language mode in status bar (bottom-right)
3. Manually set: Click language → Select "DAZZLE"

---

## Configuration (Common Settings)

Access: `Cmd+,` / `Ctrl+,` → Search "dazzle"

### Essential Settings

```json
{
  // Path to DAZZLE CLI
  "dazzle.cliPath": "dazzle",

  // Auto-validate on save
  "dazzle.validateOnSave": true,

  // Python for LSP (empty = auto-detect)
  "dazzle.pythonPath": "",

  // LLM provider
  "dazzle.llm.provider": "anthropic",

  // LLM model
  "dazzle.llm.model": "claude-3-5-sonnet-20241022"
}
```

---

## Output Channels

View detailed logs:

1. **View** → **Output** (or `Cmd+Shift+U` / `Ctrl+Shift+U`)
2. Select channel from dropdown:
   - **DAZZLE**: Validation output
   - **DAZZLE LSP**: Language server logs

---

## File Structure Template

```
my-project/
├── dazzle.toml           # Project manifest
├── dsl/                  # DSL files
│   ├── core.dsl          # Core entities
│   ├── surfaces.dsl      # UI surfaces
│   └── integrations.dsl  # External services
├── build/                # Generated code (after build)
└── .gitignore
```

---

## Example: Complete CRUD App

```dsl
# dsl/core.dsl
module myapp.core

app myapp "My Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  created_at: datetime auto_add
  updated_at: datetime auto_update

# dsl/surfaces.dsl
module myapp.surfaces

use myapp.core

# List view
surface task_list "Tasks":
  uses entity Task
  mode: list
  section main "All Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"

# Detail view
surface task_detail "Task Details":
  uses entity Task
  mode: detail
  section info "Task Information":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
  section meta "Metadata":
    field created_at "Created"
    field updated_at "Updated"

# Create/Edit form
surface task_form "Task Form":
  uses entity Task
  mode: form
  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
```

**Build**:
```bash
dazzle build --stack django_micro_modular
```

---

## Pro Tips

### 1. Use Outline View
- Explorer sidebar → "Outline"
- Shows file structure
- Click to navigate

### 2. Multi-Cursor Editing
- `Cmd+D` / `Ctrl+D` to select next occurrence
- Edit multiple fields at once

### 3. Symbol Search
- `Cmd+Shift+O` / `Ctrl+Shift+O`
- Quickly jump to entities

### 4. Peek Definition
- `Opt+F12` / `Alt+F12`
- See definition without leaving file

### 5. Problems Panel Navigation
- `F8` to jump to next error
- `Shift+F8` for previous error

### 6. Breadcrumbs
- View → Show Breadcrumbs
- Shows context path

### 7. Format on Save
- Settings → Search "format on save"
- Auto-format DSL (if formatter available)

### 8. File Icons
- Install "File Icons" extension
- Better visual distinction of `.dsl` files

### 9. Minimap
- View → Show Minimap
- Overview of long files

### 10. Zen Mode
- `Cmd+K Z` / `Ctrl+K Z`
- Distraction-free editing

---

## Getting Help

### Within VS Code
1. Command Palette → Type "DAZZLE"
2. Output channels: "DAZZLE" and "DAZZLE LSP"
3. Problems panel for errors

### External Resources
- **Documentation**: `/docs/DAZZLE_DSL_REFERENCE_0_1.md`
- **GitHub**: https://github.com/dazzle/dazzle
- **Issues**: https://github.com/dazzle/dazzle/issues
- **Extension README**: `/extensions/vscode/README.md`

### Report Issues
Include:
- VS Code version: `Help` → `About`
- Extension version: Extensions → DAZZLE DSL
- DAZZLE version: `dazzle --version`
- OS and version
- Error from Output channels
- Steps to reproduce

---

## Checklists

### New Project Setup
- [ ] Install DAZZLE: `pip install dazzle`
- [ ] Create project: `dazzle init`
- [ ] Open in VS Code: `code .`
- [ ] Verify extension active (check Command Palette)
- [ ] Create first DSL file
- [ ] Save and validate
- [ ] Check Problems panel

### Before Building
- [ ] All DSL files saved
- [ ] Run "DAZZLE: Validate Project"
- [ ] Problems panel shows 0 errors
- [ ] Commit changes to git
- [ ] Run "DAZZLE: Build Project"
- [ ] Select appropriate stack
- [ ] Review generated code

### Troubleshooting Checklist
- [ ] Extension installed and enabled?
- [ ] DAZZLE CLI in PATH? (`which dazzle`)
- [ ] `dazzle.toml` in workspace root?
- [ ] Python package installed? (`python3 -c "import dazzle"`)
- [ ] Check Output channels for errors
- [ ] Try reloading window (`Reload Window`)
- [ ] Check VS Code version (>= 1.80.0)

---

## Quick Command Reference

```bash
# CLI Commands (in terminal)
dazzle init              # Initialize project
dazzle validate          # Validate DSL
dazzle build             # Build project
dazzle lint              # Lint project
dazzle stacks            # List available stacks
dazzle --help            # Show help

# VS Code Commands (Command Palette)
DAZZLE: Validate Project
DAZZLE: Build Project
DAZZLE: Lint Project
DAZZLE: Analyze Specification
```

---

**For detailed information, see the full [User Guide](vscode_extension_user_guide.md)**
