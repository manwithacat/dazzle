"""Tests for target-agnostic deployment planning (dazzle deploy plan).

The AWS-CDK generator was retired in v0.101.0 (issue #1568); `build_infra_plan`
is the salvaged, deploy-target-neutral surface over the core infra inference.
"""

from dazzle.core import ir
from dazzle.deploy import InfraPlan, build_infra_plan


def test_plan_infers_database_from_entities(simple_appspec: ir.AppSpec) -> None:
    plan = build_infra_plan(simple_appspec)
    assert isinstance(plan, InfraPlan)
    assert plan.app_name == "test_app"
    kinds = {c.kind for c in plan.components}
    assert "database" in kinds  # any app with entities needs Postgres
    assert "DATABASE_URL" in plan.required_env_vars
    assert not plan.is_stateless


def test_plan_is_target_agnostic_no_aws_or_docker(simple_appspec: ir.AppSpec) -> None:
    """The plan must not leak the retired AWS/CDK/container assumptions."""
    plan = build_infra_plan(simple_appspec)
    blob = (
        " ".join(c.summary + " " + (c.detail or "") for c in plan.components)
        + " "
        + " ".join(plan.notes)
    ).lower()
    for banned in ("ecs", "fargate", "ecr", "cloudformation", "cdk"):
        assert banned not in blob, f"plan leaked AWS-specific term: {banned!r}"
    # The buildpack/core-process framing IS expected.
    assert any("buildpack" in n.lower() or "core process" in n.lower() for n in plan.notes)


def test_plan_json_roundtrip(simple_appspec: ir.AppSpec) -> None:
    d = build_infra_plan(simple_appspec).to_dict()
    assert d["app"] == "test_app"
    assert isinstance(d["components"], list)
    assert isinstance(d["required_env_vars"], list)
    assert {"kind", "summary", "detail", "required"} <= set(d["components"][0].keys())


def test_stateless_app_has_no_components() -> None:
    empty = ir.AppSpec(
        name="empty_app",
        title="Empty",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[]),
    )
    plan = build_infra_plan(empty)
    assert plan.is_stateless
    assert plan.components == []
    assert any("stateless" in n.lower() for n in plan.notes)
