"""Renderer support for Button/Link/Interactive/InlineEdit + Toolbar.

Tests the typed-htmx-field -> hx-* attribute emission path."""

import pytest

from dazzle.render.fragment import (
    URL,
    Button,
    HxTrigger,
    InlineEdit,
    Interactive,
    Link,
    TargetSelector,
    Text,
    Toolbar,
)
from dazzle.render.fragment.renderer import FragmentRenderer

_T = TargetSelector("#t")


@pytest.mark.parametrize(
    ("fragment", "present", "absent"),
    [
        # A button without htmx fields emits no hx-* attributes.
        pytest.param(
            Button(label="Save", variant="primary"),
            ("Save", 'class="dz-button"', 'data-dz-variant="primary"'),
            ("hx-",),
            id="button-label-and-variant-without-htmx",
        ),
        pytest.param(
            Button(
                label="Refresh",
                hx_get=URL("/refresh"),
                hx_target=TargetSelector("#region-task_list-main"),
                hx_swap="innerHTML",
            ),
            ('hx-get="/refresh"', 'hx-target="#region-task_list-main"', 'hx-swap="innerHTML"'),
            (),
            id="button-hx-get-target-swap",
        ),
        pytest.param(
            Button(
                label="Delete",
                variant="danger",
                hx_post=URL("/tasks/42/delete"),
                hx_target=TargetSelector("closest tr"),
                hx_swap="delete",
                hx_confirm="Are you sure?",
            ),
            ('hx-post="/tasks/42/delete"', 'hx-confirm="Are you sure?"'),
            (),
            id="button-hx-post-with-confirm",
        ),
        # Phase 4B.1.d: hx_put / hx_vals / hx_ext. hx-vals is single-quoted so
        # the JSON's double quotes need no escaping; extensions comma-join.
        pytest.param(
            Button(label="Approve", hx_put=URL("/api/items/42"), hx_target=_T),
            ('hx-put="/api/items/42"',),
            (),
            id="button-hx-put",
        ),
        pytest.param(
            Button(label="Set", hx_post=URL("/x"), hx_target=_T, hx_vals='{"status": "approved"}'),
            ('hx-vals=\'{"status": "approved"}\'',),
            (),
            id="button-hx-vals-single-quoted",
        ),
        pytest.param(
            Button(label="X", hx_post=URL("/x"), hx_target=_T, hx_ext=("json-enc", "morph")),
            ('hx-ext="json-enc,morph"',),
            (),
            id="button-hx-ext-comma-joined",
        ),
        # Full queue transition shape (legacy queue.html inline action button).
        pytest.param(
            Button(
                label="Mark resolved",
                hx_put=URL("/api/queue/42"),
                hx_target=TargetSelector("#region-tickets"),
                hx_swap="innerHTML",
                hx_vals='{"status": "resolved"}',
                hx_ext=("json-enc",),
            ),
            (
                'hx-put="/api/queue/42"',
                'hx-target="#region-tickets"',
                'hx-swap="innerHTML"',
                'hx-ext="json-enc"',
                "hx-vals=",
                "Mark resolved",
            ),
            (),
            id="button-queue-transition-shape",
        ),
        pytest.param(
            Link(label="Open", href=URL("/items/42")),
            ('href="/items/42"', "Open"),
            (),
            id="link",
        ),
        pytest.param(
            Interactive(
                child=Text("clickable area"),
                hx_get=URL("/details/42"),
                hx_target=TargetSelector("#detail-pane"),
                hx_trigger=HxTrigger("click"),
            ),
            ('hx-get="/details/42"', 'hx-trigger="click"', "clickable area"),
            (),
            id="interactive-wrapper",
        ),
        pytest.param(
            InlineEdit(field_name="title", value="Original", placeholder="Enter title"),
            ("Original", 'data-field="title"'),
            (),
            id="inline-edit",
        ),
        pytest.param(
            Toolbar(label="Actions", actions=(Button(label="New", variant="primary"),)),
            ("dz-toolbar", "New"),
            (),
            id="toolbar-with-actions",
        ),
    ],
)
def test_renders(fragment: object, present: tuple[str, ...], absent: tuple[str, ...]) -> None:
    out = FragmentRenderer().render(fragment)
    assert [s for s in present if s not in out] == []
    assert [s for s in absent if s in out] == []


def test_render_button_visibility_hidden_uses_native_attribute() -> None:
    out = FragmentRenderer().render(Button(label="Maybe", visibility="hidden"))
    assert " hidden>" in out or " hidden " in out
