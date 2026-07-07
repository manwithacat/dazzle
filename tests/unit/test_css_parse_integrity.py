"""CSS comment-bomb gate for the Dazzle-side stylesheets — mirror of the
HM package gate (packages/hatchi-maxchi/tests/test_css_parse_integrity.py).

A ``*/`` written INSIDE a comment terminates it early; the leaked prose
becomes an invalid selector prelude that swallows the NEXT rule in the
built bundle (Tier F3: ate the command-palette overlay; Tier A2: ate
.dz-auth-page, .dz-auth-success and .dz-loading-spinner). Substring
gates can't see it — the swallowed selector still matches as text.

Invariant: strip comments exactly as a browser does (non-greedy
``/* ... */``); the residue must contain no ``*/`` (the leaked block
always ends at the comment's real closer) and balanced braces.
"""

import re
from pathlib import Path

CSS_ROOT = Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/css"

_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def test_no_comment_bombs_in_dazzle_css() -> None:
    problems: list[str] = []
    for f in sorted(CSS_ROOT.rglob("*.css")):
        if "dist" in f.parts or "vendor" in f.parts:
            continue
        residue = _COMMENT.sub("", f.read_text(encoding="utf-8"))
        rel = f.relative_to(CSS_ROOT)
        if "*/" in residue:
            line = residue[: residue.index("*/")].count("\n") + 1
            problems.append(f"{rel}: stray '*/' outside any comment (~line {line})")
        if residue.count("{") != residue.count("}"):
            problems.append(f"{rel}: unbalanced braces")
    assert not problems, "CSS comment-bomb failures (the swallowed-rule class):\n  " + "\n  ".join(
        problems
    )
