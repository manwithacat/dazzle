"""Regression tests for #901 — cross-entity per-card / per-stage
aggregate counts silently returning 0.

Both `display: action_grid` and `display: pipeline_steps` declare
per-card / per-stage `count_aggregate` expressions that can target
ANY entity, not just the region's `source:` entity. Pre-fix, the
runtime unconditionally passed `_scope_only_filters` (resolved
against the source entity) into the per-card/stage repo, causing
silent SQL failures and 0-values when the entities differed.

Fix: gate scope_filters on `entity_name == ctx.source`. When
entities differ, pass `None` and log a warning so operators can
audit. Destination entity's own RBAC still applies at navigation
time; the count badge becomes "all rows the runtime can read"
which is a known UX cost (cross-entity counts are unscoped).
"""

from __future__ import annotations

from pathlib import Path


class TestCrossEntityScopeGate:
    """Static-source guard pinning the #901 fix in both branches."""

    def _read_runtime(self) -> str:
        return (
            Path(__file__).resolve().parents[2] / "src/dazzle_back/runtime/workspace_rendering.py"
        ).read_text()

    def test_action_grid_per_card_gates_scope_on_entity_match(self) -> None:
        """The action_grid per-card branch must gate scope_filters on
        whether the per-card entity matches the region source — a
        bare `_scope_only_filters` pass-through regresses #901."""
        src = self._read_runtime()
        # The action_card_data branch must have the gate
        assert (
            "_card_scope = (\n                    _scope_only_filters if _entity_name == ctx.source else None\n                )"
            in src
            or ("_card_scope" in src and "_entity_name == ctx.source" in src)
        ), "action_grid per-card branch missing #901 entity-match gate"

    def test_pipeline_steps_per_stage_gates_scope_on_entity_match(self) -> None:
        """Same check for the pipeline_steps per-stage branch."""
        src = self._read_runtime()
        assert "_stage_scope" in src and "_entity_name == ctx.source" in src, (
            "pipeline_steps per-stage branch missing #901 entity-match gate"
        )

    def test_warning_logged_on_cross_entity_unscoped_query(self) -> None:
        """Both branches must log a warning when the entity differs
        from the source — this is the operator's audit signal that
        the count is unscoped."""
        src = self._read_runtime()
        # Two warning sites, one per branch
        assert src.count("cross-entity") >= 2, (
            "cross-entity warning missing in one of the two branches — operators "
            "won't notice that some counts are running unscoped"
        )

    def test_fix_documented_in_comments(self) -> None:
        """Both branches reference #901 in a comment so future edits
        understand WHY the gate is there. Removing the gate would
        regress the bug."""
        src = self._read_runtime()
        assert src.count("#901") >= 2, (
            "Both action_grid + pipeline_steps branches must cite #901 in a "
            "comment so future edits don't strip the gate accidentally"
        )


class TestSimulatedScopeGateBehaviour:
    """Pure-function simulation of the gate logic — verifies the
    decision rule without booting the runtime."""

    def _gate(self, entity_name: str, source: str, scope: object) -> object:
        """Mirror the runtime's `_card_scope = ...` / `_stage_scope = ...`
        expression."""
        return scope if entity_name == source else None

    def test_same_entity_passes_scope_through(self) -> None:
        scope = {"__scope_predicate": ("col = %s", ["x"])}
        assert self._gate("MarkingResult", "MarkingResult", scope) is scope

    def test_different_entity_drops_scope(self) -> None:
        scope = {"__scope_predicate": ("col = %s", ["x"])}
        assert self._gate("AssessmentEvent", "MarkingResult", scope) is None

    def test_no_scope_no_warn_no_op(self) -> None:
        """When scope is None (admin / no scope rules), the gate is
        a no-op — no warning, just None passes through."""
        assert self._gate("AssessmentEvent", "MarkingResult", None) is None
        assert self._gate("MarkingResult", "MarkingResult", None) is None
