"""Issue #1030 (v0.66.132): regression tests for detail VIEW action
toolbar.

Pre-fix, `_build_dispatch_ctx`'s detail branch only forwarded `fields`
and `related_groups` — `edit_url`, `delete_url`, `transitions`,
`integration_actions`, `external_link_actions` from `DetailContext`
were silently dropped, so the typed adapter rendered no action
buttons. The legacy template's Edit / Delete / Mark-in-progress /
Mark-complete header was missing entirely under `render: fragment`.

Fix: thread all action-bearing fields into ctx; adapter's
`_build_view` composes a Row of action primitives prepended to the
detail body.
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
    name = "task_view"
    title = "Task Detail"
    mode = SurfaceMode.VIEW
    related_groups: list = []


class _RC:
    def __init__(self, detail: DetailContext) -> None:
        self.detail = detail
        self.form = None
        self.table = None


def _detail_with_all_actions() -> DetailContext:
    return DetailContext(
        entity_name="Task",
        title="Task Detail",
        fields=[FieldContext(name="title", label="Title")],
        item={"title": "Buy ingredients"},
        edit_url="/tasks/abc/edit",
        delete_url="/_dazzle/tasks/abc",
        back_url="/tasks",
        transitions=[
            TransitionContext(
                to_state="in_progress",
                label="Mark in progress",
                api_url="/_dazzle/tasks/abc/transitions/in_progress",
            ),
            TransitionContext(
                to_state="complete",
                label="Mark complete",
                api_url="/_dazzle/tasks/abc/transitions/complete",
            ),
        ],
        integration_actions=[
            IntegrationActionContext(
                label="Sync to Slack",
                integration_name="slack",
                mapping_name="task_sync",
                api_url="/_dazzle/tasks/abc/integrations/slack/sync",
            ),
        ],
        external_link_actions=[
            ExternalLinkAction(
                name="docs",
                label="Open in docs",
                url="https://docs.example.test/tasks/abc",
            ),
        ],
    )


def _render_view(detail: DetailContext) -> str:
    ctx = _build_dispatch_ctx(_RC(detail), _Surface())
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_view(_Surface(), ctx))


def test_dispatch_ctx_threads_edit_delete_back_urls() -> None:
    detail = _detail_with_all_actions()
    ctx = _build_dispatch_ctx(_RC(detail), _Surface())
    assert ctx["edit_url"] == "/tasks/abc/edit"
    assert ctx["delete_url"] == "/_dazzle/tasks/abc"
    assert ctx["back_url"] == "/tasks"
    assert ctx["entity_name"] == "Task"


def test_dispatch_ctx_threads_transitions_with_full_shape() -> None:
    """Each transition serialises to {to_state, label, api_url} so the
    adapter can compose Buttons without re-reading model attrs."""
    ctx = _build_dispatch_ctx(_RC(_detail_with_all_actions()), _Surface())
    transitions = ctx["transitions"]
    assert len(transitions) == 2
    assert transitions[0] == {
        "to_state": "in_progress",
        "label": "Mark in progress",
        "api_url": "/_dazzle/tasks/abc/transitions/in_progress",
    }


def test_view_renders_edit_link_with_primary_url() -> None:
    html = _render_view(_detail_with_all_actions())
    assert "Edit" in html
    assert 'href="/tasks/abc/edit"' in html


def test_view_renders_delete_button_with_hx_delete_and_confirm() -> None:
    """Delete button uses Button.hx_delete (added in this release)
    + an entity-name-aware confirm prompt."""
    html = _render_view(_detail_with_all_actions())
    assert 'hx-delete="/_dazzle/tasks/abc"' in html
    assert 'hx-confirm="Delete this task?"' in html
    assert 'hx-target="body"' in html


def test_view_renders_one_button_per_state_machine_transition() -> None:
    """Each TransitionContext gets a Button. ADR-0049 Phase 2: transitions are
    hx-PUT with the status field → target state in hx-vals (legacy semantics —
    the prior hx-post without vals never told the endpoint which state to move
    to), plus a `data-dazzle-action` anchor."""
    html = _render_view(_detail_with_all_actions())
    assert 'hx-put="/_dazzle/tasks/abc/transitions/in_progress"' in html
    assert 'hx-put="/_dazzle/tasks/abc/transitions/complete"' in html
    assert "data-dazzle-action=" in html and ".transition." in html
    assert "Mark in progress" in html
    assert "Mark complete" in html


def test_view_renders_integration_action_button() -> None:
    """Manual integration triggers (e.g. Slack sync) get their own
    Button with hx_post pointing at the integration api_url."""
    html = _render_view(_detail_with_all_actions())
    assert "Sync to Slack" in html
    assert 'hx-post="/_dazzle/tasks/abc/integrations/slack/sync"' in html


def test_view_renders_external_link_as_anchor() -> None:
    """External links are pure navigation — Link primitive (no htmx)."""
    html = _render_view(_detail_with_all_actions())
    assert 'href="https://docs.example.test/tasks/abc"' in html
    assert "Open in docs" in html


def test_view_with_no_actions_renders_just_fields() -> None:
    """A DetailContext with no edit/delete/transitions still renders
    cleanly — the action row is empty so nothing is prepended."""
    detail = DetailContext(
        entity_name="Item",
        title="Item",
        fields=[FieldContext(name="name", label="Name")],
        item={"name": "Widget"},
    )
    html = _render_view(detail)
    assert "Widget" in html
    assert "hx-delete" not in html
    assert "hx-post" not in html
    assert ">Edit<" not in html


def test_button_supports_hx_delete_attribute() -> None:
    """Button gained `hx_delete` in this release. The renderer emits
    `hx-delete="<url>"` and the validation pair allows DELETE alongside
    GET/POST/PUT (mutually exclusive)."""
    from dazzle.render.fragment import URL, Button, FragmentRenderer, TargetSelector

    btn = Button(
        label="Delete",
        hx_delete=URL("/api/x/123"),
        hx_target=TargetSelector("body"),
        variant="danger",
    )
    html = FragmentRenderer().render(btn)
    assert 'hx-delete="/api/x/123"' in html


def test_button_rejects_multiple_http_methods() -> None:
    """Button cannot have more than one of hx_get / hx_post / hx_put /
    hx_delete — same invariant as before, now extended to include
    hx_delete."""
    import pytest

    from dazzle.render.fragment import URL, Button, TargetSelector
    from dazzle.render.fragment.errors import HtmxBindingError

    with pytest.raises(HtmxBindingError, match="more than one"):
        Button(
            label="x",
            hx_post=URL("/a"),
            hx_delete=URL("/b"),
            hx_target=TargetSelector("body"),
        )
