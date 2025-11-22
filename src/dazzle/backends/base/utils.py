"""
Common utilities for backends.

Provides helper functions that are useful across multiple backends:
- File system operations
- String formatting
- Code generation helpers
"""

import secrets
from pathlib import Path
from typing import List, Optional


def ensure_dir(path: Path) -> None:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists
    """
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str, create_dirs: bool = True) -> None:
    """
    Write content to a file.

    Args:
        path: File path to write to
        content: Content to write
        create_dirs: Whether to create parent directories if they don't exist
    """
    if create_dirs:
        ensure_dir(path.parent)
    path.write_text(content)


def generate_secret(length: int = 32) -> str:
    """
    Generate a secure random secret.

    Args:
        length: Number of bytes (will be hex-encoded to 2x length string)

    Returns:
        Hex-encoded random string
    """
    return secrets.token_hex(length)


def generate_password(length: int = 16) -> str:
    """
    Generate a URL-safe random password.

    Args:
        length: Number of bytes

    Returns:
        URL-safe random string
    """
    return secrets.token_urlsafe(length)


def indent(text: str, spaces: int = 4) -> str:
    """
    Indent all lines in text by specified number of spaces.

    Args:
        text: Text to indent
        spaces: Number of spaces to indent

    Returns:
        Indented text
    """
    indent_str = " " * spaces
    lines = text.split("\n")
    return "\n".join(indent_str + line if line.strip() else line for line in lines)


def join_lines(lines: List[str], separator: str = "\n") -> str:
    """
    Join lines, filtering out empty ones.

    Args:
        lines: List of lines to join
        separator: Separator between lines

    Returns:
        Joined string
    """
    return separator.join(line for line in lines if line)


def camel_to_snake(name: str) -> str:
    """
    Convert CamelCase to snake_case.

    Args:
        name: CamelCase string

    Returns:
        snake_case string
    """
    import re
    # Insert underscore before uppercase letters
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Insert underscore before uppercase letters followed by lowercase
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def snake_to_camel(name: str, capitalize_first: bool = True) -> str:
    """
    Convert snake_case to CamelCase.

    Args:
        name: snake_case string
        capitalize_first: Whether to capitalize first letter

    Returns:
        CamelCase string
    """
    components = name.split('_')
    if capitalize_first:
        return ''.join(x.title() for x in components)
    else:
        return components[0] + ''.join(x.title() for x in components[1:])


def pluralize(word: str) -> str:
    """
    Simple pluralization of English words.

    Args:
        word: Singular word

    Returns:
        Plural form (simple heuristic)
    """
    if word.endswith('s') or word.endswith('x') or word.endswith('z'):
        return word + 'es'
    elif word.endswith('y'):
        return word[:-1] + 'ies'
    else:
        return word + 's'


def create_init_file(directory: Path, content: str = "") -> None:
    """
    Create __init__.py file in a directory.

    Args:
        directory: Directory to create __init__.py in
        content: Content for __init__.py (default: empty)
    """
    ensure_dir(directory)
    (directory / "__init__.py").write_text(content)
