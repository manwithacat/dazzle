# DAZZLE VS Code Extension - User Guide

**Version**: 0.4.0
**Last Updated**: 2025-11-23
**Purpose**: Complete guide for users and user acceptance testing

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Installation](#installation)
3. [First Project Setup](#first-project-setup)
4. [Core Features](#core-features)
5. [Working with DSL Files](#working-with-dsl-files)
6. [Commands and Actions](#commands-and-actions)
7. [LSP Features](#lsp-features)
8. [LLM-Assisted Features](#llm-assisted-features)
9. [Configuration](#configuration)
10. [Troubleshooting](#troubleshooting)
11. [UAT Test Scenarios](#uat-test-scenarios)

---

## Getting Started

### What is the DAZZLE VS Code Extension?

The DAZZLE VS Code extension provides comprehensive IDE support for working with DAZZLE DSL files, including:

- **Syntax highlighting** for `.dsl` files
- **Real-time validation** with error/warning display
- **Intelligent autocomplete** for types and keywords
- **Hover documentation** for entities and fields
- **Go-to-definition** navigation
- **LLM-assisted spec analysis** for generating DSL from natural language

### Who Should Use This Extension?

- Developers writing DAZZLE DSL specifications
- Product managers defining application requirements
- Technical writers documenting system designs
- Teams using DAZZLE for rapid application development

---

## Installation

### Prerequisites

Before installing the extension, you need:

1. **Visual Studio Code** (version 1.80.0 or higher)
   - Download from: https://code.visualstudio.com/

2. **DAZZLE CLI** installed and accessible in your PATH
   - Installation command:
     ```bash
     pip install dazzle
     ```

3. **Python 3.11+** (for DAZZLE runtime)
   - Download from: https://www.python.org/

### Step-by-Step Installation

#### Method 1: Install DAZZLE CLI First (Recommended)

```bash
# Step 1: Install DAZZLE
pip install dazzle

# Step 2: Verify installation
dazzle --help

# Expected output:
# Usage: dazzle [OPTIONS] COMMAND [ARGS]...
# DAZZLE – DSL-first app generator
# ...

# Step 3: Verify Python package
python3 -c "import dazzle.lsp.server; print('✓ LSP server available')"
```

#### Method 2: Install Extension

**Option A: From VS Code Marketplace** (Coming Soon)
1. Open VS Code
2. Press `Cmd+Shift+X` (Mac) or `Ctrl+Shift+X` (Windows/Linux)
3. Search for "DAZZLE DSL"
4. Click "Install"

**Option B: From Source (Development)**
1. Clone the DAZZLE repository:
   ```bash
   git clone https://github.com/dazzle/dazzle
   cd dazzle/extensions/vscode
   ```

2. Install dependencies:
   ```bash
   npm install
   npm run compile
   ```

3. Launch Extension Development Host:
   - Press `F5` in VS Code
   - A new VS Code window will open with the extension loaded

**Option C: Manual Installation from .vsix**
1. Download or build the `.vsix` file:
   ```bash
   cd extensions/vscode
   npm install
   npm run package
   ```

2. Install the package:
   ```bash
   code --install-extension dazzle-dsl-0.4.0.vsix
   ```

### Verification

After installation, verify everything works:

1. **Check Extension is Active**:
   - Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Type "DAZZLE"
   - You should see DAZZLE commands listed

2. **Create a Test File**:
   - Create a new file: `test.dsl`
   - Type: `module test`
   - You should see syntax highlighting

3. **Check Output Channels**:
   - Open Output panel: `View` → `Output`
   - Select "DAZZLE" from dropdown
   - Select "DAZZLE LSP" from dropdown
   - Both should show initialization messages

---

## First Project Setup

### Creating a New DAZZLE Project

#### Step 1: Initialize Project

```bash
# Create and navigate to project directory
mkdir my-dazzle-app
cd my-dazzle-app

# Initialize DAZZLE project
dazzle init
```

This creates:
- `dazzle.toml` - Project manifest
- `dsl/` - Directory for DSL files
- `.gitignore` - Git ignore rules

#### Step 2: Open in VS Code

```bash
code .
```

#### Step 3: Verify Extension Activation

When you open the workspace:
1. Extension automatically detects `dazzle.toml`
2. Status notification appears: "DAZZLE DSL extension activated!"
3. File watchers start monitoring `.dsl` files
4. LSP server starts (if available)

#### Step 4: Create Your First DSL File

1. Create `dsl/core.dsl`
2. Type the following:

```dsl
module myapp.core

app myapp "My Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add
```

3. Save the file (`Cmd+S` / `Ctrl+S`)
4. Watch the Problems panel for validation results

---

## Core Features

### 1. Syntax Highlighting

The extension provides color-coded syntax highlighting for:

#### Keywords (Purple/Blue)
- `module`, `use`, `app`
- `entity`, `surface`, `experience`
- `service`, `foreign_model`, `integration`

#### Types (Teal/Cyan)
- `uuid`, `str`, `int`, `float`, `bool`
- `text`, `datetime`, `date`, `time`
- `enum`, `ref`

#### Modifiers (Yellow/Gold)
- `required`, `unique`, `pk`
- `auto_add`, `auto_update`
- `indexed`, `default`

#### Strings and Numbers (Green/Orange)
- String literals: `"Task List"`
- Numbers: `200`, `10.5`

#### Comments (Gray)
- Line comments: `# This is a comment`

**Test It**:
1. Open any `.dsl` file
2. Observe that keywords are colored differently from types
3. Comments should be gray/muted

### 2. Real-Time Validation

The extension validates your DSL as you type and on save.

#### How It Works

1. **On Save**: Automatic validation runs
2. **Problems Panel**: Errors and warnings appear
3. **Inline Squiggles**: Red/yellow underlines in editor
4. **Output Channel**: Detailed validation logs

#### Example Validation Flow

**Create a file with an error**:

```dsl
module test.validation

app myapp "Test App"

entity User "User":
  id: uuid pk
  name: str(100) required

surface user_list "User List":
  uses entity NonExistentEntity  # ← This will cause an error
  mode: list
```

**Expected Results**:
1. Problems panel shows: "Unknown entity 'NonExistentEntity'"
2. Red squiggle under `NonExistentEntity`
3. Click error to jump to line

**Fix the error**:
```dsl
surface user_list "User List":
  uses entity User  # ← Fixed
  mode: list
```

**Expected Results**:
1. Problems panel clears
2. Red squiggle disappears
3. Output shows: "No issues found ✓"

#### Validation Levels

- **Errors** (Red): Must fix before building
  - Unknown entities
  - Invalid syntax
  - Missing required fields
  - Duplicate definitions

- **Warnings** (Yellow): Should review
  - Unused imports
  - Deprecated syntax
  - Naming conventions
  - Best practice violations

### 3. File Watchers

The extension automatically monitors:

- **`.dsl` files**: Any changes trigger validation
- **`dazzle.toml`**: Changes reload configuration
- **All files in `dsl/` directory**: Recursive monitoring

**Test File Watchers**:
1. Open a DAZZLE project
2. Make changes to a `.dsl` file
3. Save the file
4. Check Output panel → "DAZZLE" channel
5. You should see: "Running validation in /path/to/project..."

#### Disabling Auto-Validation

If auto-validation is distracting:

1. Press `Cmd+,` (Mac) or `Ctrl+,` (Windows/Linux)
2. Search for "dazzle validate"
3. Uncheck "Dazzle: Validate On Save"
4. Use manual validation: `Cmd+Shift+P` → "DAZZLE: Validate Project"

---

## Working with DSL Files

### Creating DSL Files

#### Method 1: Manual Creation

1. Right-click in Explorer
2. Select "New File"
3. Name it with `.dsl` extension
4. Extension activates automatically

#### Method 2: Using Terminal

```bash
# Create module file
touch dsl/mymodule.dsl

# Open in VS Code
code dsl/mymodule.dsl
```

### Basic DSL Structure

Every DSL file should start with a module declaration:

```dsl
module myapp.modulename

# Then define your entities, surfaces, etc.
```

### Example: Complete DSL File

```dsl
module todo.core

app todo "Todo Application"

# Entity definitions
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  created_at: datetime auto_add
  updated_at: datetime auto_update

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  created_at: datetime auto_add

# Surface definitions
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field created_at "Created"

surface task_detail "Task Details":
  uses entity Task
  mode: detail

  section main "Task Information":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"

  section metadata "Metadata":
    field created_at "Created At"
    field updated_at "Last Updated"

surface task_form "Create/Edit Task":
  uses entity Task
  mode: form

  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
```

### Multi-Module Projects

#### File Structure

```
my-project/
├── dazzle.toml
└── dsl/
    ├── core.dsl        # Core entities
    ├── auth.dsl        # Authentication
    ├── api.dsl         # API surfaces
    └── admin.dsl       # Admin surfaces
```

#### Using Modules

**In `dsl/api.dsl`**:
```dsl
module myapp.api

use myapp.core  # Import core module

surface task_api "Task API":
  uses entity Task  # From core module
  mode: list
```

**In `dsl/admin.dsl`**:
```dsl
module myapp.admin

use myapp.core
use myapp.auth

surface admin_dashboard "Admin Dashboard":
  uses entity User  # From auth or core
  mode: list
```

---

## Commands and Actions

### Accessing Commands

**Method 1: Command Palette**
- Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
- Type "DAZZLE"
- Select command

**Method 2: Right-Click Context Menu** (when available)

**Method 3: Keyboard Shortcuts** (if configured)

### Available Commands

#### 1. DAZZLE: Validate Project

**Purpose**: Check all DSL files for errors and warnings

**How to Use**:
1. Open Command Palette
2. Type "DAZZLE: Validate"
3. Select "DAZZLE: Validate Project"
4. Progress notification appears
5. Results shown in Problems panel

**What It Does**:
- Parses all `.dsl` files in project
- Checks syntax and semantics
- Validates entity references
- Checks for duplicate definitions
- Displays errors/warnings in Problems panel

**Example Output** (in Output channel):
```
Running validation in /Users/you/my-project...
Executing: dazzle validate --format vscode --manifest dazzle.toml
Validation completed with code 0
No issues found ✓
```

**With Errors**:
```
Running validation in /Users/you/my-project...
Executing: dazzle validate --format vscode --manifest dazzle.toml
Validation completed with code 1
Found 3 diagnostic(s)
```

Problems panel shows:
```
dsl/core.dsl:15:10: error: Unknown entity 'Product'
dsl/api.dsl:8:5: warning: Unused import 'myapp.auth'
dsl/surfaces.dsl:20:3: error: Field 'created_by' not found in entity 'Task'
```

#### 2. DAZZLE: Build Project

**Purpose**: Generate code from DSL specifications

**How to Use**:
1. Open Command Palette
2. Type "DAZZLE: Build"
3. Select "DAZZLE: Build Project"
4. Integrated terminal opens
5. Build process runs

**What It Does**:
- Opens new terminal in workspace
- Runs `dazzle build` command
- Shows interactive output
- Prompts for stack selection if needed

**Example Terminal Output**:
```bash
$ dazzle build
Select stack:
1. openapi
2. django_micro_modular
3. docker
4. terraform
> 2

Building with stack: django_micro_modular
✓ Parsing DSL modules
✓ Linking modules
✓ Validating AppSpec
✓ Generating Django models
✓ Generating API views
✓ Generating serializers
✓ Generating URLs
✓ Generating admin classes

Build complete! Output: ./build/
```

**Build Output Structure**:
```
build/
├── models/
│   ├── task.py
│   └── user.py
├── views/
│   ├── task_views.py
│   └── user_views.py
├── serializers/
│   └── serializers.py
└── urls.py
```

#### 3. DAZZLE: Lint Project

**Purpose**: Run extended linting for best practices

**How to Use**:
1. Open Command Palette
2. Type "DAZZLE: Lint"
3. Select "DAZZLE: Lint Project"
4. Terminal opens with lint results

**What It Checks**:
- Naming conventions
- Dead/unused modules
- Unused imports
- Code organization
- Best practices

**Example Output**:
```bash
$ dazzle lint
Running extended lint checks...

✓ No naming convention violations
⚠ 1 unused import found:
  - dsl/api.dsl: unused 'use myapp.auth'

✓ No dead modules
✓ No unreachable code

Lint complete: 1 warning, 0 errors
```

#### 4. DAZZLE: Analyze Specification

**Purpose**: Use AI to analyze natural language specifications

**Requirements**:
- LLM API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)
- Specification file open (usually `.md` or `.txt`)

**How to Use**:
1. Open a specification file (e.g., `SPEC.md`)
2. Open Command Palette
3. Type "DAZZLE: Analyze"
4. Select "DAZZLE: Analyze Specification"
5. Confirm cost estimate (if applicable)
6. Wait for analysis (progress shown)
7. View results in webview panel

**What It Does**:
- Extracts entities and their fields
- Identifies state machines
- Finds CRUD operations
- Detects business rules
- Generates clarifying questions
- Shows coverage statistics

**Example Workflow**:

**1. Create `SPEC.md`**:
```markdown
# Task Management System

## Overview
Build a task tracking system where users can create, assign,
and track tasks through different statuses.

## Requirements

### User Management
- Users must register with email and password
- Users have a name and profile picture
- Users can be assigned tasks

### Task Management
- Tasks have a title (required) and description
- Tasks can be assigned to a user
- Tasks have status: todo, in_progress, done
- Tasks have priority: low, medium, high
- Tasks track creation and update timestamps

### Task Lifecycle
When a task is created, it starts in "todo" status.
Users can move tasks to "in_progress" when working on them.
When complete, tasks move to "done" status.

## Questions
- Should tasks support comments?
- Do we need task categories/tags?
- Should tasks have due dates?
```

**2. Run Analysis**:
```
Analyzing specification with LLM...
├─ Extracting state machines and CRUD operations...
├─ Identifying entities...
├─ Detecting business rules...
└─ Generating clarifying questions...

Analysis complete!
```

**3. View Results**:
```
📊 Specification Analysis Results

Entities Found: 2
├─ User
│  ├─ email: str (required, unique)
│  ├─ password: str (required)
│  ├─ name: str
│  └─ profile_picture: str
└─ Task
   ├─ title: str (required)
   ├─ description: text
   ├─ status: enum [todo, in_progress, done]
   ├─ priority: enum [low, medium, high]
   ├─ assigned_to: ref User
   ├─ created_at: datetime
   └─ updated_at: datetime

State Machines: 1
├─ Task.status
   ├─ todo → in_progress
   ├─ in_progress → done
   └─ in_progress → todo

CRUD Operations:
├─ Task: Create, Read, Update, Delete
└─ User: Create, Read, Update

Clarifying Questions (3):
1. Task Comments (Priority: High)
   Q: Should tasks support comments?
   Options: Yes, No

2. Task Categories (Priority: Medium)
   Q: Do we need task categories/tags?
   Options: Yes, No

3. Due Dates (Priority: Medium)
   Q: Should tasks have due dates?
   Options: Yes, No
```

**4. Interactive Q&A** (if questions exist):
```
Continue with Q&A? [Yes] [No]

Task Comments (Priority: High)
Q: Should tasks support comments?
> Yes
< No

[Selected: Yes]

Task Categories (Priority: Medium)
Q: Do we need task categories/tags?
> Yes
< No

[Selected: No]
```

**5. Generate DSL** (Coming in v0.5):
Based on analysis and answers, generate complete DSL.

---

## LSP Features

The Language Server Protocol (LSP) provides intelligent code features.

### Prerequisites

LSP features require:
- DAZZLE Python package installed
- Python 3.11+ accessible
- LSP server can be imported: `python3 -c "import dazzle.lsp.server"`

### Feature 1: Hover Documentation

**What**: Show information when you hover over code

**How to Use**:
1. Open a `.dsl` file
2. Hover mouse over an entity name, field, or keyword
3. Tooltip appears with documentation

**Example**:

Hover over `uuid`:
```
uuid - Universally Unique Identifier
Type: UUID (RFC 4122)
Storage: 16 bytes
Format: 8-4-4-4-12 hex digits
Example: 550e8400-e29b-41d4-a716-446655440000
```

Hover over `Task` (entity name):
```
entity Task
Defined in: dsl/core.dsl:5
Fields: 7
References: 3 surfaces
```

Hover over `required`:
```
required - Field Modifier
Marks field as required/non-nullable
Database: NOT NULL constraint
Validation: Enforced at API level
```

### Feature 2: Go to Definition

**What**: Jump to where an entity or field is defined

**How to Use**:

**Method 1: Cmd+Click (Mac) / Ctrl+Click (Windows)**
1. Hold `Cmd` / `Ctrl`
2. Click on entity reference
3. Editor jumps to definition

**Method 2: Right-Click**
1. Right-click on entity reference
2. Select "Go to Definition"

**Method 3: F12 Key**
1. Place cursor on entity reference
2. Press `F12`

**Example**:

In `dsl/surfaces.dsl`:
```dsl
surface task_list "Task List":
  uses entity Task  # ← Cmd+Click on "Task"
  mode: list
```

Jumps to `dsl/core.dsl`:
```dsl
entity Task "Task":  # ← Cursor lands here
  id: uuid pk
  title: str(200) required
  # ...
```

### Feature 3: Autocomplete

**What**: Intelligent code completion as you type

**How to Use**:
1. Start typing
2. Suggestions appear automatically
3. Use arrow keys to select
4. Press `Enter` or `Tab` to accept

**Trigger Autocomplete Manually**:
- Press `Ctrl+Space`

**Example 1: Type Completion**

Type `st` in a field definition:
```dsl
entity User "User":
  name: st█
```

Suggestions appear:
```
str       String type
str(n)    String with max length
status    (from other entities)
```

Select `str` and continue:
```dsl
entity User "User":
  name: str(█
```

Type `100`:
```dsl
entity User "User":
  name: str(100) █
```

Suggestions for modifiers:
```
required  Make field required
unique    Add unique constraint
indexed   Create database index
default   Set default value
```

**Example 2: Keyword Completion**

Type `ent` at root level:
```
ent█
```

Suggestions:
```
entity           Define an entity
entity_ref       (if available)
```

**Example 3: Enum Values**

```dsl
entity Task "Task":
  status: enum[todo,in_progress,done]
  priority: enum[█
```

Suggestions might include common enum patterns:
```
low,medium,high
0,1,2,3
pending,approved,rejected
```

### Feature 4: Document Symbols

**What**: Outline view of DSL file structure

**How to Use**:

**Method 1: Outline View**
1. Open a `.dsl` file
2. Look at Explorer sidebar
3. Click "Outline" section
4. Browse file structure

**Method 2: Symbol Navigation**
1. Press `Cmd+Shift+O` (Mac) or `Ctrl+Shift+O` (Windows)
2. Type symbol name
3. Select to jump

**Example Outline**:
```
core.dsl
├─ module: myapp.core
├─ app: myapp
├─ Entities
│  ├─ Task
│  │  ├─ id: uuid
│  │  ├─ title: str(200)
│  │  ├─ status: enum
│  │  └─ priority: enum
│  └─ User
│     ├─ id: uuid
│     └─ email: str(200)
└─ Surfaces
   ├─ task_list
   └─ task_detail
```

Click any item to jump to that definition.

### Feature 5: Diagnostics

**What**: Real-time error checking as you type

**When**: As you type (or on save, depending on settings)

**Where**:
- Red squiggles in editor
- Problems panel (`Cmd+Shift+M` / `Ctrl+Shift+M`)
- Gutter icons (red × or yellow !)

**Example**:

Type:
```dsl
entity Task "Task":
  id: uuid pk
  owner: ref UnknownEntity  # ← Red squiggle appears
```

Problems panel shows:
```
Error: Unknown entity 'UnknownEntity'
File: dsl/core.dsl
Line: 3, Column: 14
```

Hover over red squiggle:
```
Unknown entity 'UnknownEntity'
Did you mean: User, Task, Project?
```

---

## LLM-Assisted Features

### Setting Up LLM Features

#### Step 1: Install LLM Dependencies

```bash
pip install "dazzle[llm]"
```

#### Step 2: Configure API Key

**For Anthropic (Recommended)**:
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

**For OpenAI**:
```bash
export OPENAI_API_KEY=sk-...
```

#### Step 3: Configure VS Code Settings

1. Open Settings (`Cmd+,` / `Ctrl+,`)
2. Search for "dazzle.llm"
3. Set provider: `anthropic` or `openai`
4. Set model: `claude-3-5-sonnet-20241022` (default) or `gpt-4-turbo`
5. Set max cost: `1.0` (USD)

### Using Spec Analysis

See [Commands: DAZZLE: Analyze Specification](#4-dazzle-analyze-specification) for detailed walkthrough.

**Quick Start**:
1. Create `SPEC.md` with requirements
2. Run "DAZZLE: Analyze Specification"
3. Review extracted entities and state machines
4. Answer clarifying questions
5. (Future) Generate DSL from analysis

---

## Configuration

### Accessing Settings

1. Press `Cmd+,` (Mac) or `Ctrl+,` (Windows/Linux)
2. Search for "dazzle"
3. Modify settings as needed

### Available Settings

#### General Settings

##### `dazzle.cliPath`
- **Type**: String
- **Default**: `"dazzle"`
- **Description**: Path to DAZZLE CLI executable

**Examples**:
```json
// Use dazzle from PATH
"dazzle.cliPath": "dazzle"

// Use absolute path
"dazzle.cliPath": "/usr/local/bin/dazzle"

// Use Python module (legacy)
"dazzle.cliPath": "python3 -m dazzle.cli"
```

##### `dazzle.manifest`
- **Type**: String
- **Default**: `"dazzle.toml"`
- **Description**: Name of the DAZZLE manifest file

**Examples**:
```json
// Standard
"dazzle.manifest": "dazzle.toml"

// Custom name
"dazzle.manifest": "project.toml"
```

##### `dazzle.validateOnSave`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Automatically validate on file save

**Examples**:
```json
// Enable auto-validation (default)
"dazzle.validateOnSave": true

// Disable auto-validation (manual only)
"dazzle.validateOnSave": false
```

##### `dazzle.pythonPath`
- **Type**: String
- **Default**: `""` (auto-detect)
- **Description**: Python interpreter path for LSP server

**Examples**:
```json
// Auto-detect (recommended)
"dazzle.pythonPath": ""

// Explicit path
"dazzle.pythonPath": "/usr/local/bin/python3"

// Virtual environment
"dazzle.pythonPath": "/path/to/venv/bin/python"
```

#### LLM Settings

##### `dazzle.llm.provider`
- **Type**: String (enum)
- **Default**: `"anthropic"`
- **Options**: `"anthropic"`, `"openai"`
- **Description**: LLM provider for spec analysis

##### `dazzle.llm.model`
- **Type**: String
- **Default**: `"claude-3-5-sonnet-20241022"`
- **Description**: Model to use for analysis

**Examples**:
```json
// Anthropic models
"dazzle.llm.model": "claude-3-5-sonnet-20241022"
"dazzle.llm.model": "claude-3-opus-20240229"

// OpenAI models
"dazzle.llm.model": "gpt-4-turbo"
"dazzle.llm.model": "gpt-4o"
```

##### `dazzle.llm.maxCostPerAnalysis`
- **Type**: Number
- **Default**: `1.0`
- **Description**: Maximum cost in USD per spec analysis

### Example Configuration

**settings.json**:
```json
{
  "dazzle.cliPath": "dazzle",
  "dazzle.validateOnSave": true,
  "dazzle.pythonPath": "",
  "dazzle.llm.provider": "anthropic",
  "dazzle.llm.model": "claude-3-5-sonnet-20241022",
  "dazzle.llm.maxCostPerAnalysis": 1.0
}
```

---

## Troubleshooting

### Issue 1: Command 'dazzle' not found

**Symptom**:
- Commands fail with "command not found"
- Output shows: `Failed to run DAZZLE CLI: spawn dazzle ENOENT`

**Diagnosis**:
```bash
# Check if dazzle is installed
which dazzle   # Mac/Linux
where dazzle   # Windows

# Expected: /path/to/dazzle
# If not found: DAZZLE not installed
```

**Solution**:
```bash
# Install DAZZLE
pip install dazzle

# Verify installation
dazzle --help

# If still not working, find installation path
pip show dazzle

# Configure explicit path in VS Code settings
# Settings → dazzle.cliPath → "/path/to/dazzle"
```

### Issue 2: LSP Features Not Working

**Symptom**:
- No hover tooltips
- No autocomplete
- No go-to-definition
- Warning: "DAZZLE LSP server not found"

**Diagnosis**:
```bash
# Check if LSP module is available
python3 -c "import dazzle.lsp.server; print('OK')"

# Expected: OK
# If error: ModuleNotFoundError: No module named 'dazzle'
```

**Solution**:
```bash
# Install DAZZLE in Python environment
pip install dazzle

# If using virtual environment, activate it first
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
pip install dazzle

# Configure Python path in VS Code
# Settings → dazzle.pythonPath → "/path/to/python"
```

**Check LSP Output**:
1. Open Output panel: `View` → `Output`
2. Select "DAZZLE LSP" from dropdown
3. Look for error messages
4. Common errors:
   - "ModuleNotFoundError" → Install dazzle
   - "Connection refused" → Check Python path
   - "Timeout" → LSP server crashed

### Issue 3: Validation Not Showing Errors

**Symptom**:
- Save file, but no errors/warnings in Problems panel
- Output shows "Running validation" but no results

**Diagnosis**:
```bash
# Check if validation works from command line
cd /path/to/project
dazzle validate

# Does it show errors?
```

**Solutions**:

**A. No `dazzle.toml` in workspace**:
```bash
# Check for manifest file
ls dazzle.toml

# If not found, initialize project
dazzle init
```

**B. Wrong working directory**:
1. Check VS Code opened the correct folder
2. Workspace folder must contain `dazzle.toml`
3. Don't open parent or child directory

**C. Validation disabled**:
1. Settings → Search "dazzle validate"
2. Enable "Dazzle: Validate On Save"
3. Or run manually: `Cmd+Shift+P` → "DAZZLE: Validate"

**D. CLI not producing correct output format**:
```bash
# Test validation output format
dazzle validate --format vscode

# Expected format:
# file:line:col: severity: message
# Example: dsl/core.dsl:15:10: error: Unknown entity 'X'
```

### Issue 4: Extension Not Activating

**Symptom**:
- No DAZZLE commands in palette
- No syntax highlighting
- Extension not in Extensions list

**Diagnosis**:
1. Press `Cmd+Shift+X` / `Ctrl+Shift+X`
2. Search for "DAZZLE"
3. Check if installed

**Solutions**:

**A. Extension not installed**:
- Follow [Installation](#installation) steps

**B. Extension disabled**:
1. Extensions panel → DAZZLE DSL
2. Click "Enable"

**C. VS Code too old**:
- Update VS Code to 1.80.0 or higher
- Help → Check for Updates

**D. Extension error on activation**:
1. Help → Toggle Developer Tools
2. Console tab
3. Look for DAZZLE-related errors
4. Report issue with error message

### Issue 5: LLM Features Not Working

**Symptom**:
- "DAZZLE: Analyze Specification" command fails
- Error: "No LLM API key configured"

**Diagnosis**:
```bash
# Check environment variables
echo $ANTHROPIC_API_KEY  # Mac/Linux
echo %ANTHROPIC_API_KEY%  # Windows

# Should print: sk-ant-api03-...
```

**Solutions**:

**A. API key not set**:
```bash
# Set in shell profile (~/.bashrc, ~/.zshrc)
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Or set in VS Code terminal
# Restart VS Code after setting
```

**B. Dependencies not installed**:
```bash
# Install LLM dependencies
pip install "dazzle[llm]"

# Verify
python3 -c "import anthropic; print('OK')"
```

**C. Cost limit too low**:
1. Settings → Search "dazzle.llm.maxCost"
2. Increase value: `2.0` or `5.0`
3. Retry analysis

### Issue 6: Slow Performance

**Symptom**:
- Editor lags when typing
- Validation takes too long
- LSP server slow to respond

**Solutions**:

**A. Disable auto-validation**:
```json
"dazzle.validateOnSave": false
```
Then validate manually when needed.

**B. Large project optimization**:
- Split DSL into smaller modules
- Reduce file watchers scope
- Close unused `.dsl` files

**C. LSP server issues**:
1. Restart LSP: `Cmd+Shift+P` → "Reload Window"
2. Check LSP output for errors
3. Disable LSP if not needed

### Issue 7: Syntax Highlighting Wrong

**Symptom**:
- Colors are incorrect
- Keywords not highlighted
- Everything is one color

**Solutions**:

**A. Check file extension**:
- File must end with `.dsl` or `.dazzle`
- Rename if needed: `mv file.txt file.dsl`

**B. Force language mode**:
1. Bottom-right of status bar
2. Click language mode (currently "Plain Text")
3. Select "DAZZLE" or search for it

**C. Theme compatibility**:
- Some themes may not show DSL colors well
- Try a different theme: `Cmd+K Cmd+T`
- Recommended: Dark+ (default dark), Light+ (default light)

### Getting Help

If issues persist:

1. **Check Documentation**: Read this guide and README
2. **Check Output Channels**:
   - View → Output → "DAZZLE"
   - View → Output → "DAZZLE LSP"
3. **Developer Tools**: Help → Toggle Developer Tools
4. **GitHub Issues**: Report at https://github.com/dazzle/dazzle/issues
5. **Include**:
   - VS Code version
   - Extension version
   - DAZZLE CLI version (`dazzle --version`)
   - Operating system
   - Error messages from Output channels
   - Steps to reproduce

---

## UAT Test Scenarios

This section provides test scenarios for user acceptance testing.

### UAT-001: Installation Verification

**Objective**: Verify extension can be installed and activated

**Prerequisites**: VS Code 1.80.0+, DAZZLE CLI installed

**Steps**:
1. Install extension using preferred method
2. Restart VS Code
3. Open Command Palette
4. Type "DAZZLE"

**Expected Results**:
- ✓ Extension appears in Extensions list
- ✓ Status bar shows extension loaded (if configured)
- ✓ DAZZLE commands appear in palette
- ✓ No error notifications

**Pass Criteria**: All expected results achieved

---

### UAT-002: Syntax Highlighting

**Objective**: Verify DSL files are properly highlighted

**Steps**:
1. Create new file: `test.dsl`
2. Paste the following content:
```dsl
module test.highlighting

app myapp "My App"

entity User "User":
  id: uuid pk
  name: str(100) required
  email: str(200) unique
  created_at: datetime auto_add
```
3. Observe syntax coloring

**Expected Results**:
- ✓ Keywords (`module`, `app`, `entity`) are colored (purple/blue)
- ✓ Types (`uuid`, `str`, `datetime`) are colored (teal/cyan)
- ✓ Modifiers (`pk`, `required`, `unique`) are colored (yellow/gold)
- ✓ Strings (`"User"`, `"My App"`) are colored (green)
- ✓ Numbers (`100`, `200`) are colored (orange/green)

**Pass Criteria**: All syntax elements properly colored

---

### UAT-003: Basic Validation (Success)

**Objective**: Verify successful validation with no errors

**Steps**:
1. Create/open DAZZLE project with `dazzle.toml`
2. Create `dsl/valid.dsl`:
```dsl
module test.valid

app test "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
```
3. Save file
4. Open Problems panel (`Cmd+Shift+M`)
5. Check Output → "DAZZLE"

**Expected Results**:
- ✓ Problems panel shows 0 problems
- ✓ Output shows "No issues found ✓"
- ✓ No red squiggles in editor

**Pass Criteria**: Clean validation with no errors

---

### UAT-004: Basic Validation (Errors)

**Objective**: Verify errors are detected and displayed

**Steps**:
1. Create `dsl/invalid.dsl`:
```dsl
module test.invalid

app test "Test App"

entity User "User":
  id: uuid pk

surface user_list "Users":
  uses entity UnknownEntity
  mode: list
```
2. Save file
3. Check Problems panel

**Expected Results**:
- ✓ Problems panel shows 1 error
- ✓ Error message: "Unknown entity 'UnknownEntity'"
- ✓ Error shows correct file and line number
- ✓ Red squiggle under `UnknownEntity` in editor
- ✓ Clicking error navigates to line

**Pass Criteria**: Error detected and correctly displayed

---

### UAT-005: Auto-Validation on Save

**Objective**: Verify validation runs automatically on save

**Steps**:
1. Ensure setting: `"dazzle.validateOnSave": true`
2. Open `dsl/test.dsl`
3. Add an error (reference to unknown entity)
4. Save file (`Cmd+S`)
5. Observe Problems panel updates

**Expected Results**:
- ✓ Problems panel updates immediately after save
- ✓ New error appears
- ✓ Output channel shows validation ran
- ✓ Timestamp in output is current

**Pass Criteria**: Auto-validation works on save

---

### UAT-006: Manual Validation Command

**Objective**: Verify manual validation command works

**Steps**:
1. Disable auto-validation: `"dazzle.validateOnSave": false`
2. Make changes to DSL file with errors
3. Save file (validation should not run)
4. Open Command Palette
5. Run "DAZZLE: Validate Project"
6. Wait for completion

**Expected Results**:
- ✓ Progress notification shows "Validating project..."
- ✓ Validation completes
- ✓ Problems panel updates with results
- ✓ Output channel shows validation executed

**Pass Criteria**: Manual validation works correctly

---

### UAT-007: Build Command

**Objective**: Verify build command executes

**Prerequisites**: Valid DAZZLE project

**Steps**:
1. Open Command Palette
2. Run "DAZZLE: Build Project"
3. Observe terminal opens
4. Follow prompts if any

**Expected Results**:
- ✓ New terminal opens with title "DAZZLE Build"
- ✓ Terminal shows `dazzle build` command
- ✓ Build process runs (or prompts for stack)
- ✓ Can interact with terminal

**Pass Criteria**: Build command executes in terminal

---

### UAT-008: Lint Command

**Objective**: Verify lint command executes

**Steps**:
1. Open Command Palette
2. Run "DAZZLE: Lint Project"
3. Observe terminal

**Expected Results**:
- ✓ Terminal opens with title "DAZZLE Lint"
- ✓ Terminal shows `dazzle lint` command
- ✓ Lint output appears
- ✓ Shows any warnings or errors

**Pass Criteria**: Lint command executes successfully

---

### UAT-009: LSP Hover

**Objective**: Verify hover documentation works

**Prerequisites**: LSP server available

**Steps**:
1. Open DSL file with entity
2. Hover mouse over type keyword (e.g., `uuid`)
3. Observe tooltip
4. Hover over entity name
5. Observe tooltip

**Expected Results**:
- ✓ Tooltip appears on hover
- ✓ Shows documentation for hovered item
- ✓ Formatting is readable
- ✓ No errors in LSP output channel

**Pass Criteria**: Hover shows relevant documentation

---

### UAT-010: LSP Go to Definition

**Objective**: Verify go-to-definition works

**Steps**:
1. Create two files:

`dsl/entities.dsl`:
```dsl
module test.entities

entity User "User":
  id: uuid pk
```

`dsl/surfaces.dsl`:
```dsl
module test.surfaces

use test.entities

surface user_list "Users":
  uses entity User
  mode: list
```

2. Open `surfaces.dsl`
3. Cmd+Click (Mac) or Ctrl+Click (Windows) on `User`

**Expected Results**:
- ✓ Editor jumps to `entities.dsl`
- ✓ Cursor positioned at `entity User` line
- ✓ Definition is highlighted

**Pass Criteria**: Navigation to definition works

---

### UAT-011: LSP Autocomplete

**Objective**: Verify autocomplete suggestions work

**Steps**:
1. Open DSL file
2. In entity definition, start typing field type:
```dsl
entity Test "Test":
  id: uu
```
3. Observe autocomplete suggestions
4. Accept suggestion

**Expected Results**:
- ✓ Autocomplete popup appears
- ✓ Shows relevant suggestions (e.g., `uuid`)
- ✓ Can navigate with arrow keys
- ✓ Enter/Tab accepts suggestion
- ✓ Accepted text is inserted

**Pass Criteria**: Autocomplete works and inserts correctly

---

### UAT-012: Document Symbols

**Objective**: Verify document outline works

**Steps**:
1. Open DSL file with multiple entities
2. Open Explorer sidebar
3. Expand "Outline" section
4. Click on an entity in outline

**Expected Results**:
- ✓ Outline shows file structure
- ✓ Entities are listed
- ✓ Fields are nested under entities
- ✓ Clicking navigates to definition

**Pass Criteria**: Outline view populates and navigation works

---

### UAT-013: File Watchers

**Objective**: Verify file watchers detect changes

**Steps**:
1. Open DAZZLE project
2. Enable auto-validation
3. Create new `.dsl` file
4. Check Output channel
5. Modify existing `.dsl` file
6. Check Output channel
7. Delete `.dsl` file
8. Check Output channel

**Expected Results**:
- ✓ Creating file triggers validation
- ✓ Modifying file triggers validation
- ✓ Deleting file triggers validation
- ✓ Output shows all validation runs
- ✓ Problems panel updates each time

**Pass Criteria**: All file system events trigger validation

---

### UAT-014: LLM Spec Analysis (Basic)

**Objective**: Verify spec analysis command works

**Prerequisites**:
- LLM API key configured
- `dazzle[llm]` installed

**Steps**:
1. Create `SPEC.md`:
```markdown
# Simple App

Users can create and view tasks.

Tasks have:
- Title (required)
- Description
- Status: todo, done
```
2. Open `SPEC.md`
3. Run "DAZZLE: Analyze Specification"
4. Confirm cost if prompted
5. Wait for analysis

**Expected Results**:
- ✓ Progress notification shows
- ✓ Analysis completes without errors
- ✓ Webview panel opens with results
- ✓ Shows extracted entities
- ✓ Shows identified fields
- ✓ Shows state machines (if any)

**Pass Criteria**: Analysis completes and shows results

---

### UAT-015: LLM Q&A Workflow

**Objective**: Verify interactive Q&A works

**Prerequisites**: Same as UAT-014

**Steps**:
1. Run spec analysis on file with ambiguities
2. Wait for analysis
3. If questions appear, proceed with Q&A
4. Answer questions using QuickPick
5. Complete Q&A workflow

**Expected Results**:
- ✓ Questions appear in QuickPick dialog
- ✓ Can select answers
- ✓ Can navigate between questions
- ✓ Can cancel Q&A
- ✓ Answers are recorded

**Pass Criteria**: Q&A interaction works smoothly

---

### UAT-016: Configuration Changes

**Objective**: Verify settings can be changed and take effect

**Steps**:
1. Open Settings
2. Change `dazzle.cliPath` to custom value
3. Save settings
4. Run validation command
5. Check Output for command executed

**Expected Results**:
- ✓ Settings save without errors
- ✓ New CLI path is used
- ✓ Output shows correct command

**Pass Criteria**: Configuration changes apply

---

### UAT-017: Error Recovery

**Objective**: Verify extension handles errors gracefully

**Steps**:
1. Set `dazzle.cliPath` to invalid value: `/nonexistent/dazzle`
2. Run validation command
3. Observe error handling

**Expected Results**:
- ✓ Error notification appears
- ✓ Error message is clear and helpful
- ✓ Extension doesn't crash
- ✓ Can fix setting and retry

**Pass Criteria**: Errors handled gracefully

---

### UAT-018: Multi-Module Project

**Objective**: Verify extension works with multi-module projects

**Steps**:
1. Create project with multiple modules:

`dsl/core.dsl`:
```dsl
module myapp.core

entity User "User":
  id: uuid pk
```

`dsl/api.dsl`:
```dsl
module myapp.api

use myapp.core

surface user_api "User API":
  uses entity User
  mode: list
```

2. Save both files
3. Run validation

**Expected Results**:
- ✓ Both files validate
- ✓ Cross-module references work
- ✓ Go-to-definition works across files
- ✓ No errors for `use` directive

**Pass Criteria**: Multi-module support works

---

### UAT-019: Large File Performance

**Objective**: Verify performance with large DSL files

**Steps**:
1. Create DSL file with 50+ entities
2. Open file
3. Type and edit
4. Save file
5. Observe responsiveness

**Expected Results**:
- ✓ File opens quickly (< 2 seconds)
- ✓ Typing is responsive (no lag)
- ✓ Syntax highlighting works
- ✓ Validation completes in reasonable time (< 5 seconds)
- ✓ LSP features still work

**Pass Criteria**: Acceptable performance with large files

---

### UAT-020: Theme Compatibility

**Objective**: Verify syntax highlighting works with different themes

**Steps**:
1. Open DSL file
2. Switch to Dark+ theme
3. Observe highlighting
4. Switch to Light+ theme
5. Observe highlighting
6. Switch to high-contrast theme
7. Observe highlighting

**Expected Results**:
- ✓ Highlighting visible in all themes
- ✓ Colors are appropriate for theme
- ✓ Good contrast and readability

**Pass Criteria**: Works well with major themes

---

## UAT Summary Checklist

Use this checklist to track UAT progress:

### Installation & Setup
- [ ] UAT-001: Installation Verification
- [ ] UAT-016: Configuration Changes

### Syntax & Display
- [ ] UAT-002: Syntax Highlighting
- [ ] UAT-020: Theme Compatibility

### Validation
- [ ] UAT-003: Basic Validation (Success)
- [ ] UAT-004: Basic Validation (Errors)
- [ ] UAT-005: Auto-Validation on Save
- [ ] UAT-006: Manual Validation Command

### Commands
- [ ] UAT-007: Build Command
- [ ] UAT-008: Lint Command

### LSP Features
- [ ] UAT-009: LSP Hover
- [ ] UAT-010: LSP Go to Definition
- [ ] UAT-011: LSP Autocomplete
- [ ] UAT-012: Document Symbols

### Advanced Features
- [ ] UAT-013: File Watchers
- [ ] UAT-014: LLM Spec Analysis (Basic)
- [ ] UAT-015: LLM Q&A Workflow

### Error Handling & Edge Cases
- [ ] UAT-017: Error Recovery
- [ ] UAT-018: Multi-Module Project
- [ ] UAT-019: Large File Performance

### UAT Sign-Off

**Tester Name**: ___________________________
**Date**: ___________________________
**Test Environment**:
- VS Code Version: ___________________________
- Extension Version: ___________________________
- DAZZLE Version: ___________________________
- Operating System: ___________________________

**Overall Result**: ⬜ PASS  ⬜ FAIL  ⬜ PASS WITH ISSUES

**Notes**:
_____________________________________________________________
_____________________________________________________________
_____________________________________________________________

**Critical Issues Found**:
_____________________________________________________________
_____________________________________________________________

**Minor Issues Found**:
_____________________________________________________________
_____________________________________________________________

**Recommendations**:
_____________________________________________________________
_____________________________________________________________

---

## Appendix: Keyboard Shortcuts

### Default Shortcuts

| Action | Mac | Windows/Linux |
|--------|-----|---------------|
| Command Palette | `Cmd+Shift+P` | `Ctrl+Shift+P` |
| Go to Definition | `F12` or `Cmd+Click` | `F12` or `Ctrl+Click` |
| Peek Definition | `Opt+F12` | `Alt+F12` |
| Show Hover | Hover mouse | Hover mouse |
| Trigger Autocomplete | `Ctrl+Space` | `Ctrl+Space` |
| Problems Panel | `Cmd+Shift+M` | `Ctrl+Shift+M` |
| Symbol Search | `Cmd+Shift+O` | `Ctrl+Shift+O` |
| Settings | `Cmd+,` | `Ctrl+,` |
| Save File | `Cmd+S` | `Ctrl+S` |

### Custom Shortcuts

You can set custom shortcuts for DAZZLE commands:

1. Press `Cmd+K Cmd+S` (Mac) or `Ctrl+K Ctrl+S` (Windows)
2. Search for "DAZZLE"
3. Click + icon to add shortcut
4. Press desired key combination

**Recommended Custom Shortcuts**:
- Validate Project: `Cmd+Shift+V` / `Ctrl+Shift+V`
- Build Project: `Cmd+Shift+B` / `Ctrl+Shift+B`
- Analyze Spec: `Cmd+Shift+A` / `Ctrl+Shift+A`

---

## Appendix: Common DSL Patterns

### Pattern 1: Basic CRUD Entity

```dsl
entity Product "Product":
  id: uuid pk
  name: str(200) required
  description: text
  price: float required
  stock: int default=0
  active: bool default=true
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

### Pattern 2: Entity with Relationships

```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required
  items: ref OrderItem many
  status: enum[pending,confirmed,shipped,delivered]
  total: float required
  created_at: datetime auto_add
```

### Pattern 3: List Surface

```dsl
surface product_list "Product List":
  uses entity Product
  mode: list

  section main "Products":
    field name "Product Name"
    field price "Price"
    field stock "In Stock"
    field active "Active"
```

### Pattern 4: Form Surface

```dsl
surface product_form "Product Form":
  uses entity Product
  mode: form

  section details "Product Details":
    field name "Name"
    field description "Description"
    field price "Price"
    field stock "Stock Quantity"

  section settings "Settings":
    field active "Active"
```

### Pattern 5: State Machine

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium

experience ticket_lifecycle "Ticket Lifecycle":
  uses entity Ticket

  step open "New Ticket":
    transition start_work "Start Working" to in_progress
    transition close "Close Ticket" to closed

  step in_progress "Working on Ticket":
    transition resolve "Resolve" to resolved
    transition reopen "Reopen" to open

  step resolved "Resolved":
    transition close "Close" to closed
    transition reopen "Reopen" to open

  step closed "Closed":
    final
```

---

**End of User Guide**

For more information, see:
- Main README: `/README.md`
- DSL Reference: `/docs/DAZZLE_DSL_REFERENCE_0_1.md`
- Extension README: `/extensions/vscode/README.md`
- GitHub Issues: https://github.com/dazzle/dazzle/issues
