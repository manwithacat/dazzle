"""Tests for the guide-concordance linker pass (v0.71.0).

These are unit-level tests against ``check_guide_concordance`` directly.
End-to-end coverage (via ``dazzle validate``) lives in
``test_simple_task_guide_concordance.py`` once the example app gets a
guide annotation.
"""

from __future__ import annotations

from types import SimpleNamespace

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
# Attachment errors
# ---------------------------------------------------------------------------


def test_target_must_start_with_surface() -> None:
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[_step("s1", target="entity.Task.create")],
    )
    errors, _ = _run(guides=[guide], personas=[_persona("admin")])
    assert any("must start with 'surface." in e for e in errors)


def test_target_unknown_surface_errors() -> None:
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[_step("s1", target="surface.nonexistent")],
    )
    errors, _ = _run(guides=[guide], personas=[_persona("admin")])
    assert any("target surface 'nonexistent' does not exist" in e for e in errors)


def test_target_unknown_action_errors() -> None:
    surfaces = [_surface("task_list", actions=("create",))]
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[_step("s1", target="surface.task_list.action.delete")],
    )
    errors, _ = _run(guides=[guide], surfaces=surfaces, personas=[_persona("admin")])
    assert any("has no action 'delete'" in e for e in errors)


# ---------------------------------------------------------------------------
# Audience errors
# ---------------------------------------------------------------------------


def test_unknown_persona_in_audience_errors() -> None:
    guide = _guide(
        "g1",
        audience="persona = wizard",
        steps=[_step("s1", target="surface.task_list")],
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        personas=[_persona("admin")],
    )
    assert any("unknown persona 'wizard'" in e for e in errors)


# ---------------------------------------------------------------------------
# Completion errors
# ---------------------------------------------------------------------------


def test_event_completion_unknown_entity_errors() -> None:
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[
            _step(
                "s1",
                target="surface.task_list",
                complete_on=ir.GuideCompleteOn(
                    kind=ir.GuideCompleteOnKind.EVENT,
                    event_ref="entity.NoSuch.created",
                ),
            )
        ],
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        personas=[_persona("admin")],
    )
    assert any("unknown entity 'NoSuch'" in e for e in errors)


def test_event_completion_unknown_lifecycle_errors() -> None:
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[
            _step(
                "s1",
                target="surface.task_list",
                complete_on=ir.GuideCompleteOn(
                    kind=ir.GuideCompleteOnKind.EVENT,
                    event_ref="entity.Task.exploded",
                ),
            )
        ],
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        entities=[_entity("Task")],
        personas=[_persona("admin")],
    )
    assert any("lifecycle 'exploded'" in e for e in errors)


def test_field_filled_unknown_field_errors() -> None:
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[
            _step(
                "s1",
                target="surface.task_create",
                complete_on=ir.GuideCompleteOn(
                    kind=ir.GuideCompleteOnKind.FIELD_FILLED,
                    field_filled="surface.task_create.field.no_such_field",
                ),
            )
        ],
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_create", entity_ref="Task")],
        entities=[_entity("Task", fields=("title",))],
        personas=[_persona("admin")],
    )
    assert any("unknown field 'no_such_field'" in e for e in errors)


# ---------------------------------------------------------------------------
# CTA target errors
# ---------------------------------------------------------------------------


def test_cta_target_unknown_surface_errors() -> None:
    guide = _guide(
        "g1",
        audience="persona = admin",
        steps=[
            _step(
                "s1",
                target="surface.task_list",
                cta_target="surface.nowhere",
            )
        ],
    )
    errors, _ = _run(
        guides=[guide],
        surfaces=[_surface("task_list")],
        personas=[_persona("admin")],
    )
    assert any("cta_target surface 'nowhere' does not exist" in e for e in errors)


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
