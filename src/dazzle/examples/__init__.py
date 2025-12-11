"""
Bundled example projects for DAZZLE.

These examples are used by `dazzle new` to create new projects.
"""

from pathlib import Path


def get_examples_dir() -> Path:
    """Get the path to the examples directory."""
    return Path(__file__).parent


def list_examples() -> list[str]:
    """List available example projects."""
    examples_dir = get_examples_dir()
    examples = []
    for item in examples_dir.iterdir():
        if item.is_dir() and (item / "dazzle.toml").exists():
            examples.append(item.name)
    return sorted(examples)
