"""#1750 — an empty entity id is not "every relation".

An empty id handed to `store.get_relations` used to mean "no filter", so a
caller with a malformed argument received every relation in the knowledge
graph as if it were an answer. The store now refuses `""`; `None` still means
"no filter". (The MCP `graph` tool that first exposed this was removed in
flense ship I; the store rule stays because `knowledge` lookups read it.)
"""

from __future__ import annotations

from typing import Any

import pytest


def _build_graph() -> Any:
    """One concept with 5 related_concept edges plus 50 unrelated edges."""
    from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

    graph = KnowledgeGraph(":memory:")
    graph.create_entity("concept:alpha", "alpha", entity_type="concept")
    for index in range(5):
        target = f"concept:beta{index}"
        graph.create_entity(target, f"beta{index}", entity_type="concept")
        graph.create_relation("concept:alpha", target, "related_concept")

    for index in range(50):
        source, target = f"concept:noise{index}", f"concept:junk{index}"
        graph.create_entity(source, f"noise{index}", entity_type="concept")
        graph.create_entity(target, f"junk{index}", entity_type="concept")
        graph.create_relation(source, target, "related_concept")
    return graph


@pytest.fixture
def graph() -> Any:
    return _build_graph()


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
