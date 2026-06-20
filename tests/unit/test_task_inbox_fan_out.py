"""Issue #1015 (v0.67.16): regression tests for the task_inbox
upstream fan-out helper.

Covers `_fetch_task_inbox_items_per_source` — the async helper
that fans out one query per declared source, scopes each against
the source entity's own access spec, and gathers results in
parallel via asyncio.gather.

Tests use stub repositories with deterministic per-entity row
lists; no real DB. RBAC scope is exercised by the wrapping
`_apply_workspace_scope_filters` call against the stub access
specs (None → no scope, empty scope rules → default-deny).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from dazzle.core.ir.workspaces import TaskInboxConfig, TaskSource, TaskSourceTemplate
from dazzle.http.runtime.workspace_card_fetchers import _fetch_task_inbox_items_per_source


class _StubRepo:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items
        self.last_filters: dict[str, Any] | None = None

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        filters: dict[str, Any] | None = None,
        sort: Any = None,
        include: Any = None,
        fk_display_only: bool = True,
    ) -> dict[str, Any]:
        self.last_filters = dict(filters or {})
        return {"items": list(self._items), "total": len(self._items)}


class _ExplodingRepo:
    async def list(self, **kwargs) -> Any:
        raise RuntimeError("synthetic repo failure")


@dataclass
class _StubCtx:
    """Minimal duck-typed WorkspaceRegionContext stand-in covering
    the fields the fan-out helper reads."""

    repositories: dict[str, Any]
    entity_access_specs: dict[str, Any]
    source: str = "Primary"
    cedar_access_spec: Any = None
    fk_graph: Any = None
    user_entity_name: str = "User"
    ctx_region: Any = None
    ir_region: Any = None
    entity_spec: Any = None
    attention_signals: list[Any] = field(default_factory=list)
    ws_access: Any = None
    require_auth: bool = False
    auth_middleware: Any = None
    precomputed_columns: list[dict[str, Any]] = field(default_factory=list)
    auto_include: list[str] = field(default_factory=list)
    surface_default_sort: list[Any] = field(default_factory=list)
    surface_empty_message: str = ""
    param_resolver: Any = None
    tenant_id: str | None = None
    entity_ref_targets: dict[str, dict[str, str]] = field(default_factory=dict)


def _config(*, sources: list[TaskSource]) -> TaskInboxConfig:
    return TaskInboxConfig(sources=sources)


@pytest.mark.asyncio
async def test_returns_empty_when_no_sources() -> None:
    cfg = _config(sources=[])
    ctx = _StubCtx(repositories={"X": _StubRepo([])}, entity_access_specs={})
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    assert result == {}


@pytest.mark.asyncio
async def test_returns_empty_when_no_repositories() -> None:
    cfg = _config(
        sources=[
            TaskSource(
                source="X",
                as_task=TaskSourceTemplate(icon="x", title="t"),
            )
        ]
    )
    ctx = _StubCtx(repositories={}, entity_access_specs={})
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    assert result == {}


@pytest.mark.asyncio
async def test_fetches_each_source_independently() -> None:
    repo_a = _StubRepo([{"id": "a1", "name": "Alice"}, {"id": "a2", "name": "Bob"}])
    repo_b = _StubRepo([{"id": "b1", "name": "Carol"}])
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
            TaskSource(source="B", count_as="bs"),
        ]
    )
    ctx = _StubCtx(
        repositories={"A": repo_a, "B": repo_b},
        entity_access_specs={"A": None, "B": None},
    )
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    assert result == {
        0: [{"id": "a1", "name": "Alice"}, {"id": "a2", "name": "Bob"}],
        1: [{"id": "b1", "name": "Carol"}],
    }


@pytest.mark.asyncio
async def test_skips_sources_with_missing_repository() -> None:
    repo_a = _StubRepo([{"id": "a1"}])
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
            TaskSource(source="MissingEntity", count_as="x"),
        ]
    )
    ctx = _StubCtx(repositories={"A": repo_a}, entity_access_specs={"A": None})
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    # Only source 0 fetched; source 1's missing repo silently dropped.
    assert 0 in result
    assert 1 not in result


@pytest.mark.asyncio
async def test_failed_source_treated_as_empty_doesnt_block_others() -> None:
    repo_a = _ExplodingRepo()
    repo_b = _StubRepo([{"id": "b1"}])
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
            TaskSource(source="B", count_as="x"),
        ]
    )
    ctx = _StubCtx(
        repositories={"A": repo_a, "B": repo_b},
        entity_access_specs={"A": None, "B": None},
    )
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    # Source 0 failed → empty. Source 1 succeeded with 1 row.
    assert result[0] == []
    assert len(result[1]) == 1


@pytest.mark.asyncio
async def test_source_filter_lands_in_repo_filters() -> None:
    """The source's filter expression should be converted via
    _extract_condition_filters and applied to the repo query."""
    from dazzle.core.ir.conditions import (
        Comparison,
        ComparisonOperator,
        ConditionExpr,
        ConditionValue,
    )

    repo_a = _StubRepo([])
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                filter=ConditionExpr(
                    comparison=Comparison(
                        field="status",
                        operator=ComparisonOperator.EQUALS,
                        value=ConditionValue(literal="active"),
                    )
                ),
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
        ]
    )
    ctx = _StubCtx(repositories={"A": repo_a}, entity_access_specs={"A": None})
    await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id="u1"
    )
    assert repo_a.last_filters == {"status": "active"}


@pytest.mark.asyncio
async def test_source_filter_dotted_path_uses_ref_targets() -> None:
    """#1232 Gap 1 — a left-side dotted FK path (e.g. `teacher.user = X`)
    must be resolved via the source entity's FK→target map (ref_targets)
    by `_build_fk_path_subquery`. Without threading ``entity_ref_targets``
    from ctx, the dotted path falls through as a literal filter key
    `teacher.user` that the repository layer cannot recognise."""
    from dazzle.core.ir.conditions import (
        Comparison,
        ComparisonOperator,
        ConditionExpr,
        ConditionValue,
    )

    repo_a = _StubRepo([])
    cfg = _config(
        sources=[
            TaskSource(
                source="TimetableSlot",
                # `teacher.user` is a dotted left-side path:
                #   TimetableSlot.teacher → StaffMember.user
                filter=ConditionExpr(
                    comparison=Comparison(
                        field="teacher.user",
                        operator=ComparisonOperator.EQUALS,
                        value=ConditionValue(literal="user-uuid"),
                    )
                ),
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
        ]
    )
    ctx = _StubCtx(
        repositories={"TimetableSlot": repo_a},
        entity_access_specs={"TimetableSlot": None},
        entity_ref_targets={"TimetableSlot": {"teacher": "StaffMember"}},
    )
    await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id="user-uuid"
    )

    # Post-fix: `_build_fk_path_subquery` produces a `teacher__in_subquery`
    # filter ("SELECT id FROM StaffMember WHERE user = %s", ["user-uuid"]).
    assert repo_a.last_filters is not None, "fetch path didn't fire"
    assert "teacher__in_subquery" in repo_a.last_filters, (
        f"expected teacher__in_subquery from FK-path resolution; got {repo_a.last_filters}"
    )
    sql, params = repo_a.last_filters["teacher__in_subquery"]
    assert '"StaffMember"' in sql, sql
    assert '"user"' in sql, sql
    assert params == ["user-uuid"], params


@pytest.mark.asyncio
async def test_source_filter_dotted_path_without_ref_targets_falls_through() -> None:
    """#1232 — pre-fix behaviour confirmation: when entity_ref_targets is
    not threaded (empty dict), the dotted-path filter falls through as a
    literal `teacher.user` key — the repo never sees the JOIN it needs."""
    from dazzle.core.ir.conditions import (
        Comparison,
        ComparisonOperator,
        ConditionExpr,
        ConditionValue,
    )

    repo_a = _StubRepo([])
    cfg = _config(
        sources=[
            TaskSource(
                source="TimetableSlot",
                filter=ConditionExpr(
                    comparison=Comparison(
                        field="teacher.user",
                        operator=ComparisonOperator.EQUALS,
                        value=ConditionValue(literal="user-uuid"),
                    )
                ),
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
        ]
    )
    ctx = _StubCtx(
        repositories={"TimetableSlot": repo_a},
        entity_access_specs={"TimetableSlot": None},
        entity_ref_targets={},  # empty — simulates the pre-fix shape
    )
    await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id="user-uuid"
    )
    # Without ref_targets the dotted path stays a literal key. The repo
    # has no JOIN; this confirms the bug — and is the regression boundary.
    assert repo_a.last_filters is not None
    assert "teacher__in_subquery" not in repo_a.last_filters
    assert "teacher.user" in repo_a.last_filters


@pytest.mark.asyncio
async def test_skips_sources_without_source_name() -> None:
    """Defensive: a source IR with empty `source:` (parser would
    reject this but defensive against partial IR) is skipped, not
    treated as a wildcard."""
    repo_a = _StubRepo([{"id": "a1"}])
    cfg = _config(
        sources=[
            TaskSource(source="", count_as="x"),
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="t"),
            ),
        ]
    )
    ctx = _StubCtx(repositories={"A": repo_a}, entity_access_specs={"A": None})
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    assert 0 not in result
    assert 1 in result
    assert len(result[1]) == 1


@pytest.mark.asyncio
async def test_repo_returning_list_directly_handled() -> None:
    """Some repo backends return a bare list rather than {items, total}."""

    class _ListRepo:
        async def list(self, **kwargs) -> Any:
            return [{"id": "x1"}]

    cfg = _config(sources=[TaskSource(source="X", count_as="x")])
    ctx = _StubCtx(repositories={"X": _ListRepo()}, entity_access_specs={"X": None})
    result = await _fetch_task_inbox_items_per_source(
        config=cfg, ctx=ctx, request=None, auth_context=None, user_id=None
    )
    assert result[0] == [{"id": "x1"}]
