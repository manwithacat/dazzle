"""
Main project initialization logic.

Handles creating new DAZZLE projects from templates or examples.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ..llm_context import create_llm_instrumentation
from .dnr_ui import generate_dnr_ui
from .spec import create_spec_template
from .templates import copy_template
from .validation import InitError, sanitize_name

if TYPE_CHECKING:
    from collections.abc import Callable


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
        examples_dir = Path(__file__).parent.parent.parent.parent.parent / "examples"

    if not examples_dir.exists():
        return []

    examples = []
    for item in examples_dir.iterdir():
        if item.is_dir() and (item / "dazzle.toml").exists():
            examples.append(item.name)

    return sorted(examples)


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
    with open(mcp_path, "w") as f:
        json.dump(mcp_config, f, indent=2)
        f.write("\n")


def init_project(
    target_dir: Path,
    project_name: str | None = None,
    from_example: str | None = None,
    title: str | None = None,
    no_llm: bool = False,
    no_git: bool = False,
    stack_name: str | None = None,
    allow_existing: bool = False,
    progress_callback: Callable[[str], None] | None = None,
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
        examples_dir = Path(__file__).parent.parent.parent.parent.parent / "examples"
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
        template_dir = Path(__file__).parent.parent.parent / "templates" / "blank"

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
        _init_git_repository(target_dir, log)
    else:
        log("Skipping git initialization (--no-git)")


def _init_git_repository(target_dir: Path, log: Callable[[str], None]) -> None:
    """
    Initialize git repository in project directory.

    Args:
        target_dir: Project directory
        log: Logging callback
    """
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
