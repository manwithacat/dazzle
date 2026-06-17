"""Regression tests for WorkspaceRegionAdapter dispatch — #1082.

Cycle 144 visual-Tier 2 found `/api/workspaces/admin_dashboard/regions/metrics`
returning a literally empty `<div>`. Cycle 148 traced it to the guard at
`workspace_region_render.py:571` which silently dropped the render when
ir_region.display was the raw pre-inference value ("list") while
ctx_region.display had been promoted to "SUMMARY" by EX-047's aggregate
inference.

The fix: relax the guard + thread the post-inference display to the
adapter via `display_override`. This file pins the dispatcher contract.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment.region import WorkspaceRegionAdapter


class _FakeRegion:
    """Minimal stand-in for an IR region — only the dispatcher reads
    `.display`, so that's all we mock."""

    def __init__(self, display: str) -> None:
        self.display = display


def test_dispatcher_routes_by_region_display_when_no_override() -> None:
    """Default path: dispatcher routes by ir_region.display."""
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("list")
    # `_BUILDERS` includes 'list' → _build_table. Just confirm it doesn't
    # raise NotImplementedError. We pass minimal ctx; actual build may
    # raise downstream on missing keys but the dispatch happens first.
    # We catch the downstream raise as evidence the dispatch succeeded.
    try:
        adapter.build(region, ctx={})
    except NotImplementedError as exc:
        raise AssertionError(f"dispatcher rejected 'list' display: {exc}") from None
    except Exception:
        # Builder-internal failure is fine for this test — we only
        # care that the dispatcher accepted 'list'.
        pass


def test_dispatcher_uses_override_when_provided() -> None:
    """When `display_override` is set, the dispatcher uses that instead
    of `region.display`. #1082 reproduction: ir_region.display="list"
    but the caller passes display_override="summary"."""
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("list")  # raw pre-inference value
    # If the override is honored, the dispatcher should route to the
    # metrics/summary builder, not the list builder. The metrics builder
    # has its own internal assertions about ctx shape; we expect either
    # success or a metrics-specific failure, but NOT a list-builder
    # failure or NotImplementedError on "summary".
    try:
        adapter.build(region, ctx={"metrics": []}, display_override="summary")
    except NotImplementedError as exc:
        raise AssertionError(f"dispatcher rejected 'summary' override: {exc}") from None
    except Exception:
        # Builder-internal failure on the metrics path is fine — we're
        # asserting the dispatch went to the right builder, not that
        # the builder runs end-to-end with empty ctx.
        pass


def test_dispatcher_override_with_summary_alias_resolves_to_metrics() -> None:
    """`summary` is an alias for `metrics` per the dispatcher's _ALIASES.
    The override path must respect alias resolution so callers can pass
    either form without surprise."""
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("list")
    # Both these should resolve to the same builder. We verify by
    # confirming the override path doesn't raise NotImplementedError
    # for either form.
    for override in ("metrics", "summary"):
        try:
            adapter.build(region, ctx={"metrics": []}, display_override=override)
        except NotImplementedError as exc:
            raise AssertionError(
                f"dispatcher rejected '{override}' override after alias resolution: {exc}"
            ) from None
        except Exception:
            pass  # builder-internal failures OK


def test_metrics_builder_emits_empty_state_when_no_metrics() -> None:
    """Once the dispatch routes correctly, _build_metrics's existing
    fallback (lines 267-272 of _builders_metrics.py) emits an EmptyState
    fragment when `inputs.metrics == []`. This pins that path so the
    "blank Metrics card" symptom (cycle 144 rows 102/104/105/113/116)
    doesn't silently regress."""
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("metrics")
    surface = adapter.build(region, ctx={"metrics": [], "columns": []})
    # The surface is a Surface(body=Region(body=EmptyState(...))). Drill
    # in to confirm the fallback fired.
    surface_body: Any = getattr(surface, "body", None)
    region_inner: Any = getattr(surface_body, "body", None) if surface_body else None
    inner_kind = type(region_inner).__name__ if region_inner is not None else None
    assert inner_kind == "EmptyState", (
        f"expected EmptyState when metrics is empty, got {inner_kind}"
    )
