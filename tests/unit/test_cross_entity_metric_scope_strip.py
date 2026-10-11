"""Cycle 1911 — cross-entity metrics strip source ``__scope_predicate``.

When a metrics region ``source: Invoice`` declares ``count(InvoiceNote)``,
region RBAC's ``__scope_predicate`` is qualified as ``"Invoice"."tenant_id"``.
Passing that filter into the InvoiceNote repo yields:

  SELECT COUNT(*) FROM "InvoiceNote" WHERE ("Invoice"."tenant_id" = …)

Postgres raises UndefinedTable; the metric path swallows to 0. Same family
as #901 / #1231 / #1250 — strip the source predicate for cross-entity
aggregates; destination RLS still applies via session GUC.
"""

from __future__ import annotations

import pytest

from dazzle.http.runtime.workspace_aggregation import _scope_filters_for_aggregate


class TestScopeFiltersForAggregate:
    def test_strips_scope_predicate_when_entities_differ(self) -> None:
        scope = {
            "__scope_predicate": ('"Invoice"."tenant_id" = $1', ["t1"]),
            "status": "open",
        }
        out = _scope_filters_for_aggregate(
            scope,
            region_source="Invoice",
            aggregate_entity="InvoiceNote",
        )
        assert out is not None
        assert "__scope_predicate" not in out
        assert out.get("status") == "open"

    def test_keeps_scope_predicate_for_same_entity(self) -> None:
        scope = {
            "__scope_predicate": ('"Invoice"."tenant_id" = $1', ["t1"]),
        }
        out = _scope_filters_for_aggregate(
            scope,
            region_source="Invoice",
            aggregate_entity="Invoice",
        )
        assert out is not None
        assert out.get("__scope_predicate") == scope["__scope_predicate"]

    def test_none_and_empty_passthrough(self) -> None:
        assert (
            _scope_filters_for_aggregate(
                None, region_source="Invoice", aggregate_entity="InvoiceNote"
            )
            is None
        )
        assert (
            _scope_filters_for_aggregate(
                {}, region_source="Invoice", aggregate_entity="InvoiceNote"
            )
            == {}
        )

    def test_missing_names_keep_predicate(self) -> None:
        scope = {"__scope_predicate": ("x = $1", [1])}
        assert (
            _scope_filters_for_aggregate(scope, region_source=None, aggregate_entity="InvoiceNote")
            is scope
        )
        assert (
            _scope_filters_for_aggregate(scope, region_source="Invoice", aggregate_entity=None)
            is scope
        )

    @pytest.mark.parametrize(
        ("aggregate_entity", "expected"),
        [
            # #1773: same-entity aggregates count only the rows the region shows;
            # scope wins a key collision (the filter narrows, never replaces).
            ("StudentProfile", {"is_current": True, "below_target": True, "school_id": "s1"}),
            # Cross-entity: region-filter keys name source columns — skipped.
            ("Note", {"school_id": "s1"}),
        ],
    )
    def test_region_filter_composes_for_same_entity_only(
        self, aggregate_entity: str, expected: dict[str, object]
    ) -> None:
        out = _scope_filters_for_aggregate(
            {"school_id": "s1"},
            region_source="StudentProfile",
            aggregate_entity=aggregate_entity,
            region_filters={"is_current": True, "below_target": True, "school_id": "evil"},
        )
        assert out == expected
