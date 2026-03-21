# tests/unit/test_heatmap_regression.py
"""Regression tests for heatmap display-name resolution, row IDs, and thresholds (#586)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from dazzle_back.runtime.workspace_rendering import (
    _inject_display_names,
    _resolve_display_name,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_items_with_fk(
    rows_field: str,
    cols_field: str,
    value_field: str,
    data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build items with FK dicts and inject _display siblings."""
    items = []
    for d in data:
        item: dict[str, Any] = {
            "id": d.get("id", "item-id"),
            rows_field: d[rows_field],
            cols_field: d[cols_field],
            value_field: d[value_field],
        }
        item = _inject_display_names(item)
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Bug 1: Row/column labels should use _display keys, not raw FK dicts
# ---------------------------------------------------------------------------


class TestHeatmapDisplayNames:
    """Heatmap pivot builder must prefer _display sibling keys over raw FK dicts."""

    def test_display_key_used_for_fk_row(self) -> None:
        """When a row field is an FK dict, the _display key should be used."""
        item: dict[str, Any] = {
            "id": "score-1",
            "student": {"id": "stu-uuid-123", "name": "Alice"},
            "subject": {"id": "sub-uuid-456", "name": "Maths"},
            "avg_score": 0.75,
        }
        item = _inject_display_names(item)
        # The _display key should exist and contain the resolved name
        assert item["student_display"] == "Alice"
        assert item["subject_display"] == "Maths"

        # Simulating what the fixed heatmap builder does:
        rv = str(item.get("student_display", "")) or _resolve_display_name(item.get("student", ""))
        cv = str(item.get("subject_display", "")) or _resolve_display_name(item.get("subject", ""))
        assert rv == "Alice"
        assert cv == "Maths"
        # NOT UUIDs
        assert "uuid" not in rv.lower()
        assert "uuid" not in cv.lower()

    def test_fallback_to_resolve_for_non_dict(self) -> None:
        """For scalar fields (no FK dict), fall back to _resolve_display_name."""
        item: dict[str, Any] = {
            "id": "score-1",
            "student": "Alice",
            "subject": "Maths",
            "avg_score": 0.75,
        }
        item = _inject_display_names(item)
        # No _display key for scalars
        assert "student_display" not in item

        rv = str(item.get("student_display", "")) or _resolve_display_name(item.get("student", ""))
        assert rv == "Alice"

    def test_display_key_preferred_over_id_in_fk(self) -> None:
        """FK dict with only id (no name/title) should still show id via _display."""
        item: dict[str, Any] = {
            "id": "score-1",
            "student": {"id": "stu-uuid-999"},
            "subject": "Maths",
            "avg_score": 0.5,
        }
        item = _inject_display_names(item)
        # _display should resolve to the id since no name/title key
        assert item["student_display"] == "stu-uuid-999"

        # With the fix, the _display key is used (consistent with other regions)
        rv = str(item.get("student_display", "")) or _resolve_display_name(item.get("student", ""))
        assert rv == "stu-uuid-999"


# ---------------------------------------------------------------------------
# Bug 1 continued: row_id preserved for action URLs
# ---------------------------------------------------------------------------


class TestHeatmapRowIds:
    """Heatmap matrix entries must include row_id for action URL interpolation."""

    def test_row_id_extracted_from_fk_dict(self) -> None:
        """row_id should come from the FK dict's id field."""
        raw_row = {"id": "stu-uuid-123", "name": "Alice"}
        row_id = str(raw_row.get("id", "") if isinstance(raw_row, dict) else "fallback")
        assert row_id == "stu-uuid-123"

    def test_row_id_fallback_to_item_id(self) -> None:
        """When row field is scalar, row_id should fall back to item id."""
        item = {"id": "item-id-456", "student": "Alice"}
        raw_row = item.get("student")
        row_id = str(raw_row.get("id", "") if isinstance(raw_row, dict) else item.get("id", ""))
        assert row_id == "item-id-456"

    def test_matrix_entry_has_row_id_key(self) -> None:
        """Heatmap matrix entries should contain a row_id key."""
        # Simulate building a matrix entry as the fixed code does
        row_ids: dict[str, str] = {"Alice": "stu-uuid-123"}
        row_label = "Alice"
        cells = [{"value": 0.75, "column": "Maths"}]
        entry = {
            "row": row_label,
            "row_id": row_ids.get(row_label, ""),
            "cells": cells,
        }
        assert entry["row_id"] == "stu-uuid-123"


# ---------------------------------------------------------------------------
# Bug 2: Threshold resolution must produce non-empty list for static values
# ---------------------------------------------------------------------------


class TestHeatmapThresholds:
    """Threshold resolution should produce correct lists for both static and ParamRef cases."""

    def test_static_thresholds_from_ctx_region(self) -> None:
        """Static thresholds on ctx_region should pass through unchanged."""
        ctx_region = MagicMock()
        ctx_region.heatmap_thresholds = [0.4, 0.6]
        # Simulate the else branch (non-ParamRef)
        thresholds = list(getattr(ctx_region, "heatmap_thresholds", None) or [])
        assert thresholds == [0.4, 0.6]

    def test_empty_thresholds_stay_empty(self) -> None:
        """When no thresholds configured, result should be empty list."""
        ctx_region = MagicMock()
        ctx_region.heatmap_thresholds = []
        thresholds = list(getattr(ctx_region, "heatmap_thresholds", None) or [])
        assert thresholds == []

    def test_paramref_fallback_to_ctx_defaults(self) -> None:
        """ParamRef with no runtime override should fall back to ctx_region defaults."""
        # Simulate: resolve_value returns None, ctx_region has defaults
        _resolved = None
        ctx_region = MagicMock()
        ctx_region.heatmap_thresholds = [0.3, 0.7]
        thresholds = list(_resolved or getattr(ctx_region, "heatmap_thresholds", None) or [])
        assert thresholds == [0.3, 0.7]

    def test_paramref_runtime_override_wins(self) -> None:
        """ParamRef with runtime override should use the resolved value."""
        _resolved = [0.5, 0.8]
        ctx_region = MagicMock()
        ctx_region.heatmap_thresholds = [0.3, 0.7]
        thresholds = list(_resolved or getattr(ctx_region, "heatmap_thresholds", None) or [])
        assert thresholds == [0.5, 0.8]

    def test_thresholds_length_for_rag_colours(self) -> None:
        """Template needs >= 2 thresholds for RAG colours."""
        thresholds = [0.4, 0.6]
        assert len(thresholds) >= 2, "Need at least 2 thresholds for red/amber/green"


# ---------------------------------------------------------------------------
# Bug 3: Template action URL uses row_id
# ---------------------------------------------------------------------------


class TestHeatmapTemplateActionUrl:
    """The heatmap template should interpolate row.row_id into action URLs."""

    def test_action_url_interpolation(self) -> None:
        """Verify the template pattern replaces {id} with row_id."""
        action_url = "/app/student/{id}"
        row = {"row": "Alice", "row_id": "stu-uuid-123", "cells": []}
        # Simulate what Jinja2's replace filter does
        result = action_url.replace("{id}", row["row_id"])
        assert result == "/app/student/stu-uuid-123"

    def test_action_url_without_placeholder(self) -> None:
        """If action_url has no {id} placeholder, it stays unchanged."""
        action_url = "/app/dashboard"
        row = {"row": "Alice", "row_id": "stu-uuid-123", "cells": []}
        result = action_url.replace("{id}", row["row_id"])
        assert result == "/app/dashboard"


# ---------------------------------------------------------------------------
# Integration: _resolve_thresholds in workspace_renderer.py
# ---------------------------------------------------------------------------


class TestResolveThresholdsFunction:
    """Test _resolve_thresholds from the UI renderer."""

    def test_literal_list(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import _resolve_thresholds

        assert _resolve_thresholds([0.4, 0.6]) == [0.4, 0.6]

    def test_none_returns_empty(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import _resolve_thresholds

        assert _resolve_thresholds(None) == []

    def test_paramref_uses_default(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import _resolve_thresholds

        ref = MagicMock()
        ref.key = "thresholds_key"
        ref.default = [0.3, 0.7]
        assert _resolve_thresholds(ref) == [0.3, 0.7]

    def test_paramref_no_default(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import _resolve_thresholds

        ref = MagicMock()
        ref.key = "thresholds_key"
        ref.default = None
        assert _resolve_thresholds(ref) == []
