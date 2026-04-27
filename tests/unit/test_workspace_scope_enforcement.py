"""Tests for workspace region scope predicate enforcement (#574).

Verifies that workspace region queries apply entity-level scope predicates
from scope: DSL blocks, matching the enforcement in API route paths.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_region_ctx(
    *,
    source: str = "Task",
    cedar_access_spec: Any = None,
    fk_graph: Any = None,
) -> Any:
    """Create a minimal WorkspaceRegionContext-like object for scope tests."""
    from dazzle_back.runtime.workspace_rendering import WorkspaceRegionContext

    ctx_region = SimpleNamespace(
        name="tasks",
        display="TABLE",
        limit=20,
        date_field="",
        date_range=False,
        aggregates=[],
        template="workspace/regions/table.html",
        endpoint="/api/workspaces/main/regions/tasks",
        source_tabs=[],
    )
    ir_region = SimpleNamespace(filter=None, sort=None)

    return WorkspaceRegionContext(
        ctx_region=ctx_region,
        ir_region=ir_region,
        source=source,
        entity_spec=SimpleNamespace(name=source, fields=[], state_machine=None),
        attention_signals=[],
        ws_access=None,
        repositories={},
        require_auth=False,
        auth_middleware=None,
        cedar_access_spec=cedar_access_spec,
        fk_graph=fk_graph,
    )


def _make_auth_context(roles: list[str], user_id: str = "user-1") -> Any:
    """Create a minimal auth context with roles."""
    user = SimpleNamespace(roles=roles, is_superuser=False, id=user_id)
    return SimpleNamespace(
        user=user,
        roles=[f"role_{r}" for r in roles],
        is_authenticated=True,
        preferences={},
    )


def _make_access_spec_with_scopes(scopes: list[Any]) -> Any:
    """Create a cedar access spec with scope rules."""
    return SimpleNamespace(scopes=scopes, permissions=[])


def _make_scope_rule(
    operation: str,
    personas: list[str],
    *,
    condition: Any = None,
    predicate: Any = None,
) -> Any:
    """Create a scope rule."""
    return SimpleNamespace(
        operation=SimpleNamespace(value=operation),
        personas=personas,
        condition=condition,
        predicate=predicate,
    )


# ===========================================================================
# _apply_workspace_scope_filters
# ===========================================================================


class TestApplyWorkspaceScopeFilters:
    """Tests for _apply_workspace_scope_filters helper."""

    def test_no_access_spec_returns_filters_unchanged(self) -> None:
        """No cedar_access_spec means no filtering — backward compat."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        ctx = _make_region_ctx(cedar_access_spec=None)
        auth = _make_auth_context(["admin"])
        original_filters = {"status": "open"}

        result_filters, denied = _apply_workspace_scope_filters(
            ctx, auth, "user-1", original_filters
        )

        assert denied is False
        assert result_filters == {"status": "open"}

    def test_no_scopes_passes_through(self) -> None:
        """Access spec with permits but no scopes passes through (no row filter) (#607)."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        access = SimpleNamespace(scopes=[], permissions=[])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["admin"])

        result_filters, denied = _apply_workspace_scope_filters(ctx, auth, "user-1", None)

        assert denied is False

    def test_no_user_id_skips_enforcement(self) -> None:
        """Without a user ID, scope enforcement is skipped."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        scope = _make_scope_rule("list", ["admin"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["admin"])

        result_filters, denied = _apply_workspace_scope_filters(ctx, auth, None, None)

        assert denied is False
        assert result_filters is None

    def test_no_auth_context_skips_enforcement(self) -> None:
        """Without auth context, scope enforcement is skipped."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        scope = _make_scope_rule("list", ["admin"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)

        result_filters, denied = _apply_workspace_scope_filters(ctx, None, "user-1", None)

        assert denied is False
        assert result_filters is None

    def test_scope_match_all_returns_no_extra_filters(self) -> None:
        """Scope rule with no condition/predicate = 'all' — no extra filters."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        scope = _make_scope_rule("list", ["admin"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["admin"])

        result_filters, denied = _apply_workspace_scope_filters(
            ctx, auth, "user-1", {"status": "open"}
        )

        assert denied is False
        assert result_filters == {"status": "open"}

    def test_scope_no_role_match_returns_denied(self) -> None:
        """No scope rule matches user roles — default-deny."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        scope = _make_scope_rule("list", ["admin"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["viewer"])  # not admin

        result_filters, denied = _apply_workspace_scope_filters(ctx, auth, "user-1", None)

        assert denied is True

    def test_scope_predicate_merged_into_filters(self) -> None:
        """Scope rule with predicate merges __scope_predicate into filters."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        # Create a scope rule with a predicate that will trigger _resolve_scope_filters
        # to return a dict with __scope_predicate
        scope = _make_scope_rule(
            "list",
            ["teacher"],
            predicate=SimpleNamespace(kind="direct"),
        )
        access = _make_access_spec_with_scopes([scope])
        fk_graph = SimpleNamespace()  # minimal fk_graph
        ctx = _make_region_ctx(cedar_access_spec=access, fk_graph=fk_graph)
        auth = _make_auth_context(["teacher"])

        # Mock _resolve_scope_filters to return a predicate result
        scope_filters = {"__scope_predicate": ("school_id = $1", ["school-1"])}
        with patch(
            "dazzle_back.runtime.route_generator._resolve_scope_filters",
            return_value=scope_filters,
        ):
            result_filters, denied = _apply_workspace_scope_filters(
                ctx, auth, "user-1", {"status": "open"}
            )

        assert denied is False
        assert result_filters is not None
        assert result_filters["status"] == "open"
        assert "__scope_predicate" in result_filters
        assert result_filters["__scope_predicate"] == ("school_id = $1", ["school-1"])

    def test_scope_wildcard_persona_matches_any_role(self) -> None:
        """Scope rule with '*' persona matches any authenticated user."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        scope = _make_scope_rule("list", ["*"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["random_role"])

        result_filters, denied = _apply_workspace_scope_filters(ctx, auth, "user-1", None)

        assert denied is False

    def test_scope_denied_produces_empty_items(self) -> None:
        """When scope returns None (default-deny), denied flag is True."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        # Scope rule for a different operation — "list" won't match
        scope = _make_scope_rule("read", ["admin"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["admin"])

        result_filters, denied = _apply_workspace_scope_filters(ctx, auth, "user-1", None)

        assert denied is True


# ===========================================================================
# Integration: WorkspaceRegionContext has new fields
# ===========================================================================


class TestWorkspaceRegionContextFields:
    """Verify WorkspaceRegionContext carries cedar_access_spec and fk_graph."""

    def test_default_none(self) -> None:
        """New fields default to None for backward compat."""
        ctx = _make_region_ctx()
        assert ctx.cedar_access_spec is None
        assert ctx.fk_graph is None

    def test_access_spec_set(self) -> None:
        """cedar_access_spec is stored on context."""
        access = SimpleNamespace(scopes=[], permissions=[])
        ctx = _make_region_ctx(cedar_access_spec=access)
        assert ctx.cedar_access_spec is access

    def test_fk_graph_set(self) -> None:
        """fk_graph is stored on context."""
        fk = SimpleNamespace()
        ctx = _make_region_ctx(fk_graph=fk)
        assert ctx.fk_graph is fk


# ===========================================================================
# Aggregate scope-denial gating (#887)
# ===========================================================================
#
# Charts and metric tiles share the same scope contract as list items: when
# `_apply_workspace_scope_filters` returns `(_, True)` (no scope rule
# matched the user's roles → default-deny), the aggregate / bucketed /
# pivot / overlay code paths must NOT run. Pre-fix, the items list was
# empty (correctly), but the aggregate SQL queries fired with no filter,
# leaking cross-tenant counts / sums / averages.
#
# These tests exercise the gating at the call-site level: with scope
# returning denied, the aggregate helpers must not be invoked.


class TestAggregateScopeGate:
    """Pin the #887 fix — aggregates suppressed when scope denies."""

    def test_default_deny_initial_state_blocks_aggregates(self) -> None:
        """The pre-init defaults are `_scope_denied = True`. If scope
        evaluation never runs (no repo / early exception), aggregates
        must not fire — the unbound-then-used pattern that pre-existed
        could surface as either NameError OR (worse, silently) as
        unfiltered SQL."""
        # Read the source and verify the pre-init is in place. This is
        # a lightweight invariant check that catches future regressions
        # where someone removes the default-deny init.
        from pathlib import Path

        src = Path("/Volumes/SSD/Dazzle/src/dazzle_back/runtime/workspace_rendering.py").read_text()
        # The pre-init must default-deny; explicit `True` is the contract.
        assert "_scope_denied: bool = True" in src, (
            "Default-deny init missing — #887 regression risk"
        )

    def test_aggregate_call_sites_gated_on_scope_denied(self) -> None:
        """Each aggregate / bucketed / pivot call site in
        `_workspace_region_handler` must include `not _scope_denied`
        in its guard. This is a static check on the source — if a
        future edit removes one of these guards, this test fails
        loudly before the bypass reaches production."""
        from pathlib import Path

        src = Path("/Volumes/SSD/Dazzle/src/dazzle_back/runtime/workspace_rendering.py").read_text()
        # Count gate uses in `_workspace_region_handler` — there are
        # 4 aggregate call sites in that handler (metrics / bucketed /
        # overlays / pivot) plus 1 in `_fetch_region_json`. Every one
        # must either short-circuit on `_scope_denied` or the function
        # itself must fail with that flag set.
        assert src.count("and not _scope_denied") >= 4, (
            "Expected ≥4 `not _scope_denied` guards across aggregate call "
            "sites in workspace_rendering.py — #887 fix incomplete"
        )
        # `_fetch_region_json` uses an `if ... and not _scope_denied:` form
        # via the `if ctx.ctx_region.aggregates and not _scope_denied:` line.
        assert "ctx.ctx_region.aggregates and not _scope_denied" in src, (
            "_fetch_region_json aggregate gate missing — #887 fix incomplete"
        )

    def test_apply_workspace_scope_filters_returns_denied_for_unmatched_role(
        self,
    ) -> None:
        """End-to-end-ish: when a scope rule names role `admin` and the
        user has only `viewer`, the helper must return denied=True.
        This is the upstream signal that the aggregate gates rely on."""
        from dazzle_back.runtime.workspace_rendering import (
            _apply_workspace_scope_filters,
        )

        scope = _make_scope_rule("list", ["admin"])
        access = _make_access_spec_with_scopes([scope])
        ctx = _make_region_ctx(cedar_access_spec=access)
        auth = _make_auth_context(["viewer"])

        _filters, denied = _apply_workspace_scope_filters(ctx, auth, "user-1", None)
        assert denied is True, (
            "viewer should be denied list-scope on admin-only rule — "
            "if this fires False the aggregate gate downstream is bypassed"
        )
