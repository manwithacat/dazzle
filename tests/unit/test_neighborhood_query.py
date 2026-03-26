"""Tests for NeighborhoodQueryBuilder — recursive CTE SQL generation (#619)."""

import pytest

from dazzle.core.ir import GraphEdgeSpec
from dazzle_back.runtime.neighborhood import NeighborhoodQueryBuilder


@pytest.fixture
def directed_edge() -> GraphEdgeSpec:
    return GraphEdgeSpec(source="from_id", target="to_id")


@pytest.fixture
def undirected_edge() -> GraphEdgeSpec:
    return GraphEdgeSpec(source="from_id", target="to_id", directed=False)


@pytest.fixture
def builder(directed_edge: GraphEdgeSpec) -> NeighborhoodQueryBuilder:
    return NeighborhoodQueryBuilder(
        node_table="nodes",
        edge_table="edges",
        graph_edge=directed_edge,
    )


@pytest.fixture
def undirected_builder(undirected_edge: GraphEdgeSpec) -> NeighborhoodQueryBuilder:
    return NeighborhoodQueryBuilder(
        node_table="nodes",
        edge_table="edges",
        graph_edge=undirected_edge,
    )


class TestDirectedCTE:
    def test_cte_basic_directed(self, builder: NeighborhoodQueryBuilder) -> None:
        sql, params = builder.cte_query("abc-123", depth=3)
        assert "WITH RECURSIVE" in sql
        assert "from_id" in sql
        assert "to_id" in sql
        assert "max_depth" in sql
        assert params["seed_id"] == "abc-123"

    def test_cte_depth_param(self, builder: NeighborhoodQueryBuilder) -> None:
        _sql, params = builder.cte_query("x", depth=5)
        assert params["max_depth"] == 5

    def test_cte_returns_distinct(self, builder: NeighborhoodQueryBuilder) -> None:
        sql, _params = builder.cte_query("x", depth=2)
        assert "DISTINCT" in sql

    def test_cte_uses_union_not_union_all(self, builder: NeighborhoodQueryBuilder) -> None:
        sql, _params = builder.cte_query("x", depth=2)
        assert " UNION " in sql
        assert "UNION ALL" not in sql


class TestUndirectedCTE:
    def test_cte_undirected_bidirectional(
        self, undirected_builder: NeighborhoodQueryBuilder
    ) -> None:
        sql, _params = undirected_builder.cte_query("x", depth=2)
        assert "CASE" in sql or " OR " in sql


class TestNodeFetchQuery:
    def test_node_fetch_uses_in_clause(self, builder: NeighborhoodQueryBuilder) -> None:
        sql, params = builder.node_fetch_query(["a", "b"])
        assert "IN" in sql
        assert params["node_ids"] == ("a", "b")

    def test_edge_fetch_constrains_both_endpoints(self, builder: NeighborhoodQueryBuilder) -> None:
        sql, params = builder.edge_fetch_query(["a", "b"])
        assert "from_id" in sql
        assert "to_id" in sql
        assert sql.count("IN") == 2
        assert params["node_ids"] == ("a", "b")


class TestScopeInjection:
    def test_edge_scope_injected_into_cte(self, directed_edge: GraphEdgeSpec) -> None:
        qb = NeighborhoodQueryBuilder(
            node_table="nodes",
            edge_table="edges",
            graph_edge=directed_edge,
            edge_scope_sql="tenant_id = %(tenant_id)s",
        )
        sql, _params = qb.cte_query("x", depth=2)
        assert "tenant_id = %(tenant_id)s" in sql

    def test_node_scope_injected_into_node_fetch(self, directed_edge: GraphEdgeSpec) -> None:
        qb = NeighborhoodQueryBuilder(
            node_table="nodes",
            edge_table="edges",
            graph_edge=directed_edge,
            node_scope_sql="active = true",
        )
        sql, _params = qb.node_fetch_query(["a"])
        assert "active = true" in sql

    def test_no_scope_when_none(self, builder: NeighborhoodQueryBuilder) -> None:
        sql, _params = builder.cte_query("x", depth=2)
        assert "tenant_id" not in sql
        sql2, _params2 = builder.node_fetch_query(["a"])
        assert "active" not in sql2
