"""
Dazzle Standard Library

Provides standard vocabulary entries, patterns, and utilities that can be
used across all Dazzle projects. The stdlib is automatically available
without explicit imports.

Standard Library Contents:
- auth_vocab.yml: Authentication patterns (simple_auth, jwt_auth, etc.)
- (future) data_vocab.yml: Common data patterns
- (future) ui_vocab.yml: Standard UI patterns

Usage in DSL:
    @use simple_auth()              # From auth_vocab.yml
    @use jwt_auth(access_token_minutes=30)

The stdlib entries are merged with app-local vocabulary, with local
entries taking precedence in case of name conflicts.
"""

from pathlib import Path

STDLIB_DIR = Path(__file__).parent


def get_stdlib_vocab_path(name: str) -> Path | None:
    """
    Get path to a stdlib vocabulary file.

    Args:
        name: Vocabulary name (e.g., 'auth' for auth_vocab.yml)

    Returns:
        Path to the vocabulary file, or None if not found
    """
    vocab_file = STDLIB_DIR / f"{name}_vocab.yml"
    if vocab_file.exists():
        return vocab_file
    return None


def list_stdlib_vocabs() -> list[str]:
    """
    List all available stdlib vocabulary files.

    Returns:
        List of vocabulary names (without _vocab.yml suffix)
    """
    return [
        f.stem.replace("_vocab", "")
        for f in STDLIB_DIR.glob("*_vocab.yml")
    ]


__all__ = [
    "STDLIB_DIR",
    "get_stdlib_vocab_path",
    "list_stdlib_vocabs",
]
