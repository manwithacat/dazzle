"""Task 3b (ADR-0049 Phase 2): substrate detail wrapper attrs + audit-history + Back.

The substrate detail wrapper lacked `data-dazzle-entity` — the selector
`tier2_playwright` e2e gestures use to scope a detail surface (the E2E tier
would catch this at the view-flip). It also dropped the audit-history slot
(`show_history` → an htmx-loaded `/_dazzle/audit-history/{entity}/{id}` region)
and the Back affordance. This pins them.
"""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import DetailContext, FieldContext
from dazzle.render.fragment import FragmentRenderer


class _Surface:
    name = "task_detail"
    title = "Task"
    mode = SurfaceMode.VIEW
    entity_ref = "Task"
    sections = ()
    related_groups = ()


class _RC:
    def __init__(self, detail: DetailContext) -> None:
        self.table = None
        self.form = None
        self.detail = detail


def _detail(**over: object) -> DetailContext:
    base: dict = {
        "entity_name": "Task",
        "title": "Ship it",
        "fields": [FieldContext(name="title", label="Title")],
        "item": {"id": "abc-123", "title": "Ship it"},
        "back_url": "/task",
    }
    base.update(over)
    return DetailContext(**base)


def _render(detail: DetailContext) -> str:
    ctx = _build_dispatch_ctx(_RC(detail), _Surface())
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(_Surface(), ctx))


def test_detail_wrapper_carries_entity_anchor() -> None:
    html = _render(_detail())
    # the selector tier2_playwright gestures use to scope the detail surface
    assert 'data-dazzle-entity="Task"' in html
    assert 'data-dz-entity-id="abc-123"' in html


def test_back_affordance_present() -> None:
    html = _render(_detail(back_url="/task"))
    assert 'href="/task"' in html
    assert "Back" in html


def test_audit_history_slot_when_show_history() -> None:
    html = _render(_detail(show_history=True))
    assert 'hx-get="/_dazzle/audit-history/Task/abc-123"' in html
    assert "dz-detail-audit-history" in html
    assert 'hx-trigger="load"' in html


def test_no_audit_history_by_default() -> None:
    html = _render(_detail())
    assert "dz-detail-audit-history" not in html
