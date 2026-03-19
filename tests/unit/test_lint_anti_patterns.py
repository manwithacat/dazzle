"""Tests for modeling anti-pattern lint warnings."""

from __future__ import annotations

from dazzle.core import ir


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _make_appspec(entities: list[ir.EntitySpec]) -> ir.AppSpec:
    return ir.AppSpec(
        name="test",
        version="1.0.0",
        domain=ir.DomainSpec(entities=entities),
        surfaces=[],
    )


class TestPolymorphicPairDetection:
    def test_detects_type_plus_id_pair(self) -> None:
        entity = ir.EntitySpec(
            name="Comment",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="commentable_type",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.ENUM,
                        enum_values=["post", "photo"],
                    ),
                ),
                ir.FieldSpec(
                    name="commentable_id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("polymorphic" in w.lower() for w in warnings)

    def test_ignores_unrelated_type_field(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="task_type",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.ENUM,
                        enum_values=["bug", "feature"],
                    ),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert not any("polymorphic" in w.lower() for w in warnings)


class TestGodEntityDetection:
    def test_detects_entity_with_too_many_fields(self) -> None:
        fields = [_id_field()] + [
            ir.FieldSpec(
                name=f"field_{i}",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR),
            )
            for i in range(16)
        ]
        entity = ir.EntitySpec(name="GodEntity", fields=fields)
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("decompos" in w.lower() for w in warnings)

    def test_ignores_normal_entity(self) -> None:
        fields = [_id_field()] + [
            ir.FieldSpec(
                name=f"field_{i}",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR),
            )
            for i in range(5)
        ]
        entity = ir.EntitySpec(name="NormalEntity", fields=fields)
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert not any("decompos" in w.lower() for w in warnings)
