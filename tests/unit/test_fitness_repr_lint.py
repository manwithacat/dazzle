"""Lint tests for fitness.repr_fields_missing warning.

Part of Agent-Led Fitness v1 Task 2.
"""

from dazzle.core import ir
from dazzle.core.ir.fitness_repr import FitnessSpec
from dazzle.core.validator import validate_fitness_repr_fields


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _body_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="body",
        type=ir.FieldType(kind=ir.FieldTypeKind.TEXT),
    )


def _make_entity(*, name: str = "Note", fitness: FitnessSpec | None = None) -> ir.EntitySpec:
    return ir.EntitySpec(
        name=name,
        title=name,
        fields=[_id_field(), _body_field()],
        fitness=fitness,
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


def test_entity_without_repr_fields_emits_lint_warning() -> None:
    appspec = _make_appspec([_make_entity(name="Note")])
    errors, warnings = validate_fitness_repr_fields(appspec)
    assert errors == []
    matches = [w for w in warnings if "Note" in w and "repr_fields" in w]
    assert len(matches) == 1


def test_entity_with_repr_fields_does_not_emit_warning() -> None:
    appspec = _make_appspec(
        [
            _make_entity(
                name="Note",
                fitness=FitnessSpec(repr_fields=["body"]),
            )
        ]
    )
    errors, warnings = validate_fitness_repr_fields(appspec)
    assert errors == []
    matches = [w for w in warnings if "Note" in w and "repr_fields" in w]
    assert matches == []


def test_fitness_repr_warning_registered_in_lint_appspec() -> None:
    """Confirm the new check is wired into lint_appspec()."""
    from dazzle.core.lint import lint_appspec

    appspec = _make_appspec([_make_entity(name="Note")])
    _errors, warnings, _relevance = lint_appspec(appspec)
    matches = [w for w in warnings if "Note" in w and "repr_fields" in w]
    assert len(matches) == 1
