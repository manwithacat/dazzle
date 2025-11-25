# DAZZLE Init Command UX Improvement

**Date**: 2025-11-23
**Issue**: Confusing `dazzle init` behavior
**Status**: Proposed Fix

## Problem Statement

The `dazzle init` command has confusing UX that doesn't match user expectations:

### Current Behavior

```bash
# User creates directory
mkdir my-project
cd my-project

# User tries to initialize (like git init)
dazzle init
# Error: Missing argument 'PATH'.
# Use: dazzle init ./my-project

# User tries current directory
dazzle init .
# Error: Initialization failed: Directory already exists: /path/to/my-project
```

### User Expectations

Users expect `dazzle init` to behave like `git init`:
- `git init` → Initializes in current directory
- `git clone <url>` → Creates new directory

But `dazzle init` behaves more like `git clone`:
- Requires a path argument
- Creates new directory
- Fails if directory exists

### Root Cause

1. **`cli.py:133-137`**: Requires `path` argument, shows error if not provided
2. **`init.py:121-122`**: `copy_template()` raises `InitError` if target directory exists
3. **Help text**: Says "Initialize a new DAZZLE project in a NEW directory" (line 103)

## User Research

### Common Workflows

**Workflow 1: Start from scratch** (Most common)
```bash
mkdir my-app
cd my-app
dazzle init  # Expected to work, currently fails
```

**Workflow 2: Init from outside**
```bash
dazzle init ./my-app  # Works, but creates my-app/
cd my-app
```

**Workflow 3: Clone example**
```bash
dazzle clone simple_task  # Works, different command
```

### Comparison with Other Tools

| Tool | Command | Behavior |
|------|---------|----------|
| `git` | `git init` | Initializes in current dir |
| `npm` | `npm init` | Initializes in current dir |
| `cargo` | `cargo init` | Initializes in current dir |
| `go` | `go mod init` | Initializes in current dir |
| `poetry` | `poetry init` | Initializes in current dir |
| **dazzle** | `dazzle init` | **Requires path argument** ❌ |

**Conclusion**: DAZZLE is the outlier. Standard practice is `init` works in current directory.

## Proposed Solution

### Option 1: Simple Fix (Recommended)

Make `path` argument optional and default to current directory when:
1. No path provided
2. Current directory is empty OR
3. User confirms with `--here` flag

```bash
# New behavior
mkdir my-app
cd my-app
dazzle init              # Works! Initializes in current dir (if empty)

# Or explicitly
cd non-empty-dir
dazzle init --here       # Force init in current dir

# Old behavior still works
dazzle init ./new-app    # Creates new-app/ directory
```

### Option 2: Dual Commands

Split into two commands:
- `dazzle init` → Initialize in current directory
- `dazzle new <path>` → Create new directory and initialize

```bash
cd my-app
dazzle init              # Initializes here

# Or
dazzle new ./other-app   # Creates and initializes new dir
```

### Option 3: Interactive Prompt

If ambiguous, prompt user:

```bash
$ dazzle init
Directory /Users/you/my-app already exists.
What would you like to do?
  1) Initialize here (current directory)
  2) Create new directory
  3) Cancel
>
```

## Recommended Solution: Option 1 + Better Errors

### Implementation Plan

#### 1. Modify `cli.py` init command

```python
@app.command()
def init(
    path: Optional[str] = typer.Argument(
        None,
        help="Directory to create project in (defaults to current directory if empty)"
    ),
    from_example: Optional[str] = typer.Option(None, ...),
    name: Optional[str] = typer.Option(None, ...),
    title: Optional[str] = typer.Option(None, ...),
    here: bool = typer.Option(
        False,
        "--here",
        help="Initialize in current directory even if not empty"
    ),
    list_examples_flag: bool = typer.Option(False, ...),
    no_llm: bool = typer.Option(False, ...),
    no_git: bool = typer.Option(False, ...),
) -> None:
    """
    Initialize a new DAZZLE project.

    By default, initializes in current directory if it's empty,
    or creates a new directory if a path is provided.

    Creates project structure with:
    - dazzle.toml manifest
    - dsl/ directory with starter module
    - README.md with getting started guide
    - .gitignore and git repository (unless --no-git)
    - LLM context files for AI assistants (unless --no-llm)

    Examples:
        dazzle init                              # Init in current dir (if empty)
        dazzle init --here                       # Force init in current dir
        dazzle init ./my-project                 # Create new directory
        dazzle init --from simple_task           # Init from example
        dazzle init ./my-app --from support_tickets  # Create new dir from example
        dazzle init --list                       # Show available examples
    """
    if list_examples_flag:
        # ... existing code ...
        return

    # Determine target directory
    if path is None:
        # No path provided, use current directory
        target = Path(".").resolve()

        # Check if current directory is suitable
        if not _is_directory_empty(target) and not here:
            # Directory is not empty
            typer.echo(f"Error: Current directory is not empty: {target}", err=True)
            typer.echo("", err=True)
            typer.echo("Options:", err=True)
            typer.echo("  1. Initialize anyway:  dazzle init --here", err=True)
            typer.echo("  2. Create new dir:     dazzle init ./my-project", err=True)
            typer.echo("  3. Empty current dir:  rm -rf * .* (be careful!)", err=True)
            raise typer.Exit(code=1)
    else:
        # Path provided, create new directory
        target = Path(path).resolve()

    # ... rest of existing init code ...
```

#### 2. Add helper function

```python
def _is_directory_empty(directory: Path) -> bool:
    """
    Check if directory is empty (or has only hidden files we create).

    A directory is considered "empty" for init purposes if it contains:
    - No files at all, OR
    - Only .git directory, OR
    - Only .git and common ignore files (.gitignore, etc.)
    """
    if not directory.exists():
        return True

    contents = list(directory.iterdir())

    if len(contents) == 0:
        return True

    # Allow some common files that might be pre-created
    allowed_files = {'.git', '.gitignore', 'README.md', 'LICENSE', '.DS_Store'}
    actual_files = {item.name for item in contents}

    # If all files are in allowed list, consider it empty
    if actual_files.issubset(allowed_files):
        return True

    return False
```

#### 3. Update `init.py` copy_template function

```python
def copy_template(
    template_dir: Path,
    target_dir: Path,
    variables: Optional[dict[str, str]] = None,
    allow_existing: bool = False,
) -> None:
    """
    Copy a template directory to target, substituting variables.

    Args:
        template_dir: Source template directory
        target_dir: Destination directory
        variables: Optional dict for template variable substitution
        allow_existing: If True, allow target_dir to exist (init in place)

    Raises:
        InitError: If target exists (and allow_existing=False) or copy fails
    """
    if target_dir.exists() and not allow_existing:
        raise InitError(f"Directory already exists: {target_dir}")

    if not template_dir.exists():
        raise InitError(f"Template not found: {template_dir}")

    variables = variables or {}

    try:
        # Create target directory if needed
        target_dir.mkdir(parents=True, exist_ok=allow_existing)

        # Copy all files, substituting variables
        for src_path in template_dir.rglob("*"):
            if src_path.is_file():
                # Compute relative path
                rel_path = src_path.relative_to(template_dir)
                dst_path = target_dir / rel_path

                # Skip if file already exists (when allow_existing=True)
                if allow_existing and dst_path.exists():
                    continue

                # Create parent directories
                dst_path.parent.mkdir(parents=True, exist_ok=True)

                # Read, substitute, and write
                try:
                    content = src_path.read_text(encoding="utf-8")
                    content = substitute_template_vars(content, variables)
                    dst_path.write_text(content, encoding="utf-8")
                except UnicodeDecodeError:
                    # Binary file, just copy
                    shutil.copy2(src_path, dst_path)

    except Exception as e:
        # Clean up on failure (only if we created the directory)
        if target_dir.exists() and not allow_existing:
            shutil.rmtree(target_dir, ignore_errors=True)
        raise InitError(f"Failed to copy template: {e}") from e
```

#### 4. Update init_project signature

```python
def init_project(
    target_dir: Path,
    project_name: Optional[str] = None,
    from_example: Optional[str] = None,
    title: Optional[str] = None,
    no_llm: bool = False,
    no_git: bool = False,
    stack_name: Optional[str] = None,
    allow_existing: bool = False,  # NEW
) -> None:
    """
    Initialize a new DAZZLE project.

    Args:
        target_dir: Directory to create project in
        project_name: Project name (defaults to directory name)
        from_example: Optional example to copy from (e.g., "simple_task")
        title: Optional human-readable title (defaults to project_name)
        no_llm: If True, skip LLM instrumentation (default: False)
        no_git: If True, skip git initialization (default: False)
        stack_name: Optional stack name to include in LLM context
        allow_existing: If True, allow initializing in existing directory

    Raises:
        InitError: If initialization fails
    """
    # ... existing code ...

    # Copy template
    copy_template(template_dir, target_dir, variables, allow_existing=allow_existing)

    # ... rest of existing code ...
```

## Error Message Improvements

### Before

```bash
$ dazzle init
Error: Missing argument 'PATH'.
Use: dazzle init ./my-project
Or: dazzle init --list
```

### After

```bash
$ dazzle init
Initializing DAZZLE project in current directory...

$ dazzle init  # (when dir not empty)
Error: Current directory is not empty: /Users/you/my-project

Options:
  1. Initialize anyway:  dazzle init --here
  2. Create new dir:     dazzle init ./my-project
  3. Empty current dir:  rm -rf * .* (be careful!)

Current directory contains:
  - dsl/
  - old_files/
  - README.md

Tip: Use --here to initialize anyway (will not overwrite existing files)
```

## Updated Documentation

### Command Help

```
dazzle init [PATH] [OPTIONS]

Initialize a new DAZZLE project.

By default, initializes in current directory if it's empty.
If a path is provided, creates a new directory at that path.

ARGUMENTS:
  [PATH]  Directory to create project in (defaults to current directory)

OPTIONS:
  --here              Force initialization in current directory
  --from EXAMPLE      Copy from example (simple_task, support_tickets)
  --name NAME         Project name (defaults to directory name)
  --title TITLE       Project title (defaults to name in Title Case)
  --list, -l          List available examples
  --no-llm            Skip LLM instrumentation files
  --no-git            Skip git repository initialization

EXAMPLES:
  dazzle init                              # Init in current dir (if empty)
  dazzle init --here                       # Force init in current dir
  dazzle init ./my-project                 # Create new directory
  dazzle init --from simple_task           # Init from example (current dir)
  dazzle init ./my-app --from support_tickets  # New dir from example
  dazzle init --list                       # Show available examples

WORKFLOWS:
  Start new project:
    mkdir my-app && cd my-app
    dazzle init

  Init in existing empty directory:
    cd existing-project
    dazzle init

  Create new directory:
    dazzle init ./new-project
```

## Migration Guide

### For Existing Users

Old command | New equivalent | Notes
------------|---------------|-------
`dazzle init ./my-project` | Same | Still works
`dazzle init .` | `dazzle init` or `dazzle init --here` | Simplified
N/A | `dazzle init` | New: init in current dir

### For Documentation

Update all examples from:
```bash
dazzle init ./my-project
cd my-project
```

To:
```bash
mkdir my-project
cd my-project
dazzle init
```

Or just:
```bash
mkdir my-project && cd my-project && dazzle init
```

## Testing Checklist

- [ ] `dazzle init` in empty directory → Success
- [ ] `dazzle init` in non-empty directory → Error with helpful message
- [ ] `dazzle init --here` in non-empty directory → Success
- [ ] `dazzle init ./new-dir` → Creates new directory
- [ ] `dazzle init ./existing-dir` → Error (dir exists)
- [ ] `dazzle init --from simple_task` → Init from example in current dir
- [ ] `dazzle init ./new-dir --from simple_task` → Create new dir from example
- [ ] `dazzle init` in directory with only .git → Success (considered empty)
- [ ] `dazzle init` in directory with .git and README.md → Success
- [ ] Error messages are clear and actionable
- [ ] Help text is accurate

## Benefits

1. **Matches user expectations**: Aligns with git, npm, cargo, etc.
2. **Less typing**: `dazzle init` instead of `dazzle init .`
3. **Better errors**: Clear, actionable error messages
4. **Flexibility**: Both workflows supported (current dir and new dir)
5. **Safety**: Won't overwrite existing files without --here flag
6. **Backwards compatible**: Old usage still works

## Risks

1. **Breaking change**: Users who scripted `dazzle init ./path` might be affected
   - **Mitigation**: Old usage still works, no breaking change
2. **Confusion**: Users might accidentally init in wrong directory
   - **Mitigation**: Confirm before init, show full path in output
3. **File conflicts**: Init in non-empty directory could cause issues
   - **Mitigation**: Require --here flag, skip existing files

## Recommendation

**Implement Option 1** with these changes:

1. Make `path` optional, default to current directory
2. Check if directory is empty before init
3. Add `--here` flag to force init in non-empty directory
4. Improve error messages with actionable suggestions
5. Update documentation and examples
6. Add comprehensive tests

**Priority**: High
**Effort**: Medium (4-6 hours)
**Impact**: High (major UX improvement)

## Implementation Order

1. ✅ Document the problem and solution (this file)
2. Add `_is_directory_empty()` helper function
3. Update `copy_template()` to support `allow_existing`
4. Update `init_project()` to pass `allow_existing`
5. Update `cli.py` init command with new logic
6. Update help text and docstrings
7. Add tests
8. Update user documentation
9. Update VS Code extension guide

## Related Issues

- Update VS Code extension documentation (completed in `docs/vscode_extension_user_guide.md`)
- Update main README.md with correct init usage
- Update quickstart guides
- Update tutorial examples

---

**Feedback Welcome**: Please review and provide feedback before implementation.
