"""#1248 Phase 2 (#1217) — `subtype_of:` discoverability via patterns.toml.

The pattern just shipped v0.72.0; the Phase 2 ticket lands its surface in
the semantic KB so MCP `knowledge` queries return the canonical idiom
(carrying the escape-hatch framing from `subtype_of_only_for_true_isa`).
"""

from __future__ import annotations


def test_patterns_toml_carries_subtype_of_entry() -> None:
    """The TOML must include a `[patterns.subtype_of]` table with the
    fields downstream consumers expect (name, description, example)."""
    import tomllib
    from pathlib import Path

    toml_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "semantics_kb"
        / "patterns.toml"
    )
    data = tomllib.loads(toml_path.read_text())
    patterns = data.get("patterns", {})
    assert "subtype_of" in patterns, (
        "patterns.toml is missing a subtype_of entry — Phase 2 (#1248) requires it."
    )
    entry = patterns["subtype_of"]
    # The downstream KG seeder reads name + description + example.
    assert entry.get("name"), entry
    assert "escape hatch" in entry.get("description", "").lower(), (
        "subtype_of: pattern entry must carry the escape-hatch framing — "
        "lead authors toward separate entities / state machines / nullable "
        "fields first; subtype_of: is for true ISA only. See the "
        "subtype_of_only_for_true_isa modeling-guidance entry."
    )
    assert "subtype_of: Asset" in entry.get("example", ""), entry["example"]


def test_get_dsl_patterns_returns_subtype_of() -> None:
    """The semantic_kb `get_dsl_patterns()` aggregator exposes the new
    entry so MCP tool calls (`get_dsl_patterns`) and the KG seeder both
    pick it up."""
    from dazzle.mcp.semantics_kb import get_dsl_patterns

    result = get_dsl_patterns()
    patterns = result.get("patterns", {})
    assert "subtype_of" in patterns, list(patterns.keys())


def test_pattern_count_meta_matches_actual_count() -> None:
    """The `[meta].pattern_count` field is a human-maintained crosscheck.
    Bumping it must track when new entries are added (this guards against
    the next pattern entry forgetting the bump)."""
    import tomllib
    from pathlib import Path

    toml_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "semantics_kb"
        / "patterns.toml"
    )
    data = tomllib.loads(toml_path.read_text())
    declared = data["meta"]["pattern_count"]
    actual = len(data.get("patterns", {}))
    assert declared == actual, (
        f"patterns.toml [meta].pattern_count ({declared}) doesn't match "
        f"the actual entry count ({actual}). Bump [meta].pattern_count when "
        f"adding/removing a [patterns.X] entry."
    )
