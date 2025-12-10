"""
Template copying and variable substitution.

Handles copying template directories and substituting {{variable}} patterns.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .validation import InitError

# Directories that should be generated, not copied from templates
# These are auto-generated from DSL and should use canonical templates
GENERATED_DIRECTORIES = {"dnr-ui", "build"}


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
