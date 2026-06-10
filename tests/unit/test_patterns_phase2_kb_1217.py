"""#1217 Phase 2 — 7 patterns.toml entries shipped together.

Pins the canonical idioms for each supported 3NF pattern (#1241-#1247).
The MCP `knowledge` tool surfaces these entries; the regression here
guards against accidental removal and against the `pattern_count`
meta drifting out of sync.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_PATTERNS_TOML = (
    Path(__file__).parent.parent.parent
    / "src"
    / "dazzle"
    / "mcp"
    / "semantics_kb"
    / "patterns.toml"
)

# Each tuple: (pattern key, must-include substring in description, must-include
# substring in example DSL). The substrings are the *canonical* idiom — if
# someone rewrites the entry and drops the keyword that makes the pattern
# discoverable, the test fails.
_PHASE2_ENTRIES = [
    ("direct_one_to_many", "parent", "ref Order"),
    ("primary_aggregate_n_to_one", "GROUP BY", "primary_aggregate:"),
    ("junction_many_to_many", "junction", "via: UserRole"),
    ("shared_parent_join", "diamond", "share: StudentProfile"),
    ("self_referencing_hierarchy", "tree", "descendants_of self"),
    ("temporal", "interval", "temporal:"),
    # #1358: needle was `soft_delete: true`, which the parser REJECTS — the
    # keyword is a bare directive (entity.py); the KB example now parses.
    ("soft_delete", "tombstone", "soft_delete"),
]


@pytest.fixture(scope="module")
def patterns_data() -> dict:
    return tomllib.loads(_PATTERNS_TOML.read_text())


@pytest.mark.parametrize(
    ("key", "desc_needle", "example_needle"),
    _PHASE2_ENTRIES,
    ids=[k for k, *_ in _PHASE2_ENTRIES],
)
def test_phase2_pattern_entry_exists(
    patterns_data: dict, key: str, desc_needle: str, example_needle: str
) -> None:
    """Each #1217 Phase 2 pattern must be present in patterns.toml with
    its canonical idiom referenced in description + example."""
    patterns = patterns_data.get("patterns", {})
    assert key in patterns, (
        f"patterns.toml is missing `[patterns.{key}]` — #1217 Phase 2 "
        f"requires it. See tests/unit/test_patterns_subtype_of_kb_1248.py "
        f"for the precedent entry."
    )
    entry = patterns[key]
    assert entry.get("name"), f"{key} entry missing `name`"
    desc = entry.get("description", "")
    assert desc_needle.lower() in desc.lower(), (
        f"`[patterns.{key}].description` should mention '{desc_needle}' "
        f"as the canonical idiom marker; got: {desc[:120]}..."
    )
    example = entry.get("example", "")
    assert example_needle in example, (
        f"`[patterns.{key}].example` should demonstrate '{example_needle}'; got: {example[:200]}..."
    )


def test_pattern_count_meta_matches_actual_count(patterns_data: dict) -> None:
    """`[meta].pattern_count` must equal the actual number of [patterns.X]
    entries. Regression guard for the next pattern addition (same shape
    as test_patterns_subtype_of_kb_1248)."""
    declared = patterns_data["meta"]["pattern_count"]
    actual = len(patterns_data.get("patterns", {}))
    assert declared == actual, (
        f"patterns.toml [meta].pattern_count ({declared}) doesn't match "
        f"the actual entry count ({actual}). Bump [meta].pattern_count when "
        f"adding/removing a [patterns.X] entry."
    )


def test_get_dsl_patterns_exposes_phase2_entries() -> None:
    """The semantic_kb aggregator must expose all 7 Phase 2 keys so MCP
    tool calls (e.g. `get_dsl_patterns`) pick them up."""
    from dazzle.mcp.semantics_kb import get_dsl_patterns

    patterns = get_dsl_patterns().get("patterns", {})
    for key, *_ in _PHASE2_ENTRIES:
        assert key in patterns, f"get_dsl_patterns() missing '{key}'"
