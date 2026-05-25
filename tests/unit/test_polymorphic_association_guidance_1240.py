"""#1240 wontfix-by-design — polymorphic association is a Rails idiosyncrasy.

The framework's MCP `knowledge` tool must serve agents the inoculation
against polymorphic-association proposals. This test pins the
`[[modeling_guidance]]` entry in `inference_kb.toml` (and exposes it via
the lookup machinery) so the guidance can't be silently regressed.

See:
- ADR-0027 — no polymorphic_ref: keyword now or planned
- ~/Desktop/issue-1240-analysis.md — the underlying interrogation
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_INFERENCE_KB = Path(__file__).parent.parent.parent / "src" / "dazzle" / "mcp" / "inference_kb.toml"


def _load_guidance() -> list[dict]:
    data = tomllib.loads(_INFERENCE_KB.read_text())
    return data.get("modeling_guidance", [])


def test_polymorphic_association_guidance_present() -> None:
    """The inference KB must carry the `polymorphic_association_antipattern`
    [[modeling_guidance]] entry. If this fails the inoculation is gone and
    agents will propose Rails-style polymorphic FKs unopposed."""
    ids = [g.get("id") for g in _load_guidance()]
    assert "polymorphic_association_antipattern" in ids, ids


def test_polymorphic_guidance_has_triggers_covering_common_aliases() -> None:
    """The trigger list must catch the spellings agents actually use:
    Rails terminology ("belongs_to polymorphic"), the (type, id) shape,
    and the colloquial English forms ("comments on any entity", "tags
    across entities")."""
    entry = next(
        g for g in _load_guidance() if g.get("id") == "polymorphic_association_antipattern"
    )
    triggers = " ".join(entry.get("triggers", [])).lower()
    # Rails idiom — the most common reason an agent would propose this.
    assert "polymorphic" in triggers
    # The shape signature an agent might describe in plain English.
    assert "subject_type" in triggers or "commentable_type" in triggers
    # The use cases the analysis interrogated.
    for needle in ("comment", "attachment", "tag"):
        assert needle in triggers, f"trigger list should cover '{needle}'; got {triggers}"


def test_polymorphic_guidance_frames_anti_pattern_and_alternatives() -> None:
    """The entry must be framed as `anti_pattern` + `prefer` — not a
    neutral description. The agent reading this must come away with the
    refusal, not a feature description."""
    entry = next(
        g for g in _load_guidance() if g.get("id") == "polymorphic_association_antipattern"
    )
    assert entry.get("anti_pattern"), entry
    prefer = entry.get("prefer", "").lower()
    # The four-question interrogation from the analysis.
    assert "ui-driven" in prefer or "ui driven" in prefer
    assert "event" in prefer
    assert "junction" in prefer
    assert "subtype_of" in prefer or "tpt" in prefer
    # The "do not propose" agent guidance.
    rationale = entry.get("rationale", "").lower()
    assert "rails" in rationale, "rationale should name the source of the smell"
    assert "polymorphic_ref" in rationale, (
        "rationale should explicitly state Dazzle has no polymorphic_ref: keyword"
    )


def test_adr_0027_exists_and_references_decision() -> None:
    """The decision must live in an ADR so future agents can find it via
    the doc tree, not just the KB."""
    adr = Path(__file__).parent.parent.parent / "docs" / "adr" / "0027-no-polymorphic-ref.md"
    assert adr.exists(), f"ADR-0027 must exist at {adr}"
    body = adr.read_text().lower()
    assert "wontfix" in body or "wont-fix" in body or "won't fix" in body, (
        "ADR-0027 must state the wontfix-by-design decision explicitly"
    )
    assert "rails" in body, "ADR-0027 must name the source of the smell"
    assert "polymorphic_ref" in body
