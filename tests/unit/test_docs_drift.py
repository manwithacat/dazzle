"""Gates that catch documentation drift from the parser/codebase.

Each test here asserts a one-directional invariant: the doc claims X
exists, and X must still exist in the parser. When the parser changes
and a doc lies as a result, the test fails with a message pointing
at the stale line.

The backlog post-mortem for #794 surfaced this gap: coverage curation
revealed that `CLAUDE.md` named `view`, `graph_edge`, and `graph_node`
as top-level DSL constructs when they're actually sub-keywords. Cost:
one `/improve` cycle spent disproving each.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _claude_md_constructs() -> list[str]:
    """Parse the ``**Constructs**:`` line from .claude/CLAUDE.md.

    Accepts backtick-quoted names on the same line — the canonical
    quick-reference format. Returns them in order of appearance.
    """
    text = (REPO_ROOT / ".claude" / "CLAUDE.md").read_text()
    match = re.search(r"\*\*Constructs\*\*:(.+)", text)
    assert match, "CLAUDE.md no longer has a `**Constructs**:` line"
    line = match.group(1)
    # Also absorb the parenthetical extended list that follows — it
    # names additional parser-dispatchable keywords for reference, and
    # those must also resolve (the drift test is one-way: everything
    # the doc names must exist).
    following = text.split(match.group(0), 1)[1].split("\n\n", 1)[0]
    combined = line + "\n" + following
    return [m.group(1) for m in re.finditer(r"`([a-z_]+)`", combined)]


def _parser_top_level_keywords() -> set[str]:
    """Extract the set of top-level dispatchable keywords from the
    parser's dispatch table in ``src/dazzle/core/dsl_parser_impl/__init__.py``.

    Match lines of the form ``TokenType.FOO: self._dispatch_foo,`` —
    that's the authoritative list because a keyword is only a top-level
    construct iff it has a dispatch entry there. The TokenType enum in
    ``lexer.py`` has members for sub-keywords too, but those aren't
    dispatched.
    """
    text = (REPO_ROOT / "src" / "dazzle" / "core" / "dsl_parser_impl" / "__init__.py").read_text()
    # "TokenType.FOO: self._dispatch_bar," — take the _dispatch_<name>
    # suffix rather than the enum name so the test tracks the keyword
    # as the user types it in DSL (e.g. TokenType.QUESTION_DECL →
    # _dispatch_question, keyword is `question`).
    method_names = re.findall(r"TokenType\.[A-Z_]+:\s*self\._dispatch_([a-z_]+)", text)
    # Also include the `app` keyword — it's parsed by the module-header
    # path in base.py, not via the dispatch dict, but it IS a top-level
    # construct that users type at column 0.
    return set(method_names) | {"app"}


def test_claude_md_constructs_all_exist_in_parser() -> None:
    """Every DSL construct named in CLAUDE.md must exist in the parser.

    This is a one-way gate: the parser can dispatch on more constructs
    than CLAUDE.md mentions (CLAUDE.md curates the user-facing subset).
    But any name CLAUDE.md lists must actually be a real top-level
    keyword — otherwise the doc is lying.
    """
    claimed = _claude_md_constructs()
    real = _parser_top_level_keywords()
    # Exclude `question` because the parser dispatch method is named
    # `_dispatch_question` but the keyword in the DSL is the token
    # `question_decl`. If CLAUDE.md writes `question` or `question_decl`
    # here, both are legal — we allow either to resolve.
    hidden = {"question_decl"}

    stale = [name for name in claimed if name not in real and name not in hidden]
    assert not stale, (
        f"CLAUDE.md names {stale!r} as DSL constructs, but the parser "
        f"does not dispatch on them as top-level keywords. Either:\n"
        f"  (a) remove the stale name(s) from the .claude/CLAUDE.md "
        f"`**Constructs**:` line, OR\n"
        f"  (b) add a parser dispatch entry in "
        f"src/dazzle/core/dsl_parser_impl/__init__.py.\n"
        f"Parser's real top-level set: {sorted(real)}"
    )


def test_coverage_tool_constructs_all_exist_in_parser() -> None:
    """The curated list in dazzle.cli.coverage._DSL_CONSTRUCTS (which
    feeds the ``dazzle coverage --fail-on-uncovered`` CI gate) must
    also be a subset of the parser's real dispatch table. Otherwise
    the coverage gate would chase a ghost keyword nobody can render.
    """
    from dazzle.cli.coverage import _DSL_CONSTRUCTS

    real = _parser_top_level_keywords()
    stale = [name for name in _DSL_CONSTRUCTS if name not in real]
    assert not stale, (
        f"coverage.py names {stale!r} in _DSL_CONSTRUCTS but the parser "
        f"doesn't dispatch on them. Remove them from coverage.py or "
        f"add parser dispatches."
    )
