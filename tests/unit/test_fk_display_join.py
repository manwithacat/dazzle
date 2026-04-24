"""FK display-only JOIN path on RelationLoader (#865).

The workspace-region code path only needs each FK's display value to render
``_display`` columns — not the full related row. Before this fix, ``repo.list``
always issued one follow-up ``SELECT *`` per FK relation via the batched
``_load_to_one`` path: 1 + N queries per region. For AegisMark's teacher
workspace (14 regions × ~3 FKs each) that's ~50+ round-trips per page.

``build_display_join_plan`` + ``apply_display_joins_to_rows`` collapse the
N follow-ups into a single LEFT JOIN'd base query. Relations that lack a
``display_field`` fall back to the existing batched path, so the fast path
is an opt-in optimisation rather than a replacement.
"""

from __future__ import annotations

from dazzle_back.runtime.relation_loader import (
    RelationInfo,
    RelationLoader,
    RelationRegistry,
)


def _registry_with(
    rel_from: str,
    rel_name: str,
    rel_to: str,
    fk_field: str,
    display_field: str | None,
) -> RelationRegistry:
    registry = RelationRegistry()
    registry.register(
        rel_from,
        RelationInfo(
            name=rel_name,
            from_entity=rel_from,
            to_entity=rel_to,
            kind="many_to_one",
            foreign_key_field=fk_field,
        ),
    )
    if display_field:
        registry.display_fields[rel_to] = display_field
    return registry


class TestBuildDisplayJoinPlan:
    def test_emits_join_and_alias_column_for_registered_display(self) -> None:
        registry = _registry_with("Order", "customer", "Customer", "customer_id", "name")
        loader = RelationLoader(registry=registry, entities=[])

        joins, extras, fallback = loader.build_display_join_plan("Order", ["customer"])

        assert len(joins) == 1
        assert len(extras) == 1
        assert fallback == []
        # JOIN should reference the quoted target table + the FK column
        assert '"Customer"' in joins[0]
        assert '"customer_id"' in joins[0]
        assert '"_fkd_customer"' in joins[0]
        # Extra column should project display_field under the relation alias
        assert '"_fkd_customer"."name"' in extras[0]
        assert 'AS "customer__display"' in extras[0]

    def test_relation_without_display_field_falls_back(self) -> None:
        registry = _registry_with("Order", "customer", "Customer", "customer_id", None)
        loader = RelationLoader(registry=registry, entities=[])

        joins, extras, fallback = loader.build_display_join_plan("Order", ["customer"])

        assert joins == []
        assert extras == []
        assert fallback == ["customer"]

    def test_to_many_relation_falls_back(self) -> None:
        registry = RelationRegistry()
        registry.register(
            "Customer",
            RelationInfo(
                name="orders",
                from_entity="Customer",
                to_entity="Order",
                kind="one_to_many",
                foreign_key_field="customer_id",
            ),
        )
        registry.display_fields["Order"] = "name"
        loader = RelationLoader(registry=registry, entities=[])

        joins, extras, fallback = loader.build_display_join_plan("Customer", ["orders"])

        assert joins == []
        assert extras == []
        assert fallback == ["orders"]

    def test_mixed_includes_split_between_fast_path_and_fallback(self) -> None:
        registry = RelationRegistry()
        registry.register(
            "Order",
            RelationInfo(
                name="customer",
                from_entity="Order",
                to_entity="Customer",
                kind="many_to_one",
                foreign_key_field="customer_id",
            ),
        )
        registry.register(
            "Order",
            RelationInfo(
                name="region",
                from_entity="Order",
                to_entity="Region",
                kind="many_to_one",
                foreign_key_field="region_id",
            ),
        )
        registry.display_fields["Customer"] = "name"
        # Region intentionally has no display_field
        loader = RelationLoader(registry=registry, entities=[])

        joins, extras, fallback = loader.build_display_join_plan("Order", ["customer", "region"])

        assert len(joins) == 1
        assert len(extras) == 1
        assert fallback == ["region"]


class TestApplyDisplayJoinsToRows:
    def test_folds_display_column_into_fk_dict(self) -> None:
        registry = _registry_with("Order", "customer", "Customer", "customer_id", "name")
        loader = RelationLoader(registry=registry, entities=[])

        rows = [
            {"id": "o-1", "customer_id": "c-1", "customer__display": "Alice"},
            {"id": "o-2", "customer_id": "c-2", "customer__display": "Bob"},
        ]
        result = loader.apply_display_joins_to_rows(rows, "Order", ["customer"])

        assert result[0]["customer"] == {"id": "c-1", "__display__": "Alice"}
        assert result[1]["customer"] == {"id": "c-2", "__display__": "Bob"}
        # The temporary display column should be consumed, not leaked.
        assert "customer__display" not in result[0]
        assert "customer__display" not in result[1]

    def test_null_fk_produces_none(self) -> None:
        registry = _registry_with("Order", "customer", "Customer", "customer_id", "name")
        loader = RelationLoader(registry=registry, entities=[])

        rows = [{"id": "o-1", "customer_id": None, "customer__display": None}]
        result = loader.apply_display_joins_to_rows(rows, "Order", ["customer"])

        assert result[0]["customer"] is None

    def test_missing_display_column_does_not_crash(self) -> None:
        """A relation in ``include`` that didn't JOIN (fallback) has no
        ``{rel}__display`` key — the helper must leave those alone."""
        registry = _registry_with("Order", "customer", "Customer", "customer_id", None)
        loader = RelationLoader(registry=registry, entities=[])

        rows = [{"id": "o-1", "customer_id": "c-1"}]  # no customer__display
        result = loader.apply_display_joins_to_rows(rows, "Order", ["customer"])

        # Row passed through unchanged — the batched path will populate customer.
        assert "customer" not in result[0]


class TestQueryBuilderJoinWiring:
    def test_joins_and_extra_cols_appear_in_select(self) -> None:
        from dazzle_back.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Order", placeholder_style="%s")
        builder.joins = [
            'LEFT JOIN "Customer" AS "_fkd_customer" ON "_fkd_customer".id = "Order"."customer_id"'
        ]
        builder.extra_select_cols = ['"_fkd_customer"."name" AS "customer__display"']

        sql, _ = builder.build_select()

        assert '"Order".*' in sql
        assert '"_fkd_customer"."name" AS "customer__display"' in sql
        assert 'LEFT JOIN "Customer"' in sql

    def test_no_joins_base_select_unchanged(self) -> None:
        from dazzle_back.runtime.query_builder import QueryBuilder

        builder = QueryBuilder(table_name="Order", placeholder_style="%s")
        sql, _ = builder.build_select()

        assert sql.startswith("SELECT * FROM")
