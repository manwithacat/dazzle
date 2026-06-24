"""ADR-0024 enforcement: no regex parsing in the DSL parser.

A regex matching a DSL grammar shape (call form, keyword, sub-expression)
is a smell — the right next step is to add an IR type and a dispatcher
method, not a ``re.compile``.

This test scans the DSL parser surface for ``re.*`` calls and fails on
hits outside an explicit allowlist. The allowlist captures pre-existing
lexical-shape regex (duration literals, Entity.field identifier pattern)
that has not yet been migrated to a tokeniser. **The allowlist should
shrink over time, never grow.** New additions to it must come with a
follow-up issue to migrate the call site.

When this test fails, the right response is almost always to add an IR
type + parser method, not to extend the allowlist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

# Files + line numbers of pre-existing regex calls in the parser surface.
# Each entry is (relative_path, line_number, rationale). A regex call on
# a line listed here is allowed; any other regex call fails the test.
#
# Drained to zero in #1155 — the previous four entries (Entity.field
# probe + three duration-literal splits) now route through char-walk
# helpers in ``dsl_parser_impl/_lexical.py``. Adding an entry requires
# a paired migration plan (see the issue tracker, label `adr-0024`).
_ALLOWLIST: frozenset[tuple[str, int]] = frozenset()

# The directories scanned. Add new parser surfaces here, not new
# allowlist entries.
_SCAN_DIRS: tuple[str, ...] = ("src/dazzle/core/dsl_parser_impl",)
_SCAN_FILES: tuple[str, ...] = ("src/dazzle/core/dsl_parser.py",)

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
        if p.is_file():
            files.append(p)
    return files


def test_no_unallowed_regex_in_dsl_parser() -> None:
    """No new ``re.*`` calls may appear in the DSL parser surface.

    Pre-existing calls are listed in ``_ALLOWLIST`` with (path, line).
    Any non-allowlisted hit fails this test with an instruction to
    migrate the call site to typed IR per ADR-0024, OR — with strong
    justification — extend the allowlist alongside a tracked migration
    issue.
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
                if (rel, lineno) in _ALLOWLIST:
                    continue
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
                "internal character class), add the (path, line) tuple to ",
                "_ALLOWLIST in this test alongside a migration issue.",
            ]
        )
        raise AssertionError("\n".join(msg_lines))


def test_allowlist_entries_still_valid() -> None:
    """Every allowlist entry must still point at a line that contains
    a regex call. Drift in line numbers (after a refactor that moved the
    code) means the allowlist is masking new violations elsewhere.
    """
    root = _project_root()
    stale: list[tuple[str, int]] = []
    for rel, lineno in _ALLOWLIST:
        path = root / rel
        if not path.is_file():
            stale.append((rel, lineno))
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if lineno < 1 or lineno > len(lines):
            stale.append((rel, lineno))
            continue
        if not _RE_CALL_PATTERN.search(lines[lineno - 1]):
            stale.append((rel, lineno))

    if stale:
        msg_lines = [
            "ADR-0024 allowlist contains stale entries — the line no ",
            "longer contains a regex call:",
            "",
        ]
        for rel, lineno in stale:
            msg_lines.append(f"  {rel}:{lineno}")
        msg_lines.extend(
            [
                "",
                "Either remove the entry (the migration happened — celebrate!) ",
                "or update the line number if the code moved.",
            ]
        )
        raise AssertionError("\n".join(msg_lines))
