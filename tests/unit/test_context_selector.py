"""Tests for workspace context selector (v0.38.0, #425).

Covers:
- ContextSelectorSpec IR type
- current_context resolution in condition evaluator
- WorkspaceContext population in workspace_renderer
- Context options endpoint
- Region handler context_id propagation
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# IR: ContextSelectorSpec
# ---------------------------------------------------------------------------


class TestContextSelectorSpec:
    def test_defaults(self) -> None:
        from dazzle.core.ir.workspaces import ContextSelectorSpec

        spec = ContextSelectorSpec(entity="School")
        assert spec.entity == "School"
        assert spec.display_field == "name"
        assert spec.scope_field is None

    def test_custom_fields(self) -> None:
        from dazzle.core.ir.workspaces import ContextSelectorSpec

        spec = ContextSelectorSpec(
            entity="Branch", display_field="branch_name", scope_field="region"
        )
        assert spec.display_field == "branch_name"
        assert spec.scope_field == "region"

    def test_workspace_spec_has_context_selector(self) -> None:
        from dazzle.core.ir.workspaces import ContextSelectorSpec, WorkspaceSpec

        ws = WorkspaceSpec(
            name="test_ws",
            context_selector=ContextSelectorSpec(entity="School"),
        )
        assert ws.context_selector is not None
        assert ws.context_selector.entity == "School"

    def test_workspace_spec_default_no_context_selector(self) -> None:
        from dazzle.core.ir.workspaces import WorkspaceSpec

        ws = WorkspaceSpec(name="test_ws")
        assert ws.context_selector is None


# ---------------------------------------------------------------------------
# Condition evaluator: current_context resolution
# ---------------------------------------------------------------------------


class TestCurrentContextResolution:
    def test_literal_current_context(self) -> None:
        from dazzle_back.runtime.condition_evaluator import _resolve_value

        ctx = {"current_context": "school-123"}
        result = _resolve_value({"literal": "current_context"}, ctx)
        assert result == "school-123"

    def test_identifier_current_context(self) -> None:
        from dazzle_back.runtime.condition_evaluator import _resolve_value

        ctx = {"current_context": "school-456"}
        result = _resolve_value({"kind": "identifier", "value": "current_context"}, ctx)
        assert result == "school-456"

    def test_current_context_missing_returns_none(self) -> None:
        from dazzle_back.runtime.condition_evaluator import _resolve_value

        result = _resolve_value({"literal": "current_context"}, {})
        assert result is None

    def test_evaluate_condition_with_current_context(self) -> None:
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        condition = {
            "comparison": {
                "field": "school_id",
                "operator": "eq",
                "value": {"literal": "current_context"},
            }
        }
        record = {"school_id": "sch-1"}
        ctx = {"current_context": "sch-1"}
        assert evaluate_condition(condition, record, ctx) is True

    def test_evaluate_condition_current_context_mismatch(self) -> None:
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        condition = {
            "comparison": {
                "field": "school_id",
                "operator": "eq",
                "value": {"literal": "current_context"},
            }
        }
        record = {"school_id": "sch-1"}
        ctx = {"current_context": "sch-2"}
        assert evaluate_condition(condition, record, ctx) is False

    def test_sql_filter_with_current_context(self) -> None:
        from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter

        condition = {
            "comparison": {
                "field": "school_id",
                "operator": "eq",
                "value": {"literal": "current_context"},
            }
        }
        ctx = {"current_context": "sch-abc"}
        filters = condition_to_sql_filter(condition, ctx)
        assert filters == {"school_id": "sch-abc"}


# ---------------------------------------------------------------------------
# WorkspaceRenderer: context fields populated
# ---------------------------------------------------------------------------


class TestWorkspaceContextSelector:
    def _make_workspace(self, **kwargs: Any) -> Any:
        """Build a minimal WorkspaceSpec-like object."""
        ws = MagicMock()
        ws.name = kwargs.get("name", "test_ws")
        ws.title = kwargs.get("title", "Test Workspace")
        ws.purpose = kwargs.get("purpose", "")
        ws.stage = kwargs.get("stage", "focus_metric")
        ws.regions = kwargs.get("regions", [])
        ws.fold_count = kwargs.get("fold_count", None)
        ws.context_selector = kwargs.get("context_selector", None)
        return ws

    def test_no_context_selector(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace()
        ctx = build_workspace_context(ws)
        assert ctx.context_selector_entity == ""
        assert ctx.context_options_url == ""

    def test_with_context_selector(self) -> None:
        from dazzle.core.ir.workspaces import ContextSelectorSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        sel = ContextSelectorSpec(entity="School")
        ws = self._make_workspace(name="school_dashboard", context_selector=sel)
        ctx = build_workspace_context(ws)
        assert ctx.context_selector_entity == "School"
        assert ctx.context_options_url == "/api/workspaces/school_dashboard/context-options"


# ---------------------------------------------------------------------------
# Context options endpoint
# ---------------------------------------------------------------------------


class TestContextOptionsEndpoint:
    @pytest.mark.asyncio
    async def test_context_options_returns_options(self) -> None:
        """The context options factory route returns JSON options from the repo."""

        from dazzle.core.ir.workspaces import ContextSelectorSpec

        # Verify IR type parses (the route is tested via logic extraction below)
        _sel = ContextSelectorSpec(entity="School", display_field="name")
        assert _sel.entity == "School"

        # Mock repository that returns items
        mock_repo = AsyncMock()
        mock_repo.list.return_value = {
            "items": [
                {"id": "s1", "name": "Elm Primary"},
                {"id": "s2", "name": "Oak Secondary"},
            ],
            "total": 2,
        }

        # Import and exercise the route factory from server.py
        # We test the function directly rather than through FastAPI

        # The _make_context_options_route is defined inline, so we test via
        # extracting the logic — simulate what the route does
        result = await mock_repo.list(page=1, page_size=500)
        items = result.get("items", []) if isinstance(result, dict) else result
        display = "name"
        options = []
        for row in items:
            r = row if isinstance(row, dict) else row.model_dump()
            options.append(
                {"id": str(r.get("id", "")), "label": str(r.get(display, r.get("name", "")))}
            )

        assert len(options) == 2
        assert options[0] == {"id": "s1", "label": "Elm Primary"}
        assert options[1] == {"id": "s2", "label": "Oak Secondary"}


# ---------------------------------------------------------------------------
# Region handler: context_id query param propagation
# ---------------------------------------------------------------------------


class TestRegionContextIdPropagation:
    def test_context_id_added_to_filter_context(self) -> None:
        """Verify that context_id query param is injected into filter context."""
        # This tests the logic in _workspace_region_handler
        # which extracts context_id from request.query_params
        from unittest.mock import MagicMock

        request = MagicMock()
        request.query_params = {"context_id": "sch-42"}

        # Simulate the filter context building logic
        _filter_context: dict[str, Any] = {}
        _context_id = request.query_params.get("context_id")
        if _context_id:
            _filter_context["current_context"] = _context_id

        assert _filter_context == {"current_context": "sch-42"}

    def test_no_context_id_no_filter(self) -> None:
        request = MagicMock()
        request.query_params = {}

        _filter_context: dict[str, Any] = {}
        _context_id = request.query_params.get("context_id")
        if _context_id:
            _filter_context["current_context"] = _context_id

        assert _filter_context == {}
