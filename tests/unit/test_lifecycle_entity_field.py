"""Tests that EntitySpec accepts an optional lifecycle field (plan task 2)."""

from dazzle.core.ir import EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)


def _minimal_fields() -> list[FieldSpec]:
    return [
        FieldSpec(
            name="id",
            type=FieldType(kind=FieldTypeKind.UUID),
            modifiers=[],
        ),
    ]


def test_entity_spec_accepts_lifecycle() -> None:
    lifecycle = LifecycleSpec(
        status_field="status",
        states=[
            LifecycleStateSpec(name="draft", order=0),
            LifecycleStateSpec(name="published", order=1),
        ],
        transitions=[
            LifecycleTransitionSpec(
                from_state="draft",
                to_state="published",
                roles=["author"],
            ),
        ],
    )

    entity = EntitySpec(
        name="Article",
        title="Article",
        fields=_minimal_fields(),
        lifecycle=lifecycle,
    )

    assert entity.lifecycle is not None
    assert entity.lifecycle.status_field == "status"
    assert len(entity.lifecycle.states) == 2
    assert entity.lifecycle.states[0].name == "draft"
    assert entity.lifecycle.states[0].order == 0
    assert entity.lifecycle.states[1].name == "published"
    assert len(entity.lifecycle.transitions) == 1
    assert entity.lifecycle.transitions[0].from_state == "draft"
    assert entity.lifecycle.transitions[0].to_state == "published"
    assert entity.lifecycle.transitions[0].roles == ["author"]


def test_entity_spec_lifecycle_default_is_none() -> None:
    entity = EntitySpec(
        name="Note",
        title="Note",
        fields=_minimal_fields(),
    )
    assert entity.lifecycle is None
