"""
Project initialization utilities for DAZZLE.

Handles:
- Creating new projects from templates
- Copying example projects
- Substituting template variables
- LLM instrumentation setup
- Git repository initialization
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from .errors import DazzleError
from .llm_context import create_llm_instrumentation


class InitError(DazzleError):
    """Raised when project initialization fails."""

    pass


# Reserved keywords that can't be used as project/module names
RESERVED_KEYWORDS = {
    # DSL keywords
    "app",
    "module",
    "entity",
    "surface",
    "experience",
    "service",
    "foreign_model",
    "integration",
    "test",
    "use",
    "section",
    "field",
    "action",
    "step",
    "transition",
    # Python keywords
    "import",
    "from",
    "def",
    "class",
    "if",
    "else",
    "elif",
    "for",
    "while",
    "break",
    "continue",
    "return",
    "yield",
    "try",
    "except",
    "finally",
    "with",
    "as",
    "raise",
    "assert",
    "del",
    "pass",
    "lambda",
    "global",
    "nonlocal",
    "and",
    "or",
    "not",
    "in",
    "is",
    # Common problematic names
    "true",
    "false",
    "null",
    "none",
    "type",
    "list",
    "dict",
    "set",
    "str",
    "int",
    "float",
    "bool",
    "tuple",
    "range",
    "object",
    # Django/Python stdlib conflicts
    "admin",
    "auth",
    "models",
    "views",
    "urls",
    "settings",
    "forms",
    "serializers",
    "tests",
    "migrations",
    "static",
    "templates",
}


def list_examples(examples_dir: Path | None = None) -> list[str]:
    """
    List available example projects.

    Args:
        examples_dir: Path to examples directory (defaults to package examples/)

    Returns:
        List of example names
    """
    if examples_dir is None:
        # Use installed examples directory
        examples_dir = Path(__file__).parent.parent.parent.parent / "examples"

    if not examples_dir.exists():
        return []

    examples = []
    for item in examples_dir.iterdir():
        if item.is_dir() and (item / "dazzle.toml").exists():
            examples.append(item.name)

    return sorted(examples)


def validate_project_name(name: str) -> tuple[bool, str | None]:
    """
    Validate a project name.

    Args:
        name: Project name to validate

    Returns:
        (is_valid, error_message)

    Examples:
        validate_project_name("test")  # -> (False, "...")
        validate_project_name("my_app")  # -> (True, None)
    """
    if not name:
        return (False, "Project name cannot be empty")

    # Check if it starts with a digit
    if name[0].isdigit():
        return (
            False,
            f"Project name '{name}' cannot start with a digit. Try 'project_{name}' or '{name}_app'",
        )

    # Check reserved keywords
    if name.lower() in RESERVED_KEYWORDS:
        return (
            False,
            f"Project name '{name}' is a reserved keyword. Try '{name}_app', 'my_{name}', or '{name}_project' instead",
        )

    # Check if it's a valid Python identifier pattern
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        return (
            False,
            f"Project name '{name}' must contain only letters, numbers, and underscores, and cannot start with a number",
        )

    return (True, None)


def sanitize_name(name: str, validate: bool = True) -> str:
    """
    Convert a project name to a valid Python module name.

    Args:
        name: Project name (can include spaces, hyphens)
        validate: If True, raises InitError for reserved keywords

    Returns:
        Valid Python identifier (lowercase, underscores)

    Raises:
        InitError: If validate=True and name is reserved keyword

    Examples:
        "My Project" -> "my_project"
        "my-app" -> "my_app"
        "MyApp" -> "myapp"
    """
    # Convert to lowercase
    name = name.lower()
    # Replace non-alphanumeric with underscores
    name = re.sub(r"[^a-z0-9_]", "_", name)
    # Remove leading/trailing underscores
    name = name.strip("_")
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)

    # Ensure doesn't start with digit
    if name and name[0].isdigit():
        name = f"project_{name}"

    final_name = name or "my_project"

    # Validate if requested
    if validate:
        is_valid, error_msg = validate_project_name(final_name)
        if not is_valid:
            raise InitError(error_msg or "Invalid project name")

    return final_name


def substitute_template_vars(content: str, variables: dict[str, str]) -> str:
    """
    Substitute {{variable}} patterns in template content.

    Args:
        content: Template content with {{var}} placeholders
        variables: Dict mapping variable names to values

    Returns:
        Content with variables substituted

    Examples:
        substitute_template_vars("Hello {{name}}", {"name": "World"})
        # -> "Hello World"
    """
    for key, value in variables.items():
        pattern = f"{{{{{key}}}}}"
        content = content.replace(pattern, value)

    return content


def generate_dnr_ui(
    project_dir: Path,
    log: "Callable[[str], None] | None" = None,
) -> bool:
    """
    Generate DNR UI artifacts from the project's DSL.

    This ensures that dnr-ui/ is always generated from the canonical
    vite_generator templates, not copied from stale example files.

    Args:
        project_dir: Project directory containing dazzle.toml and dsl/
        log: Optional logging callback

    Returns:
        True if generation succeeded, False otherwise
    """
    if log is None:
        log = lambda msg: None  # noqa: E731

    # Check if dazzle.toml exists
    manifest_path = project_dir / "dazzle.toml"
    if not manifest_path.exists():
        log("  Skipping dnr-ui generation (no dazzle.toml)")
        return False

    try:
        # Import required modules
        from dazzle.core.dsl_parser import parse_dsl
        from dazzle.core.ir import ModuleIR
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest

        # Try to import DNR UI - it's optional
        try:
            from dazzle_dnr_ui.converters import convert_appspec_to_ui
            from dazzle_dnr_ui.runtime import generate_vite_app
        except ImportError:
            log("  Skipping dnr-ui generation (dazzle-dnr-ui not installed)")
            return False

        # Load manifest (validates it exists and is well-formed)
        _manifest = load_manifest(manifest_path)

        # Discover and parse DSL files
        dsl_dir = project_dir / "dsl"
        if not dsl_dir.exists():
            log("  Skipping dnr-ui generation (no dsl/ directory)")
            return False

        dsl_files = list(dsl_dir.glob("**/*.dsl"))
        if not dsl_files:
            log("  Skipping dnr-ui generation (no .dsl files found)")
            return False

        # Parse all DSL files
        modules: list[ModuleIR] = []
        for dsl_file in dsl_files:
            content = dsl_file.read_text()
            module_name, app_name, app_title, uses, fragment = parse_dsl(content, dsl_file)

            if module_name is None:
                log(f"  Skipping {dsl_file} (no module name found)")
                continue

            module_ir = ModuleIR(
                name=module_name,
                file=dsl_file,
                app_name=app_name,
                app_title=app_title,
                uses=uses,
                fragment=fragment,
            )
            modules.append(module_ir)

        if not modules:
            log("  Skipping dnr-ui generation (no modules parsed)")
            return False

        # Build AppSpec
        root_module = modules[0].name
        appspec = build_appspec(modules, root_module)

        # Convert to UISpec
        ui_spec = convert_appspec_to_ui(appspec)

        # Generate Vite project
        output_dir = project_dir / "dnr-ui"
        output_dir.mkdir(parents=True, exist_ok=True)

        files = generate_vite_app(ui_spec, str(output_dir))
        log(f"  Generated dnr-ui/ ({len(files)} files)")

        return True

    except Exception as e:
        # Don't fail init if dnr-ui generation fails
        log(f"  Warning: dnr-ui generation failed ({e})")
        return False


# Directories that should be generated, not copied from templates
# These are auto-generated from DSL and should use canonical templates
GENERATED_DIRECTORIES = {"dnr-ui", "build"}


def copy_template(
    template_dir: Path,
    target_dir: Path,
    variables: dict[str, str] | None = None,
    allow_existing: bool = False,
) -> None:
    """
    Copy a template directory to target, substituting variables.

    Skips directories in GENERATED_DIRECTORIES (e.g., dnr-ui/, build/)
    since these are auto-generated from DSL and should use canonical templates.

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

                # Skip files in generated directories (dnr-ui/, build/, etc.)
                # These will be regenerated from DSL using canonical templates
                if any(part in GENERATED_DIRECTORIES for part in rel_path.parts):
                    continue

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


def verify_project(project_dir: Path, show_diff: bool = False) -> bool:
    """
    Verify a DAZZLE project after creation.

    Runs validation and optionally shows what would be generated.

    Args:
        project_dir: Path to project directory
        show_diff: If True, show what would be generated (default: False)

    Returns:
        True if validation passes, False otherwise
    """
    try:
        # Run validation
        result = subprocess.run(
            ["python3", "-m", "dazzle.cli", "validate"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Validation failed
            return False

        # Optionally show diff
        if show_diff:
            result = subprocess.run(
                ["python3", "-m", "dazzle.cli", "build", "--diff"],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )
            # Note: we don't fail on diff errors, just on validation errors

        return True

    except (subprocess.CalledProcessError, FileNotFoundError):
        # If we can't run validation, consider it a failure
        return False


def create_mcp_config(project_dir: Path) -> None:
    """
    Create .mcp.json configuration file for Claude Code integration.

    Args:
        project_dir: Directory to create the file in
    """
    mcp_config = {
        "mcpServers": {
            "dazzle": {
                "command": "python",
                "args": ["-m", "dazzle.mcp.server"],
                "cwd": "${workspaceFolder}",
            }
        }
    }

    mcp_path = project_dir / ".mcp.json"
    import json

    with open(mcp_path, "w") as f:
        json.dump(mcp_config, f, indent=2)
        f.write("\n")


def create_spec_template(target_dir: Path, project_name: str, title: str) -> None:
    """
    Create a SPEC.md template file to guide founders in defining their project.

    Args:
        target_dir: Project directory
        project_name: Project name
        title: Human-readable project title
    """
    spec_path = target_dir / "SPEC.md"

    spec_content = f"""# {title} - Product Specification

**Project Type**: _[e.g., Personal Tool, Team App, Customer Portal]_
**Target Users**: _[Who will use this? Be specific!]_
**Deployment**: _[Single-user, Multi-user, Public-facing]_

---

## Project Overview

_Describe your project in 2-3 sentences from a founder's perspective._

I need a [type of application] that helps [target users] to [main goal]. The key problem I'm solving is [problem statement]. Users should be able to [primary actions] with minimal friction.

**Example**:
> I need a simple task management application where I can keep track of my to-do items. Nothing fancy - just a straightforward way to create tasks, mark their status, and set priorities. I want to be able to see all my tasks at a glance, view details when needed, and mark tasks as complete when I finish them.

---

## Core Features

### What I Need to Track

_List the main "things" (entities/objects) in your system._

**[Entity Name]** (e.g., Task, User, Order, Ticket):
- **[Field Name]** (required/optional) - Brief description
- **[Field Name]** (required/optional) - Brief description
- **Status/State** - List possible values (e.g., "Draft, Active, Complete")
- **Timestamps** - Created, Updated, etc.

**Example**:
> **Task**:
> - **Title** (required) - Short name for the task
> - **Description** (optional) - Detailed information
> - **Status** - To Do, In Progress, Done
> - **Priority** - Low, Medium, High
> - **Created At** - Auto-timestamp

### User Stories

**As a [user type], I want to:**

1. **[Action/Goal]**
   - [Specific detail about what this enables]
   - [Why this is important]
   - [Expected result]

2. **[Action/Goal]**
   - [Details...]

**Example**:
> **As a user, I want to:**
>
> 1. **View all my tasks**
>    - See a list of all tasks with their title, status, and priority
>    - Quickly scan what needs to be done
>    - Have the most recent tasks appear first
>
> 2. **Create new tasks**
>    - Enter a title (required)
>    - Optionally add a description
>    - Set an initial priority (defaults to Medium)

---

## User Interface

### Pages I Need

1. **[Page Name]** (e.g., Task List, Home Dashboard)
   - Shows: [What data/information]
   - Actions: [What users can do]
   - Features: [Filters, sorting, etc.]

2. **[Page Name]** (e.g., Create Form, Detail View)
   - Purpose: [Why users come here]
   - Fields: [What they fill out or see]
   - Next step: [Where they go after]

**Example**:
> 1. **Task List Page**
>    - Shows: All tasks in a table (Title, Status, Priority)
>    - Actions: Create new task, Edit, Delete, View details
>    - Features: Sort by date, Filter by status

---

## What the System Provides Automatically

_These features are built into DAZZLE-generated applications - you don't need to ask for them!_

### Admin Dashboard
A powerful admin interface is automatically generated with:
- Browse all your data in tables
- Search and filter capabilities
- Bulk actions (delete multiple items)
- Direct database editing
- Data export
- **Access**: Available in navigation and home page

### Home Page
A central hub that shows:
- Quick access to all your resources
- Links to create new items
- Admin dashboard access
- System status

### Navigation
Automatic navigation menu with:
- Links to all main pages
- Admin interface link
- Mobile-responsive design (hamburger menu on phones)

### Data Persistence
- Database with automatic migrations
- Data persists when you close the browser
- Timestamps auto-update when editing
- Relationships between entities maintained

### Deployment Support
- One-click deployment configs for Heroku, Railway, Vercel
- Environment variable management
- Production-ready settings
- SQLite for development, easy migration to PostgreSQL

---

## Example Scenarios

_Write 2-3 concrete examples of how someone would use your application._

### Scenario 1: [Common Use Case]

1. User does [action]
2. System shows [result]
3. User then [next action]
4. Final outcome: [what's achieved]

**Example**:
> ### Scenario 1: Creating My First Task
>
> 1. Open the app - see empty task list
> 2. Click "Create New Task"
> 3. Enter: "Buy groceries" (title)
> 4. Select priority: High
> 5. Click Save
> 6. Return to list - see my new task with status "To Do"

---

## Success Criteria

_How will you know this project is successful?_

This app is successful if:
- [Measurable outcome 1]
- [User experience goal 2]
- [Technical goal 3]
- [Adoption/usage goal 4]

**Example**:
> This app is successful if:
> - I can create a task in under 10 seconds
> - I can see my entire task list at a glance
> - I never lose my task data
> - The app "just works" without configuration
> - I can deploy it for free on a cloud platform

---

## Technical Requirements

### Must Have
- Works on desktop and mobile browsers
- Fast page loads
- Data persists across sessions
- Easy deployment

### Nice to Have
- [Feature that would be great but not essential]
- [Enhancement for later]

### Out of Scope (For Version 1)
_Important: List what you explicitly DON'T need for the first version._

- User authentication (if single-user)
- Advanced search
- File attachments
- Email notifications
- Mobile apps
- API access

---

## Notes for Development

### Keep It Simple
- I'd rather have it working quickly than have lots of features
- Use sensible defaults wherever possible
- Automatic timestamps - I don't want to enter dates manually
- Standard web technologies that are easy to maintain

### Data Relationships
_If your entities relate to each other, describe how:_

- [Entity A] can have many [Entity B] (one-to-many)
- [Entity X] must have a [Entity Y] (required relationship)
- [Entity M] can optionally link to [Entity N]

**Example**:
> - A User can create many Tasks (one-to-many)
> - Every Task must have a creator (required)
> - Tasks can be assigned to a User (optional)

### Priority Guidance
_If using priority/status fields, explain what they mean:_

**Status Options**:
- [Option 1] - When to use this
- [Option 2] - When to use this

**Priority Levels**:
- [Level 1] - Example situations
- [Level 2] - Example situations

---

## Working with AI Assistants to Build This

_Tips for collaborating with LLM agents to turn this spec into DAZZLE DSL:_

### Getting Started

1. **Share this SPEC.md** with your AI assistant (Claude, ChatGPT, etc.)

2. **Ask the AI to help translate** your requirements into DAZZLE DSL:
   - "Based on my SPEC.md, help me create the entity definitions in DAZZLE DSL"
   - "What fields should I define for the [Entity] entity?"
   - "How do I express the relationship between [Entity A] and [Entity B]?"

3. **Iterate on the DSL**:
   - Start with one entity to get the pattern right
   - Add fields incrementally
   - Test with `dazzle validate` frequently
   - The AI can help debug validation errors

4. **Build and refine**:
   - Run `dazzle build` to see your application
   - Show the AI what was generated
   - Discuss what needs adjustment
   - Update the DSL based on feedback

### Helpful Prompts for AI

- "Review my entity definitions - are there any missing required fields?"
- "I want users to be able to [action] - what surfaces do I need to define?"
- "The validation is failing - can you help me understand this error?"
- "How do I make [field] optional instead of required?"
- "I need a dropdown field with options [A, B, C] - how do I define that in DSL?"

### What to Show the AI

✅ **DO share**:
- This SPEC.md file
- Your DSL files (dsl/*.dsl)
- Validation errors from `dazzle validate`
- Generated code if you have questions about behavior

❌ **DON'T stress about**:
- Perfect DSL syntax on first try - iterate!
- Getting every field right immediately
- Knowing all DAZZLE features upfront

### Example Conversation Flow

> **You**: "I've created a SPEC.md for a task management app. Can you help me create the DAZZLE DSL?"
>
> **AI**: "I'll help! Based on your spec, let's start with the Task entity. Here's a first draft..."
>
> **You**: "Great! How do I make the description optional?"
>
> **AI**: "Remove the 'required' keyword from that field..."
>
> **You**: [runs `dazzle validate`] "I'm getting an error about the status field"
>
> **AI**: "That error means... try changing it to..."

---

## Next Steps

1. **Fill out this template** with your project requirements
2. **Share with your AI assistant** to create DAZZLE DSL together
3. **Run `dazzle validate`** to check your DSL
4. **Run `dazzle build`** to generate your application
5. **Test and iterate** - update DSL based on what you see

**Remember**: Start simple! You can always add more features later. Better to have a working v1 than a perfect plan that never ships. 🚀
"""

    spec_path.write_text(spec_content)


def init_project(
    target_dir: Path,
    project_name: str | None = None,
    from_example: str | None = None,
    title: str | None = None,
    no_llm: bool = False,
    no_git: bool = False,
    stack_name: str | None = None,
    allow_existing: bool = False,
    progress_callback: "Callable[[str], None] | None" = None,
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
        progress_callback: Optional callback for progress messages

    Raises:
        InitError: If initialization fails
    """

    def log(msg: str) -> None:
        """Log progress message if callback provided."""
        if progress_callback:
            progress_callback(msg)

    # Determine project name
    if project_name is None:
        project_name = target_dir.name

    log(f"Initializing project '{project_name}'...")

    # Sanitize for use as module name
    module_name = sanitize_name(project_name)
    log(f"  Module name: {module_name}")

    # Determine title
    if title is None:
        # Convert project_name to title case
        title = project_name.replace("_", " ").replace("-", " ").title()
    log(f"  Project title: {title}")

    # Prepare template variables
    variables = {
        "project_name": project_name,
        "module_name": module_name,
        "project_title": title,
    }

    # Determine source directory
    if from_example:
        log(f"Copying from example '{from_example}'...")
        # Copy from example
        examples_dir = Path(__file__).parent.parent.parent.parent / "examples"
        template_dir = examples_dir / from_example

        if not template_dir.exists():
            available = list_examples(examples_dir)
            raise InitError(
                f"Example '{from_example}' not found. "
                f"Available examples: {', '.join(available) if available else 'none'}"
            )
    else:
        log("Creating blank project from template...")
        # Use blank template
        template_dir = Path(__file__).parent.parent / "templates" / "blank"

        if not template_dir.exists():
            raise InitError(f"Blank template not found at {template_dir}")

    # Copy template
    log(f"  Copying project files to {target_dir}...")
    copy_template(template_dir, target_dir, variables, allow_existing=allow_existing)
    log("  Project files copied")

    # Create SPEC.md template (only for blank projects, not examples)
    if not from_example:
        log("  Creating SPEC.md template...")
        create_spec_template(target_dir, project_name, title)

    # Create .mcp.json if it doesn't exist
    mcp_path = target_dir / ".mcp.json"
    if not mcp_path.exists():
        log("  Creating MCP configuration (.mcp.json)...")
        create_mcp_config(target_dir)

    # Create LLM instrumentation (unless disabled)
    if not no_llm:
        log("Creating LLM instrumentation files...")
        try:
            create_llm_instrumentation(
                project_dir=target_dir,
                project_name=project_name,
                stack_name=stack_name,
            )
            log("  Created LLM_CONTEXT.md, .llm/, .claude/, .copilot/")
        except Exception as e:
            # Don't fail the entire init if LLM instrumentation fails
            # Just warn the user
            import warnings

            warnings.warn(f"Failed to create LLM instrumentation: {e}", stacklevel=2)
            log(f"  Warning: LLM instrumentation failed ({e})")
    else:
        log("Skipping LLM instrumentation (--no-llm)")

    # Generate DNR UI from DSL (ensures we use canonical templates, not stale copies)
    log("Generating DNR UI from DSL...")
    generate_dnr_ui(target_dir, log)

    # Initialize git repository (unless disabled)
    if not no_git:
        log("Initializing git repository...")
        try:
            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=target_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            log("  Git repository initialized")

            # Create .gitignore if it doesn't exist
            gitignore_path = target_dir / ".gitignore"
            if not gitignore_path.exists():
                log("  Creating .gitignore...")
                gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# DAZZLE
.dazzle/
dev_docs/

# Database
*.sqlite3
*.db
"""
                gitignore_path.write_text(gitignore_content)

            # Make initial commit (optional - only if we have content)
            # Check if we have files to commit
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )
            if status_result.stdout.strip():
                log("  Staging files for initial commit...")
                # Add all files
                subprocess.run(
                    ["git", "add", "."],
                    cwd=target_dir,
                    check=True,
                    capture_output=True,
                )
                log("  Creating initial commit...")
                # Make initial commit
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit: DAZZLE project setup"],
                    cwd=target_dir,
                    check=True,
                    capture_output=True,
                )
                log("  Initial commit created")

        except subprocess.CalledProcessError as e:
            # Don't fail the entire init if git initialization fails
            # Just warn the user
            import warnings

            warnings.warn(f"Failed to initialize git repository: {e}", stacklevel=2)
            log(f"  Warning: git initialization failed ({e})")
        except FileNotFoundError:
            # git not installed
            import warnings

            warnings.warn("git command not found - skipping git initialization", stacklevel=2)
            log("  Warning: git not found, skipping")
    else:
        log("Skipping git initialization (--no-git)")


def reset_project(
    target_dir: Path,
    from_example: str,
    preserve_patterns: list[str] | None = None,
) -> dict[str, list[str]]:
    """
    Reset a DAZZLE project to match the example, preserving user-created files.

    This performs a "smart reset" that:
    1. Overwrites DSL source files with the example versions
    2. Deletes generated artifacts (build/ directory)
    3. Preserves user-created files not in the example
    4. Preserves files matching preserve_patterns

    Args:
        target_dir: Existing project directory to reset
        from_example: Example to reset to (e.g., "simple_task")
        preserve_patterns: Optional glob patterns for files to always preserve

    Returns:
        Dict with keys: 'overwritten', 'deleted', 'preserved', 'added'

    Raises:
        InitError: If reset fails
    """
    if not target_dir.exists():
        raise InitError(f"Directory does not exist: {target_dir}")

    # Find example directory
    examples_dir = Path(__file__).parent.parent.parent.parent / "examples"
    example_dir = examples_dir / from_example

    if not example_dir.exists():
        available = list_examples(examples_dir)
        raise InitError(
            f"Example '{from_example}' not found. "
            f"Available examples: {', '.join(available) if available else 'none'}"
        )

    # Default preserve patterns (user config, IDE settings, etc.)
    default_preserve = [
        ".git/**",
        ".vscode/**",
        ".idea/**",
        "*.local",
        "*.local.*",
        ".env",
        ".env.local",
        ".env.*.local",
    ]

    all_preserve = default_preserve + (preserve_patterns or [])

    # Track what we do
    result: dict[str, list[str]] = {
        "overwritten": [],
        "deleted": [],
        "preserved": [],
        "added": [],
    }

    # Get all files in example (these are source files)
    example_files: set[str] = set()
    for src_path in example_dir.rglob("*"):
        if src_path.is_file():
            rel_path = str(src_path.relative_to(example_dir))
            # Skip build directory in example
            if not rel_path.startswith("build/") and not rel_path.startswith(".dazzle/"):
                example_files.add(rel_path)

    # Get all files in target directory
    target_files: set[str] = set()
    for dst_path in target_dir.rglob("*"):
        if dst_path.is_file():
            rel_path = str(dst_path.relative_to(target_dir))
            target_files.add(rel_path)

    # Check if a path matches preserve patterns
    def should_preserve(rel_path: str) -> bool:
        from fnmatch import fnmatch

        for pattern in all_preserve:
            if fnmatch(rel_path, pattern):
                return True
            # Also check if it's under a preserved directory
            parts = rel_path.split("/")
            for i in range(len(parts)):
                partial = "/".join(parts[: i + 1])
                if fnmatch(partial, pattern.removesuffix("/**")):
                    return True
        return False

    # Step 1: Delete build/ directory (generated artifacts)
    build_dir = target_dir / "build"
    if build_dir.exists():
        for f in build_dir.rglob("*"):
            if f.is_file():
                result["deleted"].append(str(f.relative_to(target_dir)))
        shutil.rmtree(build_dir)

    # Step 2: Delete .dazzle/ directory (build state)
    dazzle_state_dir = target_dir / ".dazzle"
    if dazzle_state_dir.exists():
        for f in dazzle_state_dir.rglob("*"):
            if f.is_file():
                result["deleted"].append(str(f.relative_to(target_dir)))
        shutil.rmtree(dazzle_state_dir)

    # Step 3: Overwrite/add files from example
    for rel_path in example_files:
        src_path = example_dir / rel_path
        dst_path = target_dir / rel_path

        if should_preserve(rel_path):
            if dst_path.exists():
                result["preserved"].append(rel_path)
            continue

        # Create parent directories
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy the file
        try:
            content = src_path.read_text(encoding="utf-8")
            if dst_path.exists():
                result["overwritten"].append(rel_path)
            else:
                result["added"].append(rel_path)
            dst_path.write_text(content, encoding="utf-8")
        except UnicodeDecodeError:
            # Binary file
            if dst_path.exists():
                result["overwritten"].append(rel_path)
            else:
                result["added"].append(rel_path)
            shutil.copy2(src_path, dst_path)

    # Step 4: Identify preserved user files (files not in example)
    for rel_path in target_files:
        if rel_path not in example_files:
            # Skip already deleted files (build/, .dazzle/)
            if rel_path.startswith("build/") or rel_path.startswith(".dazzle/"):
                continue
            # This is a user-created file, preserve it
            if rel_path not in result["preserved"]:
                result["preserved"].append(rel_path)

    return result


__all__ = [
    "InitError",
    "list_examples",
    "sanitize_name",
    "substitute_template_vars",
    "copy_template",
    "init_project",
    "reset_project",
    "verify_project",
]
