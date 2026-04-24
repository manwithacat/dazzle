"""Region filter resolution for the `current_context` sentinel (#857).

The workspace `context_selector` picks an entity id (e.g. a TeachingGroup)
and propagates it as the `context_id` query param. A region filter like
``filter: teaching_group = current_context`` previously fell through
`_extract_condition_filters` with the literal string `"current_context"`
as the filter value, producing a broken SQL query. The fix threads the
selected id through the extractor and resolves the sentinel to the value
(or skips the filter if nothing is selected).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any


def _cmp(field: str, value: Any) -> Any:
    """Build an AccessConditionSpec-style comparison condition."""
    return SimpleNamespace(
        kind="comparison",
        field=field,
        value=value,
        comparison_op=SimpleNamespace(value="="),
    )


def _ir_cmp(field: str, raw_value: Any) -> Any:
    """Build an IR ConditionExpr-style condition (no .kind, uses .comparison)."""
    return SimpleNamespace(
        comparison=SimpleNamespace(
            field=field,
            value=raw_value,
            operator=SimpleNamespace(value="="),
        ),
    )


class TestCurrentContextAccessConditionSpec:
    """AccessConditionSpec path: `current_context` resolves via context_id kwarg."""

    def test_resolves_current_context_to_selected_id(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = _cmp("teaching_group", "current_context")
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=None,
            context_id="tg-abc",
        )

        assert filters == {"teaching_group": "tg-abc"}

    def test_no_context_skips_filter(self) -> None:
        """Selector cleared ⇒ filter drops out so persona scope applies unfiltered."""
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = _cmp("teaching_group", "current_context")
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=None,
            context_id=None,
        )

        assert filters == {}

    def test_literal_string_unchanged(self) -> None:
        """Plain literal equals-another-string still works (no current_context regression)."""
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = _cmp("status", "active")
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            context_id="tg-abc",
        )

        assert filters == {"status": "active"}


class TestCurrentContextIRConditionExpr:
    """IR ConditionExpr path: same resolution."""

    def test_resolves_current_context_to_selected_id(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = _ir_cmp("teaching_group", "current_context")
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=None,
            context_id="tg-xyz",
        )

        assert filters == {"teaching_group": "tg-xyz"}

    def test_no_context_skips_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = _ir_cmp("teaching_group", "current_context")
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            context_id=None,
        )

        assert filters == {}

    def test_combined_with_current_user(self) -> None:
        """An AND of `current_user` + `current_context` resolves both sides."""
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        left = _ir_cmp("owner", "current_user")
        right = _ir_cmp("teaching_group", "current_context")
        cond = SimpleNamespace(
            operator=SimpleNamespace(value="and"),
            left=left,
            right=right,
            comparison=None,
        )
        filters: dict[str, Any] = {}

        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            context_id="tg-777",
        )

        assert filters.get("owner") == "user-123"
        assert filters.get("teaching_group") == "tg-777"


class TestBackwardsCompatibility:
    """Callers that don't pass context_id still work (kwarg is optional)."""

    def test_without_context_id_kwarg_is_safe(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        cond = _cmp("status", "active")
        filters: dict[str, Any] = {}

        # Mimics existing call sites that predate #857
        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            None,
        )

        assert filters == {"status": "active"}
