"""Seed corpus loader for the DSL parser fuzzer."""

from pathlib import Path


def load_corpus(examples_dir: Path) -> list[str]:
    """Load all .dsl files from a directory tree as fuzzer seed corpus.

    Args:
        examples_dir: Root directory containing .dsl files.

    Returns:
        List of DSL source strings, one per file.
    """
    entries: list[str] = []
    for dsl_file in sorted(examples_dir.rglob("*.dsl")):
        text = dsl_file.read_text(encoding="utf-8").strip()
        if text:
            entries.append(text)
    return entries
