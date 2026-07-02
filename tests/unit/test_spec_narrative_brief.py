"""SpecBrief models, builder, and CLI command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.spec import spec_app
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.spec_narrative.brief import build_brief
from dazzle.spec_narrative.models import (
    ActivatedClaim,
    ActorItem,
    CapabilityItem,
    DomainItem,
    SectionPlan,
    SecurityPosture,
    SpecBrief,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- models ---------------------------------------------------------------


def test_spec_brief_serialises_round_trip():
    brief = SpecBrief(
        app_name="todo",
        app_title="Todo App",
        domain=[
            DomainItem(name="Task", title="Task", intent=None, lifecycle_states=["open", "done"])
        ],
        actors=[ActorItem(id="member", label="Member", description=None)],
        capabilities=[CapabilityItem(name="task_list", title="Tasks", entity="Task", mode="list")],
        security=SecurityPosture(
            has_row_level_security=True, scoped_entities=["Task"], persona_count=1
        ),
        activated_claims=[
            ActivatedClaim(
                id="row_level_security",
                group="security",
                audience="investor",
                claim="x",
                evidence="dazzle db verify",
            )
        ],
        skeleton=[SectionPlan(section="executive_summary", populated=True, claim_ids=[])],
    )
    dumped = brief.model_dump_json()
    restored = SpecBrief.model_validate_json(dumped)
    assert restored == brief
    assert restored.domain[0].lifecycle_states == ["open", "done"]


# --- builder --------------------------------------------------------------


def test_build_brief_plain_app_has_no_rls_claim():
    # custom_renderer is a scope-free probe fixture.
    brief = build_brief(load_project_appspec(REPO_ROOT / "fixtures/custom_renderer"))
    assert brief.app_name
    assert brief.domain, "expected at least one domain item"
    assert brief.security.has_row_level_security is False
    claim_ids = {c.id for c in brief.activated_claims}
    assert "scope_filtering" not in claim_ids
    assert "database_rls" not in claim_ids
    # framework constants always present
    assert "postgres_backed" in claim_ids
    # every section appears in the skeleton, in fixed order
    sections = [s.section for s in brief.skeleton]
    assert sections == [
        "executive_summary",
        "what_it_does",
        "who_uses_it",
        "where_work_happens",
        "how_work_flows",
        "automation_and_controls",
        "technical_foundation",
        "compliance_posture",
    ]


def test_build_brief_excludes_framework_platform_entities():
    brief = build_brief(load_project_appspec(REPO_ROOT / "examples/simple_task"))
    names = {d.name for d in brief.domain}
    # user-modelled entities present
    assert "Task" in names
    # framework plumbing (domain == "platform") excluded
    for plumbing in ("AIJob", "FeedbackReport", "SystemHealth", "SystemMetric", "DeployHistory"):
        assert plumbing not in names, f"{plumbing} leaked into the stakeholder brief"


def test_build_brief_scoped_but_untenanted_app_claims_app_layer_not_database_rls():
    # rbac_validation: scope rules, NO tenancy → app-layer scope filtering only.
    # It must NOT claim database-enforced RLS (the overstatement the split fixes).
    brief = build_brief(load_project_appspec(REPO_ROOT / "fixtures/rbac_validation"))
    claim_ids = {c.id for c in brief.activated_claims}
    assert "scope_filtering" in claim_ids
    assert "database_rls" not in claim_ids
    assert brief.security.has_row_level_security is True
    assert brief.security.scoped_entities, "expected scoped entity names"
    tech = next(s for s in brief.skeleton if s.section == "technical_foundation")
    assert "scope_filtering" in tech.claim_ids


def test_build_brief_tenant_app_activates_database_rls_and_multi_tenant():
    # tenant_rls: shared_schema tenancy → genuine Postgres RLS + multi-tenant.
    brief = build_brief(load_project_appspec(REPO_ROOT / "fixtures/tenant_rls"))
    claim_ids = {c.id for c in brief.activated_claims}
    assert "database_rls" in claim_ids
    assert "multi_tenant" in claim_ids


def test_build_brief_excludes_framework_surfaces_from_capabilities():
    brief = build_brief(load_project_appspec(REPO_ROOT / "examples/simple_task"))
    cap_names = {c.name for c in brief.capabilities}
    domain_names = {d.name for d in brief.domain}
    for cap in brief.capabilities:
        # no admin dashboard plumbing
        assert not cap.name.startswith("_admin_"), f"admin surface {cap.name} leaked"
        # no surface targeting a framework entity (e.g. FeedbackReport)
        if cap.entity is not None:
            assert cap.entity in domain_names, (
                f"surface {cap.name} targets non-user entity {cap.entity}"
            )
    # the feedback widget surfaces (over framework FeedbackReport) are gone
    assert "feedback_create" not in cap_names
    assert "feedback_admin" not in cap_names


def test_build_brief_compliance_section_only_when_evidence():
    plain = build_brief(load_project_appspec(REPO_ROOT / "examples/simple_task"))
    plain_compliance = next(s for s in plain.skeleton if s.section == "compliance_posture")
    assert plain_compliance.populated is False


# --- CLI ------------------------------------------------------------------


def test_cli_spec_brief_emits_valid_json():
    runner = CliRunner()
    result = runner.invoke(
        spec_app,
        ["brief", "--project", str(REPO_ROOT / "examples/simple_task"), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["app_name"]
    assert isinstance(payload["activated_claims"], list)
    assert any(c["id"] == "postgres_backed" for c in payload["activated_claims"])


def test_cli_spec_brief_text_format_runs():
    runner = CliRunner()
    result = runner.invoke(
        spec_app,
        ["brief", "--project", str(REPO_ROOT / "examples/simple_task"), "--format", "text"],
    )
    assert result.exit_code == 0, result.output
    assert "SPEC BRIEF" in result.stdout


# --- MCP read-op (dsl:brief) ----------------------------------------------


def test_mcp_dsl_brief_op_returns_same_brief_as_builder():
    from dazzle.mcp.server.handlers_consolidated import handle_dsl

    out = handle_dsl(
        {"operation": "brief", "project_path": str(REPO_ROOT / "examples/simple_task")}
    )
    payload = json.loads(out)
    expected = build_brief(load_project_appspec(REPO_ROOT / "examples/simple_task"))
    assert payload == json.loads(expected.model_dump_json(indent=2))


def test_mcp_dsl_brief_op_in_registry_enum():
    from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

    dsl_tool = next(t for t in get_all_consolidated_tools() if t.name == "dsl")
    enum = dsl_tool.inputSchema["properties"]["operation"]["enum"]
    assert "brief" in enum
