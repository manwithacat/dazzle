"""Tests for the guide-concordance linker pass (v0.71.0).

These are unit-level tests against ``check_guide_concordance`` directly.
End-to-end coverage (via ``dazzle validate``) lives in
``test_simple_task_guide_concordance.py`` once the example app gets a
guide annotation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.core import ir
from dazzle.core.guide_concordance import check_guide_concordance


def _surface(name: str, *, actions: tuple[str, ...] = (), entity_ref: str | None = None):
    return SimpleNamespace(
        name=name,
        actions=[SimpleNamespace(name=a) for a in actions],
        sections=[],
        entity_ref=entity_ref,
    )


def _entity(name: str, *, fields: tuple[str, ...] = ()):
    return SimpleNamespace(name=name, fields=[SimpleNamespace(name=f) for f in fields])


def _persona(pid: str):
    return SimpleNamespace(id=pid)


def _step(
    name: str,
    *,
    target: str,
    kind=ir.GuideStepKind.POPOVER,
    complete_on=None,
    cta_target: str | None = None,
    audience_when: str | None = None,
) -> ir.GuideStep:
    return ir.GuideStep(
        name=name,
        kind=kind,
        title="t",
        body="b",
        target=target,
        complete_on=complete_on or ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
        cta_target=cta_target,
        audience_when=audience_when,
    )


def _guide(name: str, *, audience: str, steps: list[ir.GuideStep]) -> ir.GuideSpec:
    return ir.GuideSpec(
        name=name,
        title=name,
        audience=audience,
        steps=steps,
        step_order=[s.name for s in steps],
    )


def _run(
    *,
    guides=None,
    surfaces=None,
    entities=None,
    personas=None,
    streams=None,
):
    return check_guide_concordance(
        guides or [],
        surfaces=surfaces or [],
        entities=entities or [],
        personas=personas or [],
        streams=streams or [],
    )


# ---------------------------------------------------------------------------
# Clean case
# ---------------------------------------------------------------------------


def test_clean_guide_produces_no_errors() -> None:
    surfaces = [_surface("task_list", actions=("create",))]
    personas = [_persona("admin")]
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[_step("s1", target="surface.task_list.action.create")],
    )
    errors, warnings = _run(guides=[guide], surfaces=surfaces, personas=personas)
    assert errors == []
    assert warnings == []


# ---------------------------------------------------------------------------
# Step-reference validation errors (attachment / audience / completion / CTA)
#
# One contract, one table: a guide step carrying an invalid reference
# produces an error containing `expected`. `step_kwargs` are forwarded to
# `_step("s1", ...)`; the audience persona pool is always just `admin`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("audience", "step_kwargs", "surfaces", "entities", "expected"),
    [
        pytest.param(
            "persona = admin",
            {"target": "entity.Task.create"},
            [],
            [],
            "must start with 'surface.",
            id="target-must-start-with-surface",
        ),
        pytest.param(
            "persona = admin",
            {"target": "surface.nonexistent"},
            [],
            [],
            "target surface 'nonexistent' does not exist",
            id="target-unknown-surface",
        ),
        pytest.param(
            "persona = admin",
            {"target": "surface.task_list.action.delete"},
            [_surface("task_list", actions=("create",))],
            [],
            "has no action 'delete'",
            id="target-unknown-action",
        ),
        pytest.param(
            "persona = wizard",
            {"target": "surface.task_list"},
            [_surface("task_list")],
            [],
            "unknown persona 'wizard'",
            id="audience-unknown-persona",
        ),
        pytest.param(
            "persona = admin",
            {
                "target": "surface.task_list",
                "complete_on": ir.GuideCompleteOn(
                    kind=ir.GuideCompleteOnKind.EVENT,
                    event_ref="entity.NoSuch.created",
                ),
            },
            [_surface("task_list")],
            [],
            "unknown entity 'NoSuch'",
            id="event-completion-unknown-entity",
        ),
        pytest.param(
            "persona = admin",
            {
                "target": "surface.task_list",
                "complete_on": ir.GuideCompleteOn(
                    kind=ir.GuideCompleteOnKind.EVENT,
                    event_ref="entity.Task.exploded",
                ),
            },
            [_surface("task_list")],
            [_entity("Task")],
            "lifecycle 'exploded'",
            id="event-completion-unknown-lifecycle",
        ),
        pytest.param(
            "persona = admin",
            {
                "target": "surface.task_create",
                "complete_on": ir.GuideCompleteOn(
                    kind=ir.GuideCompleteOnKind.FIELD_FILLED,
                    field_filled="surface.task_create.field.no_such_field",
                ),
            },
            [_surface("task_create", entity_ref="Task")],
            [_entity("Task", fields=("title",))],
            "unknown field 'no_such_field'",
            id="field-filled-unknown-field",
        ),
        pytest.param(
            "persona = admin",
            {"target": "surface.task_list", "cta_target": "surface.nowhere"},
            [_surface("task_list")],
            [],
            "cta_target surface 'nowhere' does not exist",
            id="cta-target-unknown-surface",
        ),
    ],
)
def test_invalid_step_reference_errors(
    audience: str,
    step_kwargs: dict,
    surfaces: list,
    entities: list,
    expected: str,
) -> None:
    guide = _guide("g1", audience=audience, steps=[_step("s1", **step_kwargs)])
    errors, _ = _run(
        guides=[guide],
        surfaces=surfaces,
        entities=entities,
        personas=[_persona("admin")],
    )
    assert any(expected in e for e in errors), errors


# ---------------------------------------------------------------------------
# Step-order integrity
# ---------------------------------------------------------------------------


def test_step_order_references_unknown_step_errors() -> None:
    s1 = _step("s1", target="surface.task_list")
    guide = ir.GuideSpec(
        name="g1",
        title="g1",
        audience="persona = admin",
        steps=[s1],
        step_order=["s1", "s2"],  # s2 doesn't exist
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        personas=[_persona("admin")],
    )
    assert any("step_order names 's2'" in e for e in errors)


def test_step_order_duplicate_errors() -> None:
    s1 = _step("s1", target="surface.task_list")
    guide = ir.GuideSpec(
        name="g1",
        title="g1",
        audience="persona = admin",
        steps=[s1],
        step_order=["s1", "s1"],
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        personas=[_persona("admin")],
    )
    assert any("step_order lists 's1' twice" in e for e in errors)


def test_orphan_step_produces_warning_not_error() -> None:
    s1 = _step("s1", target="surface.task_list")
    s2 = _step("s2", target="surface.task_list")
    guide = ir.GuideSpec(
        name="g1",
        title="g1",
        audience="persona = admin",
        steps=[s1, s2],
        step_order=["s1"],  # s2 orphaned
    )
    errors, warnings = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        personas=[_persona("admin")],
    )
    assert errors == []
    assert any("orphan (never fires)" in w for w in warnings)


# ---------------------------------------------------------------------------
# CTA audience-access check (#1292)
# ---------------------------------------------------------------------------

from dazzle.core.ir import AccessSpec, PermissionKind, PermissionRule  # noqa: E402


def _cta_surface(name: str, *, entity_ref: str, mode: str = "create"):
    return SimpleNamespace(name=name, actions=[], sections=[], entity_ref=entity_ref, mode=mode)


def _persona_role(pid: str, role: str | None = None):
    return SimpleNamespace(id=pid, effective_role=role or pid)


def _entity_create_only(name: str, *, allowed_role: str):
    """Entity whose CREATE permit is restricted to a single role."""
    return SimpleNamespace(
        name=name,
        fields=[],
        access=AccessSpec(
            permissions=[PermissionRule(operation=PermissionKind.CREATE, personas=[allowed_role])]
        ),
    )


def test_cta_denied_for_audience_errors() -> None:
    """A create CTA whose whole audience lacks create permission fails (#1292)."""
    surfaces = [_cta_surface("system_create", entity_ref="System", mode="create")]
    entities = [_entity_create_only("System", allowed_role="admin")]
    personas = [_persona_role("ops_engineer"), _persona_role("admin")]
    guide = _guide(
        "ops_first_run",
        audience="persona = ops_engineer",
        steps=[_step("s1", target="surface.system_create", cta_target="surface.system_create")],
    )
    errors, _ = _run(guides=[guide], surfaces=surfaces, entities=entities, personas=personas)
    assert any("system_create" in e and "cannot" in e for e in errors), errors


def test_cta_allowed_for_audience_passes() -> None:
    """A create CTA whose audience holds the create permit passes."""
    surfaces = [_cta_surface("system_create", entity_ref="System", mode="create")]
    entities = [_entity_create_only("System", allowed_role="admin")]
    personas = [_persona_role("admin")]
    guide = _guide(
        "admin_setup",
        audience="persona = admin",
        steps=[_step("s1", target="surface.system_create", cta_target="surface.system_create")],
    )
    errors, _ = _run(guides=[guide], surfaces=surfaces, entities=entities, personas=personas)
    assert errors == [], errors


def test_cta_passes_when_any_audience_persona_permitted() -> None:
    """Multi-persona audience: one permitted persona is enough."""
    surfaces = [_cta_surface("system_create", entity_ref="System", mode="create")]
    entities = [_entity_create_only("System", allowed_role="admin")]
    personas = [_persona_role("ops_engineer"), _persona_role("admin")]
    guide = _guide(
        "mixed",
        audience="persona = ops_engineer or persona = admin",
        steps=[_step("s1", target="surface.system_create", cta_target="surface.system_create")],
    )
    errors, _ = _run(guides=[guide], surfaces=surfaces, entities=entities, personas=personas)
    assert errors == [], errors


def test_read_cta_not_gated_by_create_permit() -> None:
    """A read/list CTA is not subjected to the create-permit check (#1292)."""
    surfaces = [_cta_surface("alert_list", entity_ref="Alert", mode="list")]
    entities = [_entity_create_only("Alert", allowed_role="admin")]
    personas = [_persona_role("ops_engineer")]
    guide = _guide(
        "g",
        audience="persona = ops_engineer",
        steps=[_step("s1", target="surface.alert_list", cta_target="surface.alert_list")],
    )
    errors, _ = _run(guides=[guide], surfaces=surfaces, entities=entities, personas=personas)
    assert errors == [], errors
