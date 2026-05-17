"""#1134: ``KnowledgeGraph.create_alias`` self-defends against missing
canonical entities so the semantic-KB seed doesn't abort with a
``sqlite3.IntegrityError: FOREIGN KEY constraint failed`` on every
CLI invocation.

The seed loop deliberately falls through to "point at concept anyway"
when a canonical name resolves neither to a concept nor a pattern
(see ``_seed_semantic_kb`` in ``mcp/knowledge_graph/seed.py``).
Pre-fix, that orphan reference fired an FK violation, the whole
``_seed_semantic_kb`` call rolled back, and the catch in
``seed_framework_knowledge`` logged an ERROR-level traceback —
dominating ERROR-filtered log views.

Post-fix:
- ``create_alias`` returns ``False`` and DEBUG-logs the skip when
  the canonical entity row is missing.
- ``seed_framework_knowledge`` lowers its catch-all log to WARNING
  (still has the traceback via ``exc_info=True``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _import_kg_module(module_name: str):
    """Direct import — mirrors the pattern in test_kg_seed.py to avoid
    MCP package init issues."""
    module_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "knowledge_graph"
        / f"{module_name}.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"dazzle.mcp.knowledge_graph.{module_name}",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"dazzle.mcp.knowledge_graph.{module_name}"] = module
    spec.loader.exec_module(module)
    return module


_store_module = _import_kg_module("store")
_seed_module = _import_kg_module("seed")
KnowledgeGraph = _store_module.KnowledgeGraph


def test_create_alias_returns_true_for_existing_canonical() -> None:
    """Happy path — create_alias inserts and returns True."""
    graph = KnowledgeGraph(":memory:")
    graph.create_entity(
        entity_id="concept:state_machine",
        name="state_machine",
        entity_type="concept",
        metadata={"source": "test"},
    )
    inserted = graph.create_alias("transitions", "concept:state_machine")
    assert inserted is True
    assert graph.resolve_alias("transitions") == "concept:state_machine"


def test_create_alias_returns_false_and_skips_for_missing_canonical() -> None:
    """#1134: create_alias must NOT raise sqlite3.IntegrityError when
    the canonical entity is missing — it must skip and return False
    so the caller can continue the batch."""
    graph = KnowledgeGraph(":memory:")
    # No matching entity created.
    inserted = graph.create_alias("orphan_alias", "concept:does_not_exist")
    assert inserted is False
    # Verify nothing landed in the aliases table.
    assert graph.resolve_alias("orphan_alias") is None


def test_seed_framework_knowledge_does_not_log_error_on_orphan_aliases(caplog) -> None:
    """End-to-end: even if one alias in ALIASES points at a name that
    doesn't resolve to any concept/pattern entity, the seed completes
    cleanly without an ERROR-level "KG seeding failed" line."""
    import logging

    graph = KnowledgeGraph(":memory:")
    with caplog.at_level(logging.ERROR, logger="dazzle.mcp.knowledge_graph.seed"):
        _seed_module.seed_framework_knowledge(graph)

    # No ERROR-level line from the seed module.
    errors = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "KG seeding failed" in r.getMessage()
    ]
    assert errors == [], f"Unexpected ERROR-level seed failures: {[e.getMessage() for e in errors]}"


def test_seed_failure_logs_warning_not_error(caplog) -> None:
    """If ``_seed_semantic_kb`` itself blows up for an unrelated reason,
    the outer catch-all logs at WARNING (still has traceback via
    ``exc_info=True``), not ERROR — log polish per issue ask #2."""
    import logging
    from unittest.mock import patch

    graph = KnowledgeGraph(":memory:")
    with patch.object(_seed_module, "_seed_semantic_kb", side_effect=RuntimeError("boom")):
        with caplog.at_level(logging.WARNING, logger="dazzle.mcp.knowledge_graph.seed"):
            _seed_module.seed_framework_knowledge(graph)

    matching = [r for r in caplog.records if "KG seeding failed" in r.getMessage()]
    assert matching, "Expected a WARNING-level seed-failed log line"
    assert all(r.levelno == logging.WARNING for r in matching), (
        "Seed-failure log must be WARNING, not ERROR (#1134 ask #2)"
    )
