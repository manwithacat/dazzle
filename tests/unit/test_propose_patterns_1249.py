"""#1249 — bootstrap MCP per-pattern recogniser.

`spec_analyze(operation='propose_patterns')` walks the spec text against
two trigger sources:

  - `patterns.toml` `[patterns.X].triggers` — positive proposals
  - `inference_kb.toml` `[[modeling_guidance]].triggers` — anti-pattern
    flags (only entries with an `anti_pattern` field are surfaced)

Each test below feeds a synthetic spec that names the pattern's domain,
then asserts the right pattern surfaces in the proposals + the polymorphic
anti-pattern fires when the Rails idiom appears.
"""

from __future__ import annotations

import json

import pytest

from dazzle.mcp.server.handlers.spec_analyze import handle_spec_analyze


def _propose(spec_text: str) -> dict:
    raw = handle_spec_analyze({"operation": "propose_patterns", "spec_text": spec_text})
    return json.loads(raw)


def _proposal_ids(result: dict) -> list[str]:
    return [p["pattern_id"] for p in result.get("pattern_proposals", [])]


def _antipattern_ids(result: dict) -> list[str]:
    return [p["guidance_id"] for p in result.get("antipattern_flags", [])]


# ─────────────────────────────────────────────────────────────────────────
# Positive proposals — one test per Phase 2 pattern
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("pattern_id", "spec"),
    [
        (
            "direct_one_to_many",
            "An Order has many LineItem rows. Each Order owns a list of items.",
        ),
        (
            "primary_aggregate_n_to_one",
            "Show total revenue per Customer and the open count per Repository.",
        ),
        (
            "junction_many_to_many",
            "Users can have many roles and roles have many users — a many-to-many relationship.",
        ),
        (
            "shared_parent_join",
            "ClassEnrolment and MarkingResult share a parent (StudentProfile); a diamond join "
            "between source and aggregated entity.",
        ),
        (
            "self_referencing_hierarchy",
            "Departments form a hierarchy — each Department has a parent Department. We need "
            "the manager chain across the org chart.",
        ),
        (
            "temporal",
            "Employment history with start_date and end_date — surfaces default to the "
            "currently active row but allow historical as-of lookups.",
        ),
        (
            "soft_delete",
            "Users can be deactivated but we keep history. Audit needs to see deleted_at "
            "tombstones; we don't physically delete.",
        ),
        (
            "subtype_of",
            "We have different kinds of Asset — Vehicle is_a Asset, Building is a kind of "
            "Asset, etc. We need polymorphic queries across mixed kinds.",
        ),
    ],
)
def test_proposes_pattern_for_matching_spec(pattern_id: str, spec: str) -> None:
    """Each Phase 2 pattern surfaces when the spec uses one of its triggers."""
    result = _propose(spec)
    ids = _proposal_ids(result)
    assert pattern_id in ids, (
        f"Expected `{pattern_id}` in pattern_proposals for spec: {spec!r}; "
        f"got {ids}. Check patterns.toml [patterns.{pattern_id}].triggers."
    )


def test_proposal_carries_matched_triggers_and_hint() -> None:
    """Each proposal must include the triggers that fired (so the agent
    can verify) and a `hint` pointing at the knowledge tool."""
    result = _propose("Employment history with start_date and end_date.")
    temporal = next((p for p in result["pattern_proposals"] if p["pattern_id"] == "temporal"), None)
    assert temporal is not None, result
    assert temporal["matched_triggers"], "matched_triggers must not be empty"
    assert "knowledge" in temporal["hint"]
    assert "temporal" in temporal["hint"]


def test_no_proposal_when_spec_does_not_match_any_pattern() -> None:
    """Bare-bones spec with no recognisable shape returns empty proposals
    (regression guard against spurious matches from generic phrases)."""
    result = _propose("A widget has a name.")
    # `direct_one_to_many` shouldn't fire on "has a name" — the trigger
    # is "has many", not "has a". This guards the substring approach
    # from over-matching common English.
    assert _proposal_ids(result) == [], result


# ─────────────────────────────────────────────────────────────────────────
# Anti-pattern flagging
# ─────────────────────────────────────────────────────────────────────────


def test_flags_polymorphic_association_antipattern() -> None:
    """When the spec describes Rails-style polymorphic association (e.g.
    a Comment that points at any of N target tables via subject_type +
    subject_id), the recogniser MUST flag it — that's the #1240
    wontfix-by-design inoculation surfacing through bootstrap."""
    result = _propose(
        "We need a Comment entity with subject_type and subject_id so comments can "
        "attach to any entity — polymorphic association across Articles, Issues, and "
        "Manuscripts."
    )
    flags = _antipattern_ids(result)
    assert "polymorphic_association_antipattern" in flags, (
        f"polymorphic_association_antipattern must fire on Rails-style "
        f"discriminator FKs; got {flags}"
    )


def test_antipattern_flag_carries_interrogation_hint() -> None:
    """Anti-pattern flags must include the matched triggers + a hint
    pointing at the inference KB so the agent can read the four-question
    interrogation."""
    result = _propose("polymorphic association across multiple entity types")
    flag = next(
        (
            f
            for f in result["antipattern_flags"]
            if f["guidance_id"] == "polymorphic_association_antipattern"
        ),
        None,
    )
    assert flag is not None, result
    assert flag["matched_triggers"]
    assert "inference" in flag["hint"].lower() or "knowledge" in flag["hint"].lower()
    assert flag.get("anti_pattern"), "anti_pattern field must be set"


def test_no_antipattern_flag_when_spec_uses_canonical_idiom() -> None:
    """The polymorphic_association_antipattern triggers must NOT fire
    when the spec uses the canonical alternatives (per-target refs,
    event-stream entity, per-pair junctions, subtype_of:)."""
    result = _propose(
        "ArticleComment belongs to Article. InvoiceComment belongs to Invoice. "
        "Each comment type has its own retention rules and audit trail."
    )
    flags = _antipattern_ids(result)
    assert "polymorphic_association_antipattern" not in flags, (
        f"Per-target entities is the canonical Option 1 — must not be flagged. {result}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Schema regression
# ─────────────────────────────────────────────────────────────────────────


def test_propose_patterns_requires_spec_text() -> None:
    """Operation must error cleanly when spec_text is missing."""
    raw = handle_spec_analyze({"operation": "propose_patterns"})
    result = json.loads(raw)
    assert "error" in result or "spec_text" in result.get("message", "").lower()


def test_bootstrap_briefing_surfaces_pattern_proposals() -> None:
    """End-to-end: bootstrap's cognition pass includes pattern_proposals +
    antipattern_flags in the briefing's `analysis` slot. The agent reads
    this; if the field is missing, the recogniser is silently inert."""
    from dazzle.mcp.server.handlers.bootstrap import _run_cognition_pass

    spec = (
        "App for tracking employments. Each Person has many Employment rows with "
        "start_date and end_date. Surfaces default to currently active employment "
        "but support historical as-of lookups."
    )
    raw = _run_cognition_pass(spec, spec_source="test")
    briefing = json.loads(raw)
    analysis = briefing["analysis"]
    assert "pattern_proposals" in analysis, briefing
    assert "antipattern_flags" in analysis, briefing
    proposal_ids = [p["pattern_id"] for p in analysis["pattern_proposals"]]
    assert "temporal" in proposal_ids, (
        f"Bootstrap briefing must surface the temporal pattern for an "
        f"employment-history spec; got {proposal_ids}"
    )
    assert "direct_one_to_many" in proposal_ids, (
        f"`Person has many Employment rows` must propose direct_one_to_many; got {proposal_ids}"
    )
