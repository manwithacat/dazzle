"""Tests for modeling guidance in the inference KB."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


def _import_kg_module(name: str):
    """Import KG module directly to avoid MCP package init issues."""
    path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "knowledge_graph"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"dazzle.mcp.knowledge_graph.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"dazzle.mcp.knowledge_graph.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_store = _import_kg_module("store")
_seed = _import_kg_module("seed")


def _seeded_graph():
    """Create an in-memory KG seeded with framework knowledge."""
    graph = _store.KnowledgeGraph(":memory:")
    _seed.seed_framework_knowledge(graph)
    return graph


class TestModelingGuidanceInference:
    def test_polymorphic_query_returns_guidance(self) -> None:
        from dazzle.mcp.inference import lookup_inference

        graph = _seeded_graph()
        with patch("dazzle.mcp.inference._get_kg", return_value=graph):
            result = lookup_inference("polymorphic")
        suggestions = result.get("suggestions", [])
        guidance = [s for s in suggestions if s.get("type") == "modeling_guidance"]
        assert len(guidance) >= 1
        first = guidance[0]
        assert "avoid" in first
        assert "prefer" in first

    def test_soft_delete_query_returns_guidance(self) -> None:
        from dazzle.mcp.inference import lookup_inference

        graph = _seeded_graph()
        with patch("dazzle.mcp.inference._get_kg", return_value=graph):
            result = lookup_inference("soft delete")
        suggestions = result.get("suggestions", [])
        guidance = [s for s in suggestions if s.get("type") == "modeling_guidance"]
        assert len(guidance) >= 1

    def test_guidance_string_mentions_anti_patterns(self) -> None:
        from dazzle.mcp.inference import _GUIDANCE

        assert "polymorphic" in _GUIDANCE
        assert "god entities" in _GUIDANCE
        assert "soft-delete" in _GUIDANCE

    def test_list_all_includes_modeling_guidance_triggers(self) -> None:
        from dazzle.mcp.inference import list_all_patterns

        graph = _seeded_graph()
        with patch("dazzle.mcp.inference._get_kg", return_value=graph):
            result = list_all_patterns()
        assert "modeling_guidance_triggers" in result
        triggers = result["modeling_guidance_triggers"]
        assert "polymorphic" in triggers
        assert "soft delete" in triggers
