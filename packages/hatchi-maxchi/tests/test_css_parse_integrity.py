"""CSS parse-integrity gate — the comment-bomb detector.

Twice (Tier F3's ``.dz-search-input*/`` tombstone; Tier A2's
``link-button*/`` header) a ``*/`` written INSIDE a comment terminated
it early: the leaked prose becomes an invalid selector prelude and CSS
error recovery silently drops the FOLLOWING rule from every built
artifact. Contract gates can't see it (substring checks still match the
swallowed selector as text) and demos rarely exercise the dropped rule.

Invariant: strip comments exactly as a browser does (non-greedy
``/* ... */``); the residue must contain no ``*/`` (a leaked block
always ends at the comment's real closer) and balanced braces.
"""

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]

_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _css_files():
    yield from sorted((PKG / "components").glob("*.css"))
    yield from sorted((PKG / "base").glob("*.css"))
    yield from sorted((PKG / "tokens").glob("*.css"))


def test_no_comment_bombs_or_swallowed_rules() -> None:
    problems: list[str] = []
    for f in _css_files():
        residue = _COMMENT.sub("", f.read_text(encoding="utf-8"))
        if "*/" in residue:
            line = residue[: residue.index("*/")].count("\n") + 1
            problems.append(f"{f.name}: stray '*/' outside any comment (~line {line})")
        if residue.count("{") != residue.count("}"):
            problems.append(
                f"{f.name}: unbalanced braces ({residue.count('{')} vs {residue.count('}')})"
            )
    assert not problems, (
        "CSS comment-bomb / parse-integrity failures (the swallowed-rule "
        "class — see Tier F3 + A2 incidents):\n  " + "\n  ".join(problems)
    )
