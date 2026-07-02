"""Brief-enrichment tests (#spec-narrative sophistication): journeys, places,
automation, relationships, actor goals/workspaces, and the scope→English renderer.

The simple_task golden snapshot (test_spec_narrative_brief_snapshot) pins the
whole serialized shape; these tests pin the enrichment SEMANTICS on synthetic
predicates and on the richest example (fieldtest_hub: 26 stories, 2 workspaces,
2 ledgers, a transaction — the constructs the pre-enrichment brief dropped).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.spec_narrative.english import predicate_to_english

_REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# predicate → English
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        pytest.param(Tautology(), "all records", id="tautology"),
        pytest.param(
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active")),
            "its status is 'active'",
            id="column-eq-literal",
        ),
        pytest.param(
            ColumnCheck(field="owner_id", op=CompOp.EQ, value=ValueRef(current_user=True)),
            "its owner is the signed-in user",
            id="column-eq-current-user",
        ),
        pytest.param(
            ColumnCheck(field="school_id", op=CompOp.EQ, value=ValueRef(user_attr="school_id")),
            "its school is the user's school",
            id="column-eq-user-attr",
        ),
        pytest.param(
            ColumnCheck(
                field="assigned_tester_id", op=CompOp.EQ, value=ValueRef(user_attr="entity_id")
            ),
            "its assigned tester is the signed-in user",
            id="entity-id-reads-as-signed-in-user",
        ),
        pytest.param(
            ColumnCheck(field="revoked_at", op=CompOp.EQ, value=ValueRef(literal_null=True)),
            "its revoked at is empty",
            id="null-literal",
        ),
        pytest.param(
            ColumnCheck(field="status", op=CompOp.NEQ, value=ValueRef(literal="archived")),
            "its status is not 'archived'",
            id="neq",
        ),
        pytest.param(
            UserAttrCheck(field="realm", op=CompOp.EQ, user_attr="realm"),
            "its realm is the user's realm",
            id="user-attr-check",
        ),
        pytest.param(
            PathCheck(
                path=["manuscript", "assessment_event", "school_id"],
                op=CompOp.EQ,
                value=ValueRef(user_attr="school_id"),
            ),
            "the school of its manuscript → assessment event is the user's school",
            id="fk-path",
        ),
        pytest.param(
            ExistsCheck(target_entity="CohortMembership", bindings=[], negated=False),
            "a cohort membership record links it to the user",
            id="exists",
        ),
        pytest.param(
            ExistsCheck(target_entity="BlockList", bindings=[], negated=True),
            "no block list record links it to the user",
            id="not-exists",
        ),
        pytest.param(
            BoolComposite(
                op=BoolOp.OR,
                children=[
                    ColumnCheck(field="creator", op=CompOp.EQ, value=ValueRef(current_user=True)),
                    ColumnCheck(field="visibility", op=CompOp.EQ, value=ValueRef(literal="public")),
                ],
            ),
            "(its creator is the signed-in user or its visibility is 'public')",
            id="bool-or",
        ),
    ],
)
def test_predicate_to_english(predicate, expected: str) -> None:
    assert predicate_to_english(predicate) == expected


def test_unknown_node_falls_back_without_raising() -> None:
    class Weird:
        kind = "future_node_kind"

    assert predicate_to_english(Weird()) == "a declared access rule applies"


# ---------------------------------------------------------------------------
# Enriched brief on the richest example (fieldtest_hub)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fieldtest_brief():
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.spec_narrative.brief import build_brief

    return build_brief(load_project_appspec(_REPO / "examples" / "fieldtest_hub"))


def test_journeys_carry_authored_stories(fieldtest_brief) -> None:
    assert len(fieldtest_brief.journeys) >= 20  # fieldtest_hub authors 26 stories
    sample = {j.id: j for j in fieldtest_brief.journeys}
    assert all(j.actor for j in fieldtest_brief.journeys)
    assert any(j.outcomes for j in sample.values())


def test_places_exclude_framework_platform_workspace(fieldtest_brief) -> None:
    names = [p.name for p in fieldtest_brief.places]
    assert "_platform_admin" not in names
    workspaces = [p for p in fieldtest_brief.places if p.kind == "workspace"]
    assert workspaces, "fieldtest_hub declares user workspaces"
    assert all(p.contents for p in workspaces), "regions should surface as contents"


def test_actor_goals_and_explicit_workspaces(fieldtest_brief) -> None:
    by_id = {a.id: a for a in fieldtest_brief.actors}
    assert by_id["engineer"].goals, "persona goals: must reach the brief"
    assert "Engineering Dashboard" in by_id["engineer"].workspaces
    # admin's only grant was the framework platform workspace — filtered out.
    assert by_id["admin"].workspaces == []


def test_relationships_between_user_entities(fieldtest_brief) -> None:
    by_name = {d.name: d for d in fieldtest_brief.domain}
    issue_rels = {r.field: r for r in by_name["IssueReport"].relationships}
    assert issue_rels["device_id"].target == "Device"
    assert issue_rels["device_id"].required is True


def test_automation_carries_ledgers_and_transactions(fieldtest_brief) -> None:
    kinds = {a.kind for a in fieldtest_brief.automation}
    assert {"ledger", "transaction"} <= kinds


def test_scope_rules_render_in_plain_english(fieldtest_brief) -> None:
    rules = fieldtest_brief.security.scope_rules
    assert rules, "fieldtest_hub scopes all six entities"
    tester_device = [r for r in rules if r.entity == "Device" and "tester" in r.personas]
    assert tester_device
    assert any("signed-in user" in r.rule for r in tester_device)
    # No SQL/column vocabulary leaks into the prose.
    assert all("_id" not in r.rule and "%s" not in r.rule for r in rules)


def test_skeleton_gains_places_and_automation_sections(fieldtest_brief) -> None:
    populated = {s.section: s.populated for s in fieldtest_brief.skeleton}
    assert populated["where_work_happens"] is True
    assert populated["automation_and_controls"] is True


# ---------------------------------------------------------------------------
# Claim differentiation (Phase 2): apps with distinctive constructs activate
# claims a bare-CRUD app does not — the technical foundation must not read
# identically across the fleet.
# ---------------------------------------------------------------------------


def _claims_for(example: str) -> set[str]:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.spec_narrative.brief import build_brief

    brief = build_brief(load_project_appspec(_REPO / "examples" / example))
    return {c.id for c in brief.activated_claims}


def test_claims_activate_per_construct() -> None:
    # Each distinctive construct earns its claim where declared…
    assert "governed_ai" in _claims_for("llm_ticket_classifier")
    assert {"approval_controls", "sla_commitments"} <= _claims_for("support_tickets")
    assert "ledger_integrity" in _claims_for("fieldtest_hub")
    assert {"database_rls", "background_execution"} <= _claims_for("invoice_ops")
    # …and NOT where it isn't (fieldtest_hub has no approvals/SLAs/tenancy).
    assert {"approval_controls", "sla_commitments", "database_rls"}.isdisjoint(
        _claims_for("fieldtest_hub")
    )


def test_claim_sets_differ_across_the_fleet() -> None:
    sets = {
        ex: frozenset(_claims_for(ex))
        for ex in ("simple_task", "fieldtest_hub", "support_tickets", "invoice_ops")
    }
    assert len(set(sets.values())) >= 3, (
        f"technical-foundation sections would read near-identically: {sets}"
    )
