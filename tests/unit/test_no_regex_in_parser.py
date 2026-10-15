"""ADR-0024 enforcement: no regex parsing in the DSL parser.

A regex matching a DSL grammar shape (call form, keyword, sub-expression)
is a smell — the right next step is to add an IR type and a dispatcher
method, not a ``re.compile``.

This test scans the DSL parser surface for ``re.*`` calls and fails on
any hit. The old allowlist of lexical-shape regex was drained to zero in
#1155.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

# The parser surface scanned. The allowlist of pre-existing lexical regex was
# drained to zero in #1155 (the duration-literal and Entity.field probes now
# route through char-walk helpers in ``dsl_parser_impl/_lexical.py``); there is
# no allowlist any more, so a new regex is a failure, not an entry.
_SCAN_DIRS: tuple[str, ...] = ("src/dazzle/core/dsl_parser_impl",)
_SCAN_FILES: tuple[str, ...] = ("src/dazzle/core/parser.py",)

# Detects calls of the form `re.<method>(` — captures the most common
# misuse patterns without false-positives on `# re.compile is fine here`
# style comments (those don't match the open-paren).
_RE_CALL_PATTERN = re.compile(r"\bre\.(compile|match|search|findall|sub|fullmatch)\s*\(")


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _iter_python_files() -> list[Path]:
    root = _project_root()
    files: list[Path] = []
    for d in _SCAN_DIRS:
        files.extend((root / d).rglob("*.py"))
    for f in _SCAN_FILES:
        p = root / f
        assert p.is_file(), f"scanned parser file moved or was removed: {f}"
        files.append(p)
    return files


def test_no_unallowed_regex_in_dsl_parser() -> None:
    """No new ``re.*`` calls may appear in the DSL parser surface.

    Any hit fails with an instruction to migrate the call site to typed
    IR per ADR-0024.
    """
    root = _project_root()
    violations: list[tuple[str, int, str]] = []
    for path in _iter_python_files():
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Skip comment-only lines so explanatory prose doesn't trip
            # the scan. A trailing comment on a code line still triggers
            # if it references re.compile().
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _RE_CALL_PATTERN.search(line):
                violations.append((rel, lineno, line.strip()))

    if violations:
        msg_lines = [
            "Found regex parsing in the DSL parser surface (ADR-0024):",
            "",
        ]
        for rel, lineno, src in violations:
            msg_lines.append(f"  {rel}:{lineno}  {src}")
        msg_lines.extend(
            [
                "",
                "Regex matching a DSL shape (call form, keyword, sub-expression) ",
                "is a grammar smell. The right next step is to add an IR type ",
                "and a parser method, not a re.compile.",
                "",
                "If this is genuinely lexical-shape recognition (a token's ",
                "internal character class), add a char-walk helper to ",
                "dsl_parser_impl/_lexical.py instead.",
            ]
        )
        raise AssertionError("\n".join(msg_lines))
