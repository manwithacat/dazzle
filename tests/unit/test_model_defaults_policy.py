"""Gate: no hardcoded Claude model IDs outside dazzle.core.model_defaults (#1368).

Before this gate, six call sites each pinned their own model ID and
rotted independently — the most common pin (claude-sonnet-4-20250514)
was four days from API retirement when the audit caught it. The fix is
structural: one module owns the IDs and pricing, everything else
imports from it, and this test makes a new stray literal a CI failure.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "dazzle"

DEFAULTS_MODULE = SRC / "core" / "model_defaults.py"

# Files allowed to contain Claude model-ID literals beyond the defaults
# module itself. dsl_parser_impl/llm.py shows model IDs in DSL syntax
# examples (docstring + lexer comment) — those are user-app content, but
# the second test below keeps them on the current catalog so they can't
# rot to a retired ID.
ALLOWED_FILES = {
    DEFAULTS_MODULE,
    SRC / "core" / "dsl_parser_impl" / "llm.py",
}

# Matches Claude model IDs (claude-sonnet-4-6, claude-3-opus-20240229,
# claude-fable-5, ...) but not product names like claude-code or
# claude-in-chrome.
MODEL_ID_RE = re.compile(r"claude-(?:fable|opus|sonnet|haiku|instant|[0-9])[a-z0-9.-]*")


def _scan(path: Path) -> list[tuple[int, str]]:
    hits = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        for match in MODEL_ID_RE.finditer(line):
            hits.append((lineno, match.group(0)))
    return hits


def test_no_model_id_literals_outside_defaults_module() -> None:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path in ALLOWED_FILES:
            continue
        for lineno, model_id in _scan(path):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {model_id}")
    assert not offenders, (
        "Hardcoded Claude model IDs found outside "
        "src/dazzle/core/model_defaults.py:\n  "
        + "\n  ".join(offenders)
        + "\nImport DEFAULT_JUDGMENT_MODEL / DEFAULT_MECHANICAL_MODEL / "
        "ANTHROPIC_PRICING_PER_MTOK from dazzle.core.model_defaults instead "
        "(see that module's docstring for the tier policy)."
    )


def test_allowed_example_literals_are_on_the_current_catalog() -> None:
    """Syntax-example literals must be IDs the defaults module knows.

    This keeps docstring/comment examples from quietly aging onto
    retired model IDs: when the catalog in model_defaults.py is
    updated, any example still naming a dropped ID fails here.
    """
    from dazzle.core.model_defaults import ANTHROPIC_PRICING_PER_MTOK

    catalog = set(ANTHROPIC_PRICING_PER_MTOK)
    stale = []
    for path in sorted(ALLOWED_FILES - {DEFAULTS_MODULE}):
        for lineno, model_id in _scan(path):
            if model_id not in catalog:
                stale.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {model_id}")
    assert not stale, (
        "Model-ID examples reference IDs not in "
        "dazzle.core.model_defaults.ANTHROPIC_PRICING_PER_MTOK "
        "(likely retired):\n  " + "\n  ".join(stale)
    )


def test_defaults_are_priced() -> None:
    from dazzle.core import model_defaults as md

    assert md.DEFAULT_JUDGMENT_MODEL in md.ANTHROPIC_PRICING_PER_MTOK
    assert md.DEFAULT_MECHANICAL_MODEL in md.ANTHROPIC_PRICING_PER_MTOK
