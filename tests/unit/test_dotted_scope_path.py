"""Tests for left-side dotted path resolution in scope rules (#556)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _skip_if_no_fastapi() -> None:
    pytest.importorskip("fastapi")


class TestBuildFkPathSubquery:
    """_build_fk_path_subquery generates correct SQL subquery for FK traversal."""

    def test_simple_dotted_path(self) -> None:
        from dazzle_back.runtime.route_generator import _build_fk_path_subquery

        ref_targets = {"manuscript_id": "Manuscript"}
        result = _build_fk_path_subquery("manuscript.student_id", "user-123", ref_targets)
        assert result is not None
        fk_field, sql, params = result
        assert fk_field == "manuscript_id"
        assert '"Manuscript"' in sql
        assert '"student_id"' in sql
        assert "SELECT" in sql
        assert params == ["user-123"]

    def test_relation_name_without_id_suffix(self) -> None:
        """Field named 'manuscript' (no _id) should try manuscript_id first."""
        from dazzle_back.runtime.route_generator import _build_fk_path_subquery

        ref_targets = {"manuscript_id": "Manuscript"}
        result = _build_fk_path_subquery("manuscript.student", "user-123", ref_targets)
        assert result is not None
        fk_field, _, _ = result
        assert fk_field == "manuscript_id"

    def test_no_ref_targets_returns_none(self) -> None:
        from dazzle_back.runtime.route_generator import _build_fk_path_subquery

        result = _build_fk_path_subquery("manuscript.student", "user-123", {})
        assert result is None

    def test_unknown_relation_returns_none(self) -> None:
        from dazzle_back.runtime.route_generator import _build_fk_path_subquery

        ref_targets = {"order_id": "Order"}
        result = _build_fk_path_subquery("manuscript.student", "user-123", ref_targets)
        assert result is None

    def test_non_dotted_path_returns_none(self) -> None:
        from dazzle_back.runtime.route_generator import _build_fk_path_subquery

        ref_targets = {"manuscript_id": "Manuscript"}
        result = _build_fk_path_subquery("student_id", "user-123", ref_targets)
        assert result is None


class TestExtractConditionFiltersWithDottedPath:
    """_extract_condition_filters resolves left-side dotted paths to subqueries."""

    def _make_comparison_condition(self, field: str, value: str) -> Any:
        """Build an AccessConditionSpec-style comparison condition."""
        return SimpleNamespace(
            kind="comparison",
            field=field,
            value=value,
            comparison_op=SimpleNamespace(value="="),
        )

    def test_dotted_path_generates_subquery(self) -> None:
        import logging

        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = self._make_comparison_condition("manuscript.student_id", "current_user")
        ref_targets = {"manuscript_id": "Manuscript"}
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=ref_targets,
        )

        # Should produce a subquery filter, not a direct field filter
        assert "manuscript_id__in_subquery" in filters
        sql, params = filters["manuscript_id__in_subquery"]
        assert "SELECT" in sql
        assert '"Manuscript"' in sql
        assert '"student_id"' in sql

    def test_non_dotted_path_direct_filter(self) -> None:
        """Non-dotted fields still work as direct column filters."""
        import logging

        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = self._make_comparison_condition("student_id", "current_user")
        ref_targets = {"manuscript_id": "Manuscript"}
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=ref_targets,
        )

        assert "student_id" in filters
        assert filters["student_id"] == "user-123"

    def test_dotted_path_without_ref_targets_uses_literal(self) -> None:
        """Without ref_targets, dotted path falls through to literal column name."""
        import logging

        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = self._make_comparison_condition("manuscript.student_id", "current_user")
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=None,
        )

        # Without ref_targets, falls back to literal field name
        assert "manuscript.student_id" in filters
