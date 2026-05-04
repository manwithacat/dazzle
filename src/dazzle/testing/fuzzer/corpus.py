"""Seed corpus loader for the DSL parser fuzzer."""

from pathlib import Path


def load_corpus(examples_dir: Path) -> list[str]:
    """Load all hand-written .dsl files from a directory tree as fuzzer
    seed corpus. Auto-generated mirrors (`.dazzle/spec_snapshots/`,
    `.improve-snapshots/`) are excluded — they are framework-cached
    copies that lag the canonical sources and would otherwise contain
    stale syntax after a grammar rename.

    Args:
        examples_dir: Root directory containing .dsl files.

    Returns:
        List of DSL source strings, one per file.
    """
    skip_segments = {".dazzle", ".improve-snapshots"}
    entries: list[str] = []
    for dsl_file in sorted(examples_dir.rglob("*.dsl")):
        if any(part in skip_segments for part in dsl_file.parts):
            continue
        text = dsl_file.read_text(encoding="utf-8").strip()
        if text:
            entries.append(text)
    return entries
