"""#1750 — graph ops read the argument the schema advertises.

`graph related` read `entity_id` where the schema declares `name`, so the
lookup never happened; the empty id it then handed to `store.get_relations`
meant "no filter", so the caller received every relation in the graph as if it
were an answer. `graph inference` read `text` while the tool description and
the `knowledge` tool both say `query`.

These tests assert the published contract from the outside: call each handler
with the schema's argument names and require that a miss is distinguishable
from an answer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


def _build_graph() -> Any:
    """A small graph: one concept with 5 related_concept edges plus a decoy set."""
    from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

    graph = KnowledgeGraph(":memory:")
    graph.create_entity("concept:alpha", "alpha", entity_type="concept")
    for index in range(5):
        target = f"concept:beta{index}"
        graph.create_entity(target, f"beta{index}", entity_type="concept")
        graph.create_relation("concept:alpha", target, "related_concept")

    # Unrelated noise: if the handler stops filtering by source, this is what
    # leaks into the answer instead of an error.
    for index in range(50):
        source, target = f"concept:noise{index}", f"concept:junk{index}"
        graph.create_entity(source, f"noise{index}", entity_type="concept")
        graph.create_entity(target, f"junk{index}", entity_type="concept")
        graph.create_relation(source, target, "related_concept")

    graph.create_entity(
        "inference:validation.rule",
        "validation rule",
        entity_type="inference",
        metadata={"category": "dsl", "triggers": ["validation", "input validation"]},
    )
    return graph


@pytest.fixture
def graph() -> Any:
    return _build_graph()


def _related(graph: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    from dazzle.mcp.server.handlers_consolidated import _handle_graph_related

    return json.loads(_handle_graph_related(graph, arguments))


def _inference(graph: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    from dazzle.mcp.server.handlers_consolidated import _handle_graph_inference

    return json.loads(_handle_graph_inference(graph, arguments))


class TestRelated:
    def test_honours_limit_and_returns_distinct_neighbours(self, graph: Any) -> None:
        payload = _related(graph, {"name": "alpha", "limit": 3})

        assert len(payload["related"]) == 3
        ids = [entry["id"] for entry in payload["related"]]
        assert len(set(ids)) == 3, "one row per neighbour, not per relation"

    def test_count_reports_distinct_neighbours_not_rows_returned(self, graph: Any) -> None:
        payload = _related(graph, {"name": "alpha", "limit": 3})

        # Alpha has exactly 5 related_concept edges. Asking for 3 must not
        # report 320 — or 3 — as if rows and neighbours were the same thing.
        assert payload["count"] == 5
        assert payload["truncated"] is True
        assert payload["entity_id"] == "concept:alpha"

    def test_default_limit_is_twenty(self, graph: Any) -> None:
        payload = _related(graph, {"name": "alpha"})

        assert len(payload["related"]) == 5
        assert payload["truncated"] is False

    def test_unknown_name_errors_instead_of_returning_the_whole_graph(self, graph: Any) -> None:
        payload = _related(graph, {"name": "no_such_concept"})

        assert "error" in payload
        assert "related" not in payload

    def test_missing_name_errors_instead_of_returning_the_whole_graph(self, graph: Any) -> None:
        payload = _related(graph, {})

        assert "error" in payload
        assert "related" not in payload

    def test_a_hit_never_leaks_other_concepts(self, graph: Any) -> None:
        payload = _related(graph, {"name": "alpha", "limit": 50})

        assert all(entry["id"].startswith("concept:beta") for entry in payload["related"])


class TestInference:
    def test_reads_query(self, graph: Any) -> None:
        payload = _inference(graph, {"query": "validation"})

        assert payload["query"] == "validation"
        assert payload["count"] >= 1
        assert payload["matches"][0]["id"] == "inference:validation.rule"

    def test_honours_limit(self, graph: Any) -> None:
        payload = _inference(graph, {"query": "validation", "limit": 1})

        assert len(payload["matches"]) == 1

    def test_text_remains_an_accepted_alias(self, graph: Any) -> None:
        # The pre-#1750 docs example (docs/reference/graphs.md) sends `text`.
        payload = _inference(graph, {"text": "validation"})

        assert payload["query"] == "validation"
        assert payload["count"] >= 1

    def test_no_query_errors_instead_of_reporting_zero_matches(self, graph: Any) -> None:
        payload = _inference(graph, {})

        assert "error" in payload
        assert "matches" not in payload


class TestStoreEmptyIdIsNotAllRelations:
    def test_empty_entity_id_is_rejected(self, graph: Any) -> None:
        with pytest.raises(ValueError, match="non-empty entity id"):
            graph.get_relations(entity_id="")

    def test_none_still_means_every_relation(self, graph: Any) -> None:
        assert len(graph.get_relations(entity_id=None)) == 55

    def test_a_real_id_still_filters(self, graph: Any) -> None:
        relations = graph.get_relations(
            entity_id="concept:alpha", relation_type="related_concept", direction="outgoing"
        )

        assert len(relations) == 5


class TestDispatchReportsAMalformedIdInsteadOfTheGraph:
    """`neighbourhood` / `dependencies` / `dependents` read the right key, but an
    absent `entity_id` reached `get_relations` as `""` and returned every node in
    the graph. The store now refuses `""`, and the graph tool surfaces that as an
    error rather than a traceback."""

    def test_missing_entity_id_is_an_error_not_the_whole_graph(self, graph: Any) -> None:
        import json

        from dazzle.mcp.knowledge_graph.handlers import KnowledgeGraphHandlers
        from dazzle.mcp.server.handlers_consolidated import _dispatch_standalone_ops

        wrapped = KnowledgeGraphHandlers(graph)
        ops = {
            "neighbourhood": lambda args: json.dumps(
                wrapped.handle_get_neighbourhood(entity_id=args.get("entity_id", ""))
            )
        }

        payload = json.loads(
            _dispatch_standalone_ops(
                {"operation": "neighbourhood"}, ops, "graph", value_errors_as_errors=True
            )
        )

        assert "error" in payload
        assert "entities" not in payload


class TestPublishedSchema:
    def test_graph_schema_declares_every_key_the_handlers_read(self) -> None:
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = {t.name: t for t in get_consolidated_tools()}
        declared = set(tools["graph"].input_schema["properties"])

        # #1751 turns this into a gate over every handler; here it pins the
        # keys this fix depends on.
        assert {"name", "query", "text", "limit"} <= declared
