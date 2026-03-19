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


class TestSoftDeleteDetection:
    def test_detects_is_deleted_without_state_machine(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="is_deleted",
                    type=ir.FieldType(kind=ir.FieldTypeKind.BOOL),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("soft-delete" in w.lower() for w in warnings)

    def test_detects_deleted_at(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="deleted_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("soft-delete" in w.lower() for w in warnings)

    def test_detects_archived_at(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="archived_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert any("soft-delete" in w.lower() for w in warnings)

    def test_ignores_when_state_machine_exists(self) -> None:
        entity = ir.EntitySpec(
            name="Task",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="deleted_at",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATETIME),
                ),
            ],
            state_machine=ir.StateMachineSpec(
                status_field="status",
                states=["active", "archived"],
                transitions=[
                    ir.StateTransition(from_state="active", to_state="archived"),
                ],
            ),
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([entity]))
        assert not any("soft-delete" in w.lower() for w in warnings)


class TestStringlyTypedRefDetection:
    def test_detects_entity_name_field(self) -> None:
        customer = ir.EntitySpec(name="Customer", fields=[_id_field()])
        order = ir.EntitySpec(
            name="Order",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="customer_email",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([customer, order]))
        assert any("string copy" in w.lower() for w in warnings)

    def test_ignores_field_on_own_entity(self) -> None:
        """customer_name on Customer itself is NOT an anti-pattern."""
        customer = ir.EntitySpec(
            name="Customer",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="customer_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([customer]))
        assert not any("string copy" in w.lower() for w in warnings)


class TestDuplicatedRefFieldDetection:
    def test_detects_ref_field_copy(self) -> None:
        school = ir.EntitySpec(
            name="School",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        student = ir.EntitySpec(
            name="Student",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="school",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.REF,
                        ref_entity="School",
                    ),
                ),
                ir.FieldSpec(
                    name="school_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        warnings = extended_lint(_make_appspec([school, student]))
        assert any("duplicate" in w.lower() for w in warnings)

    def test_ignores_when_ref_target_not_found(self) -> None:
        """If ref target entity doesn't exist, skip check silently."""
        student = ir.EntitySpec(
            name="Student",
            fields=[
                _id_field(),
                ir.FieldSpec(
                    name="school",
                    type=ir.FieldType(
                        kind=ir.FieldTypeKind.REF,
                        ref_entity="School",
                    ),
                ),
                ir.FieldSpec(
                    name="school_name",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
            ],
        )
        from dazzle.core.validator import extended_lint

        # School entity not in appspec — should not crash
        warnings = extended_lint(_make_appspec([student]))
        assert not any("duplicate" in w.lower() for w in warnings)
