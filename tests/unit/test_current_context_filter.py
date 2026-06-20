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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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
        from dazzle.http.runtime.route_generator import _extract_condition_filters

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


class TestCurrentContextMultiHop1304:
    """#1304: multi-hop dotted `current_context` resolves via an FK-path
    subquery. Pre-fix: `ref_targets` wasn't threaded so the dotted key fell
    through unmapped (match-all), and `_build_fk_path_subquery` filtered on
    the bare field (`teaching_group`) instead of the FK column
    (`teaching_group_id`). The target column is resolved against the TARGET
    entity's FK map (model-dependent — not a blanket `_id` suffix, which would
    break bare-named FKs like `teacher.user`)."""

    # Global entity → FK-map: AssessmentEvent has an FK column teaching_group_id.
    _ALL_REF_TARGETS = {"AssessmentEvent": {"teaching_group_id": "TeachingGroup"}}

    def test_two_hop_dotted_current_context_builds_id_subquery(self) -> None:
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        # `assessment_event.teaching_group = current_context` on a Manuscript
        # region: assessment_event is an FK to AssessmentEvent; teaching_group
        # is an FK on AssessmentEvent (column teaching_group_id).
        cond = _ir_cmp("assessment_event.teaching_group", "current_context")
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-1",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets={"assessment_event_id": "AssessmentEvent"},
            context_id="tg-10A",
            all_ref_targets=self._ALL_REF_TARGETS,
        )

        # Resolves to a subquery keyed on the FK column (the `_id` form,
        # because teaching_group_id is an FK on the target entity).
        assert "assessment_event_id__in_subquery" in filters
        sql, params = filters["assessment_event_id__in_subquery"]
        assert '"teaching_group_id"' in sql
        assert '"AssessmentEvent"' in sql
        assert params == ["tg-10A"]

    def test_scalar_target_field_stays_bare(self) -> None:
        """A target field that is NOT an FK on the target entity (e.g. a
        scalar `user` column) must stay bare — a blanket `_id` suffix would
        break the working `teacher.user = current_user` case (#1232)."""
        from dazzle.http.runtime.route_generator import _build_fk_path_subquery

        result = _build_fk_path_subquery(
            "teacher.user",
            "user-uuid",
            {"teacher": "StaffMember"},
            {},  # StaffMember has no FK map entry → `user` is a scalar column
        )
        assert result is not None
        _fk, sql, _params = result
        assert '"user"' in sql
        assert "user_id" not in sql

    def test_explicit_id_suffix_not_double_suffixed(self) -> None:
        from dazzle.http.runtime.route_generator import _build_fk_path_subquery

        result = _build_fk_path_subquery(
            "assessment_event.teaching_group_id",
            "tg-10A",
            {"assessment_event_id": "AssessmentEvent"},
            self._ALL_REF_TARGETS,
        )
        assert result is not None
        _fk, sql, _params = result
        assert '"teaching_group_id"' in sql
        assert "teaching_group_id_id" not in sql  # no double-suffix

    def test_two_hop_without_ref_targets_does_not_build_subquery(self) -> None:
        """Without ref_targets the dotted path can't resolve — documents that
        the fetch path MUST thread ref_targets (the #1304 root gap)."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        cond = _ir_cmp("assessment_event.teaching_group", "current_context")
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-1",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets=None,
            context_id="tg-10A",
        )
        assert not any(k.endswith("__in_subquery") for k in filters)


def _and(left: Any, right: Any) -> Any:
    """Build an IR ConditionExpr AND node (no .kind, uses .operator)."""
    return SimpleNamespace(
        operator=SimpleNamespace(value="and"), left=left, right=right, comparison=None
    )


class TestContextOnlyExtraction1305:
    """#1305: ``context_only=True`` isolates the ``current_context`` slice of a
    compound region filter so the aggregate / GROUP BY paths re-scope by the
    context selector — *without* dragging the row-level literal predicates into
    the aggregate query (which would violate the #887 tenant-bounding contract).

    Pre-#1305: ``current_context`` reached the list fetch but the bar_chart /
    group_by / aggregate path used only ``scope_only_filters`` (the pure scope
    slice), so the chart returned the same buckets regardless of ``?context_id``.
    """

    _ALL_REF_TARGETS = {"AssessmentEvent": {"teaching_group_id": "TeachingGroup"}}

    def test_context_only_drops_literal_keeps_context(self) -> None:
        """`teaching_group = current_context and status = "marked"` under
        context_only must yield ONLY the context term — the literal `status`
        is the row-level filter #887 keeps out of aggregates."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        cond = _and(
            _ir_cmp("teaching_group", "current_context"),
            _ir_cmp("status", "marked"),
        )
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-1",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            context_id="tg-10A",
            context_only=True,
        )
        assert filters == {"teaching_group": "tg-10A"}

    def test_context_only_drops_current_user_keeps_context(self) -> None:
        """`owner = current_user and teaching_group = current_context` under
        context_only keeps only the context term (current_user is a scope-ish
        predicate already applied to the aggregate via scope_only_filters)."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        cond = _and(
            _ir_cmp("owner", "current_user"),
            _ir_cmp("teaching_group", "current_context"),
        )
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-123",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            context_id="tg-777",
            context_only=True,
        )
        assert filters == {"teaching_group": "tg-777"}

    def test_context_only_two_hop_builds_subquery_only(self) -> None:
        """The 2-hop dotted context term (the #1305 core) still resolves to an
        FK-path `__in_subquery` under context_only; the AND'd literal drops."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        cond = _and(
            _ir_cmp("assessment_event.teaching_group", "current_context"),
            _ir_cmp("status", "marked"),
        )
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-1",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            ref_targets={"assessment_event_id": "AssessmentEvent"},
            context_id="tg-10A",
            all_ref_targets=self._ALL_REF_TARGETS,
            context_only=True,
        )
        assert "status" not in filters
        assert "assessment_event_id__in_subquery" in filters
        sql, params = filters["assessment_event_id__in_subquery"]
        assert '"teaching_group_id"' in sql
        assert params == ["tg-10A"]

    def test_context_only_no_context_term_is_empty(self) -> None:
        """A filter with no current_context term yields no context filters —
        the aggregate then uses scope_only_filters unchanged."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        cond = _and(_ir_cmp("owner", "current_user"), _ir_cmp("status", "marked"))
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-1",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            context_id="tg-10A",
            context_only=True,
        )
        assert filters == {}

    def test_context_only_no_context_id_is_empty(self) -> None:
        """Selector cleared (context_id=None) ⇒ no context filter even with a
        current_context term, so the aggregate stays unbound on that axis."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters

        cond = _ir_cmp("teaching_group", "current_context")
        filters: dict[str, Any] = {}
        _extract_condition_filters(
            cond,
            "user-1",
            filters,
            logging.getLogger(__name__),
            auth_context=None,
            context_id=None,
            context_only=True,
        )
        assert filters == {}
