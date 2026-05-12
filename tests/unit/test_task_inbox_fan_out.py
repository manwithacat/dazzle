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

from dazzle.back.runtime.workspace_rendering import _fetch_task_inbox_items_per_source
from dazzle.core.ir.workspaces import TaskInboxConfig, TaskSource, TaskSourceTemplate


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
