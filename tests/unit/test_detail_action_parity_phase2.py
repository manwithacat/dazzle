"""Task 2 (ADR-0049 Phase 2): substrate detail-action parity.

The substrate `_build_view` action toolbar dropped the `data-dazzle-action`
analytics anchors (consumed by dz-analytics.js), used `hx-post` without the
`hx-vals` status payload for transitions (legacy `hx-put` + `hx-vals` — the
substrate transition was functionally broken), and lost `target="_blank"` on
new-tab external links. This pins the fixed parity. The dispatch ctx also had to
thread `status_field` + integration `integration_name`/`mapping_name` + external
`name` (the Phase-1 "incomplete adapter" class).
"""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import (
    DetailContext,
    ExternalLinkAction,
    FieldContext,
    IntegrationActionContext,
    TransitionContext,
)
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
        "item": {"id": "abc", "title": "Ship it"},
        "status_field": "status",
    }
    base.update(over)
    return DetailContext(**base)


def _render(detail: DetailContext) -> str:
    ctx = _build_dispatch_ctx(_RC(detail), _Surface())
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(_Surface(), ctx))


def test_edit_link_carries_action_anchor() -> None:
    html = _render(_detail(edit_url="/task/abc/edit"))
    assert 'data-dazzle-action="Task.edit"' in html
    assert 'href="/task/abc/edit"' in html


def test_delete_button_carries_action_anchor() -> None:
    html = _render(_detail(delete_url="/api/task/abc"))
    assert 'data-dazzle-action="Task.delete"' in html
    assert 'hx-delete="/api/task/abc"' in html


def test_transition_uses_hx_put_with_status_vals() -> None:
    html = _render(
        _detail(
            transitions=[
                TransitionContext(to_state="done", label="Mark Done", api_url="/api/task/abc")
            ]
        )
    )
    assert 'data-dazzle-action="Task.transition.done"' in html
    # the real fix: hx-put + hx-vals carrying the status field → target state
    assert 'hx-put="/api/task/abc"' in html
    assert '"status": "done"' in html or "status&quot;: &quot;done" in html
    # not the broken hx-post-without-vals
    assert 'hx-post="/api/task/abc"' not in html


def test_integration_action_anchor() -> None:
    html = _render(
        _detail(
            integration_actions=[
                IntegrationActionContext(
                    label="Verify",
                    integration_name="ch",
                    mapping_name="verify",
                    api_url="/api/task/abc/integrations/ch/verify",
                )
            ]
        )
    )
    assert 'data-dazzle-action="Task.integration.ch.verify"' in html
    assert 'hx-post="/api/task/abc/integrations/ch/verify"' in html


def test_external_link_new_tab_and_anchor() -> None:
    html = _render(
        _detail(
            external_link_actions=[
                ExternalLinkAction(name="docs", label="Open Docs", url="https://x", new_tab=True)
            ]
        )
    )
    assert 'data-dazzle-action="Task.external.docs"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_non_new_tab_external_has_no_target() -> None:
    html = _render(
        _detail(
            external_link_actions=[
                ExternalLinkAction(name="docs", label="Docs", url="https://x", new_tab=False)
            ]
        )
    )
    assert 'data-dazzle-action="Task.external.docs"' in html
    assert 'target="_blank"' not in html
