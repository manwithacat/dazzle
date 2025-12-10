"""
Project reset and verification.

Handles resetting projects to example state and verifying project structure.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .project import list_examples
from .validation import InitError


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
    examples_dir = Path(__file__).parent.parent.parent.parent.parent / "examples"
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
