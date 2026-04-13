"""Validator tests for lifecycle: blocks on entities (plan task 4).

Covers invariants:
- status_field must reference a real enum field on the entity
- State names must match the enum's declared values
- Order values must be unique across states
- Transition from/to must reference declared states
- Evidence, when present, must be a non-empty string
"""

import pytest

from dazzle.core import ir
from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)
from dazzle.core.validator import validate_lifecycles


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _enum_field(name: str = "status", values: list[str] | None = None) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(
            kind=ir.FieldTypeKind.ENUM,
            enum_values=values or ["open", "in_progress", "resolved", "closed"],
        ),
        modifiers=[ir.FieldModifier.REQUIRED],
    )


def _str_field(name: str) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
    )


def _make_entity(
    *,
    name: str = "Ticket",
    fields: list[ir.FieldSpec] | None = None,
    lifecycle: LifecycleSpec | None = None,
) -> ir.EntitySpec:
    return ir.EntitySpec(
        name=name,
        title=name,
        fields=fields if fields is not None else [_id_field(), _enum_field()],
        lifecycle=lifecycle,
    )


def _make_appspec(entities: list[ir.EntitySpec]) -> ir.AppSpec:
    return ir.AppSpec(
        name="Test",
        domain=ir.DomainSpec(entities=entities),
        surfaces=[],
        experiences=[],
        apis=[],
        foreign_models=[],
        integrations=[],
    )


def _happy_lifecycle() -> LifecycleSpec:
    return LifecycleSpec(
        status_field="status",
        states=[
            LifecycleStateSpec(name="open", order=0),
            LifecycleStateSpec(name="in_progress", order=1),
            LifecycleStateSpec(name="resolved", order=2),
            LifecycleStateSpec(name="closed", order=3),
        ],
        transitions=[
            LifecycleTransitionSpec(
                from_state="open",
                to_state="in_progress",
                evidence="assigned_to != null",
                roles=["agent"],
            ),
            LifecycleTransitionSpec(
                from_state="in_progress",
                to_state="resolved",
                evidence="resolution != null",
                roles=["agent"],
            ),
        ],
    )


class TestValidateLifecycles:
    def test_happy_path_produces_no_findings(self) -> None:
        entity = _make_entity(lifecycle=_happy_lifecycle())
        errors, warnings = validate_lifecycles(_make_appspec([entity]))
        assert errors == []
        assert warnings == []

    def test_entity_without_lifecycle_is_ignored(self) -> None:
        entity = _make_entity(lifecycle=None)
        errors, warnings = validate_lifecycles(_make_appspec([entity]))
        assert errors == []
        assert warnings == []

    def test_status_field_must_exist_on_entity(self) -> None:
        entity = _make_entity(
            fields=[_id_field(), _str_field("title")],
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[LifecycleStateSpec(name="open", order=0)],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("status_field" in e and "status" in e for e in errors)

    def test_status_field_must_be_enum(self) -> None:
        entity = _make_entity(
            fields=[_id_field(), _str_field("status")],
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[LifecycleStateSpec(name="open", order=0)],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("enum" in e.lower() for e in errors)

    def test_state_names_must_match_enum_values(self) -> None:
        entity = _make_entity(
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[
                    LifecycleStateSpec(name="open", order=0),
                    LifecycleStateSpec(name="bogus", order=1),
                ],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("bogus" in e for e in errors)

    def test_duplicate_order_values_are_rejected(self) -> None:
        entity = _make_entity(
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[
                    LifecycleStateSpec(name="open", order=0),
                    LifecycleStateSpec(name="in_progress", order=0),
                ],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("order" in e.lower() for e in errors)

    def test_transition_from_state_must_be_declared(self) -> None:
        entity = _make_entity(
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[
                    LifecycleStateSpec(name="open", order=0),
                    LifecycleStateSpec(name="closed", order=1),
                ],
                transitions=[
                    LifecycleTransitionSpec(
                        from_state="nowhere",
                        to_state="closed",
                    )
                ],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("nowhere" in e for e in errors)

    def test_transition_to_state_must_be_declared(self) -> None:
        entity = _make_entity(
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[
                    LifecycleStateSpec(name="open", order=0),
                    LifecycleStateSpec(name="closed", order=1),
                ],
                transitions=[
                    LifecycleTransitionSpec(
                        from_state="open",
                        to_state="nowhere",
                    )
                ],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("nowhere" in e for e in errors)

    def test_empty_evidence_string_is_rejected(self) -> None:
        entity = _make_entity(
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[
                    LifecycleStateSpec(name="open", order=0),
                    LifecycleStateSpec(name="closed", order=1),
                ],
                transitions=[
                    LifecycleTransitionSpec(
                        from_state="open",
                        to_state="closed",
                        evidence="   ",
                    )
                ],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert any("evidence" in e.lower() for e in errors)

    def test_none_evidence_is_allowed(self) -> None:
        entity = _make_entity(
            lifecycle=LifecycleSpec(
                status_field="status",
                states=[
                    LifecycleStateSpec(name="open", order=0),
                    LifecycleStateSpec(name="closed", order=1),
                ],
                transitions=[
                    LifecycleTransitionSpec(
                        from_state="open",
                        to_state="closed",
                        evidence=None,
                    )
                ],
            ),
        )
        errors, _ = validate_lifecycles(_make_appspec([entity]))
        assert errors == []


@pytest.mark.parametrize(
    "states",
    [
        [
            LifecycleStateSpec(name="open", order=0),
            LifecycleStateSpec(name="in_progress", order=1),
            LifecycleStateSpec(name="resolved", order=2),
            LifecycleStateSpec(name="closed", order=3),
        ],
    ],
)
def test_lint_appspec_includes_lifecycle_check(
    states: list[LifecycleStateSpec],
) -> None:
    """Ensure the lifecycle check is registered in lint_appspec."""
    from dazzle.core.lint import lint_appspec

    entity = _make_entity(
        lifecycle=LifecycleSpec(
            status_field="status",
            states=[LifecycleStateSpec(name="bogus", order=0)],
        ),
    )
    errors, _warnings, _relevance = lint_appspec(_make_appspec([entity]))
    assert any("bogus" in e for e in errors)
