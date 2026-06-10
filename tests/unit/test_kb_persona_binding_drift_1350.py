"""#1350: KB and docs must not teach the removed `for <persona>:` binding.

#998 renamed the persona/scope binding introducer from `for` to `as`; `for` is a
hard parse error. The KB (semantics_kb TOMLs, glossary, cli_help), the grammar
generator, and the reference/example docs all carried stale `for <persona>:`
examples for months — actively mis-training agents whose canonical syntax
lookup is `knowledge(operation='concept', ...)`.

This gate greps every agent-facing knowledge source for the dead shape. A line
consisting solely of `for <ident>:` cannot be valid DSL or Python (Python's
`for` always has ` in `), so any hit is a stale persona block.

docs/history/ is excluded — those files are point-in-time snapshots.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

DEAD_PERSONA_BLOCK = re.compile(r"^\s*for [a-z_]+:\s*$", re.MULTILINE)

SCANNED_SOURCES: list[Path] = sorted(
    [
        *(REPO_ROOT / "src/dazzle/mcp/semantics_kb").glob("*.toml"),
        REPO_ROOT / "src/dazzle/mcp/server/glossary.py",
        REPO_ROOT / "src/dazzle/mcp/cli_help.py",
        REPO_ROOT / "src/dazzle/core/grammar_gen.py",
        *(REPO_ROOT / "docs/reference").glob("*.md"),
        *(REPO_ROOT / "docs/examples").glob("*.md"),
        *(REPO_ROOT / "docs/counter-priors").glob("*.md"),
    ]
)


@pytest.mark.parametrize("path", SCANNED_SOURCES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_dead_for_persona_binding(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    hits = [
        f"{path.relative_to(REPO_ROOT)}:{text[: m.start()].count(chr(10)) + 1}: {m.group().strip()}"
        for m in DEAD_PERSONA_BLOCK.finditer(text)
    ]
    assert not hits, (
        "Stale `for <persona>:` binding (removed in #998 — use `as`):\n  "
        + "\n  ".join(hits)
        + "\nRewrite to `as <persona>:` (ux variants) or `as: <personas>` (entity scope rules)."
    )


def test_scanned_sources_exist() -> None:
    # If a scanned path disappears in a refactor, fail loudly rather than
    # silently shrinking coverage.
    assert len(SCANNED_SOURCES) > 20, SCANNED_SOURCES
    for required in ("ux.toml", "glossary.py", "cli_help.py", "grammar_gen.py", "grammar.md"):
        assert any(p.name == required for p in SCANNED_SOURCES), f"missing {required}"
