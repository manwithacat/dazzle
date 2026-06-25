"""No-DB render harness for the UX catalogue (Sub-project A).

Drives the REAL DSL -> IR -> orchestration -> adapter -> HTML path for one
``ux_catalogue`` region, feeding sample data (items + canned aggregate buckets)
from the manifest via a fake repository. No DB, no server, no browser — so the
catalogue doubles as a fidelity gate against DSL->IR->render drift.

Two deliberate deviations from a production request (the catalogue's job is to
*always* show a populated component, not to reproduce auth/scope outcomes):

1. ``scope_denied=False`` + empty scope filters — aggregate paths always render
   their content, even where a real app's missing scope rule would suppress them.
2. Columns are auto-derived from the sample item keys (the handler's fallback),
   not the DSL-configured ``precomputed_columns`` — so column types/visibility
   reflect the data shape, not the per-field DSL column metadata.

Both keep the *render path* real (IR + orchestration + adapter + fragment
renderer are production code); only the data + auth context are stubbed.
"""

import asyncio
from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.aggregate import AggregateBucket
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_region_fetch import RegionItemsResult
from dazzle.http.runtime.workspace_region_orchestration import compute_region_render_inputs
from dazzle.http.runtime.workspace_region_prelude import RequestUserContext
from dazzle.http.runtime.workspace_region_render import render_region_html
from dazzle.page.runtime.workspace_renderer import build_workspace_context
from dazzle.testing.ux_catalogue_manifest import CATALOGUE_MANIFEST

__all__ = [
    "CATALOGUE_MANIFEST",
    "iter_catalogue_regions",
    "load_showcase_appspec",
    "render_catalogue_region",
]

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "component_showcase"


class _FakeRequest:
    """Minimal stand-in for the FastAPI request the region pipeline reads."""

    def __init__(self) -> None:
        self.query_params: dict[str, str] = {}
        self.headers: dict[str, str] = {}


class _CatalogueRepo:
    """Serves canned aggregate buckets + count-metric totals; no DB.

    ``aggregate`` returns the region's canned buckets (group_by chart modes).
    ``list`` returns a canned ``total`` per call (count-metric tiles) — successive
    calls pop ``list_totals`` in order so a multi-count metrics region shows
    distinct numbers, falling back to ``default_total`` when exhausted.
    """

    def __init__(
        self,
        buckets: list[dict[str, Any]] | None = None,
        list_totals: list[int] | None = None,
        default_total: int = 8,
    ) -> None:
        self._buckets = buckets or []
        self._totals = list(list_totals or [])
        self._default_total = default_total

    async def aggregate(
        self,
        *,
        dimensions: Any = None,
        measures: Any = None,
        filters: Any = None,
        **_kw: Any,
    ) -> list[AggregateBucket]:
        return [
            AggregateBucket(dimensions=dict(b["dimensions"]), measures=dict(b["measures"]))
            for b in self._buckets
        ]

    async def list(
        self, *, page: int = 1, page_size: int = 1, filters: Any = None, **_kw: Any
    ) -> dict[str, Any]:
        total = self._totals.pop(0) if self._totals else self._default_total
        return {"items": [], "total": total}


def load_showcase_appspec() -> Any:
    """Parse + link the component_showcase fixture into an AppSpec (reads dazzle.toml)."""
    return load_project_appspec(_FIXTURE)


def iter_catalogue_regions(appspec: Any) -> list[tuple[Any, Any]]:
    """Return the ux_catalogue regions paired with their ctx_region, in order."""
    ws = next(w for w in appspec.workspaces if w.name == "ux_catalogue")
    ws_ctx = build_workspace_context(ws, appspec)
    return list(zip(ws.regions, ws_ctx.regions, strict=False))


def _auto_columns(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror the region handler's column fallback: derive dict columns from item keys."""
    if not items:
        return []
    return [
        {"key": k, "label": k.replace("_", " ").title(), "type": "text", "sortable": True}
        for k in items[0]
        if k != "id"
    ]


def render_catalogue_region(
    appspec: Any, ir_region: Any, ctx_region: Any, entry: dict[str, Any]
) -> str:
    """Render one ux_catalogue region to HTML via the real pipeline (no DB)."""
    source = ir_region.source or ""
    entity_spec = next((e for e in appspec.domain.entities if e.name == source), None)
    items = list(entry.get("sample_items") or [])
    columns = _auto_columns(items)
    repo = _CatalogueRepo(entry.get("canned_buckets"), entry.get("canned_list_totals"))
    # Every entity resolves to the same fake repo so cross-entity counts
    # (`count(OtherEntity)`) find a repository, not just the region source.
    repositories = {e.name: repo for e in appspec.domain.entities}

    ctx = WorkspaceRegionContext(
        ctx_region=ctx_region,
        ir_region=ir_region,
        source=source,
        entity_spec=entity_spec,
        attention_signals=[],
        ws_access=None,
        repositories=repositories,
        require_auth=False,
        auth_middleware=None,
    )
    fetched = RegionItemsResult(
        items=items,
        total=len(items),
        scope_only_filters={},
        context_filters={},
        scope_denied=False,
    )
    user_ctx = RequestUserContext(
        user_id=None, user_entity=None, auth_ctx_for_filters=None, filter_context={}
    )
    request = _FakeRequest()

    async def _run() -> str:
        inputs = await compute_region_render_inputs(request, ctx, user_ctx, fetched, columns)
        return await render_region_html(request, ctx, user_ctx, inputs, None, "")

    return asyncio.run(_run())
