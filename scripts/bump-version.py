#!/usr/bin/env python3
"""
Version bump script for Dazzle.

Usage:
    python scripts/bump-version.py patch   # 0.10.0 -> 0.10.1
    python scripts/bump-version.py minor   # 0.10.0 -> 0.11.0
    python scripts/bump-version.py major   # 0.10.0 -> 1.0.0
    python scripts/bump-version.py 0.12.0  # Set explicit version

Updates version in:
    - pyproject.toml (source of truth)
    - homebrew/dazzle.rb (Homebrew formula)
    - homebrew/dazzle-simple.rb (Simple Homebrew formula)
    - cli/package.json
    - package.json (root)
    - .claude/CLAUDE.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Files that contain version strings to update
VERSION_FILES = [
    ("pyproject.toml", r'^version\s*=\s*["\']([^"\']+)["\']', 'version = "{version}"'),
    ("homebrew/dazzle.rb", r'^\s*version\s+["\']([^"\']+)["\']', '  version "{version}"'),
    ("homebrew/dazzle-simple.rb", r'^\s*version\s+["\']([^"\']+)["\']', '  version "{version}"'),
    ("cli/package.json", r'"version":\s*"([^"]+)"', '"version": "{version}"'),
    ("package.json", r'"version":\s*"([^"]+)"', '"version": "{version}"'),
    (".claude/CLAUDE.md", r"\*\*Version\*\*:\s*[\d.]+", "**Version**: {version}"),
]

# Files where version appears in URLs/comments (update tag references)
TAG_FILES = [
    ("homebrew/dazzle.rb", r"v[\d]+\.[\d]+\.[\d]+"),
    ("homebrew/dazzle-simple.rb", r"v[\d]+\.[\d]+\.[\d]+"),
]


def get_current_version() -> str:
    """Read current version from pyproject.toml."""
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        raise FileNotFoundError("pyproject.toml not found. Run from project root.")

    content = pyproject.read_text()
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")

    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semver string to tuple."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid semver: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(current: str, bump_type: str) -> str:
    """Calculate new version based on bump type."""
    major, minor, patch = parse_version(current)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        # Assume it's an explicit version
        parse_version(bump_type)  # Validate format
        return bump_type


def update_file(filepath: str, pattern: str, replacement: str, new_version: str) -> bool:
    """Update version in a single file."""
    path = Path(filepath)
    if not path.exists():
        print(f"  ⚠ {filepath} not found, skipping")
        return False

    content = path.read_text()
    new_content = re.sub(
        pattern,
        replacement.format(version=new_version),
        content,
        count=1,
        flags=re.MULTILINE,
    )

    if content == new_content:
        print(f"  ⚠ {filepath} - no match found for pattern")
        return False

    path.write_text(new_content)
    print(f"  ✓ {filepath}")
    return True


def update_tag_references(filepath: str, pattern: str, new_version: str) -> bool:
    """Update version tag references (vX.Y.Z) in a file."""
    path = Path(filepath)
    if not path.exists():
        return False

    content = path.read_text()
    new_tag = f"v{new_version}"
    new_content = re.sub(pattern, new_tag, content)

    if content != new_content:
        path.write_text(new_content)
        print(f"  ✓ {filepath} (tag references)")
        return True

    return False


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    bump_type = sys.argv[1].lower()

    if bump_type in ("--help", "-h", "help"):
        print(__doc__)
        return 0

    try:
        current = get_current_version()
        new_version = bump_version(current, bump_type)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return 1

    print(f"\nBumping version: {current} → {new_version}\n")
    print("Updating files:")

    updated = 0
    for filepath, pattern, replacement in VERSION_FILES:
        if update_file(filepath, pattern, replacement, new_version):
            updated += 1

    # Update tag references in Homebrew formulas
    for filepath, pattern in TAG_FILES:
        update_tag_references(filepath, pattern, new_version)

    print(f"\n✓ Updated {updated} files to version {new_version}")

    # Reinstall editable package to update metadata
    print("\nReinstalling package...")
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  ✓ Package reinstalled")
    else:
        print(f"  ⚠ pip install failed: {result.stderr}")

    print("\nNext steps:")
    print("  1. Review changes: git diff")
    print(f"  2. Commit: git commit -am 'chore: bump version to {new_version}'")
    print(f"  3. Tag: git tag v{new_version}")
    print("  4. Push: git push && git push --tags")

    return 0


if __name__ == "__main__":
    sys.exit(main())
