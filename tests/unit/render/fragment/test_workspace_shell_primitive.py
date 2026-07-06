"""Phase 4B.5.b.1 (v0.66.120): structural tests for the typed
`WorkspaceShell` primitive.

Pins the chrome contract emitted by `_emit_workspace_shell`:

  - `<div class="dz-workspace" data-dz-dashboard-builder ...>`
    outer wrapper carrying the Alpine state machine + workspace name
    + optional fold count.
  - `<div class="dz-workspace-heading">` with `<h2 class="dz-workspace-title">`
    and an optional primary-actions row.

Byte-equivalence against the full legacy `workspace/_content.html` is
gated to 4B.5.b.3 once the slot grid + drawer + picker are also typed.
This module pins the structural contract (attribute names, class
names, HTMX/Alpine bindings) so any regression in those is caught
immediately even before the full byte-equivalence test lands."""

from __future__ import annotations

from dazzle.render.fragment import (
    FragmentRenderer,
    Text,
    WorkspacePrimaryAction,
    WorkspaceShell,
)


def _render(ws: WorkspaceShell) -> str:
    return FragmentRenderer().render(ws)


def test_workspace_shell_emits_outer_wrapper_with_builder_marker() -> None:
    """The outer `<div class="dz-workspace">` carries
    `data-dz-dashboard-builder` — the vanilla controller root that owns
    saveState / isDragging / isResizing / showPicker."""
    html = _render(WorkspaceShell(workspace_name="dashboard", title="X", body=Text("")))
    assert '<div class="dz-workspace"' in html
    assert "data-dz-dashboard-builder" in html
    assert "x-data" not in html


def test_workspace_shell_carries_workspace_name_data_attribute() -> None:
    """`data-workspace-name` flows through `data-*` attributes the JS
    reads on demand (#948 — DOM is the source of truth, no JSON island)."""
    html = _render(WorkspaceShell(workspace_name="ops_dash", title="Ops", body=Text("")))
    assert 'data-workspace-name="ops_dash"' in html


def test_workspace_shell_emits_fold_count_when_supplied() -> None:
    """`data-fold-count` is optional in the legacy template
    (`{% if fold_count is defined %}`); the typed primitive omits the
    attribute when `fold_count is None`."""
    html_with = _render(WorkspaceShell(workspace_name="d", title="X", body=Text(""), fold_count=3))
    assert 'data-fold-count="3"' in html_with

    html_without = _render(WorkspaceShell(workspace_name="d", title="X", body=Text("")))
    assert "data-fold-count" not in html_without


def test_workspace_shell_renders_heading_with_h2_title() -> None:
    """The heading row carries the user-facing title in a `dz-workspace-title`
    `<h2>`."""
    html = _render(WorkspaceShell(workspace_name="d", title="My Dashboard", body=Text("")))
    assert '<div class="dz-workspace-heading">' in html
    assert '<h2 class="dz-workspace-title">My Dashboard</h2>' in html


def test_workspace_shell_escapes_title_html() -> None:
    """Title content is escaped so user-supplied workspace titles
    can't inject markup."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="<script>alert(1)</script>",
            body=Text(""),
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_workspace_shell_omits_primary_actions_row_when_empty() -> None:
    """Legacy template wraps the row in `{% if primary_actions %}` —
    the typed primitive matches by emitting nothing when the tuple is
    empty (no empty `<div class="dz-workspace-primary-actions">` shell)."""
    html = _render(WorkspaceShell(workspace_name="d", title="X", body=Text("")))
    assert "dz-workspace-primary-actions" not in html


def test_workspace_shell_renders_primary_actions_row_with_test_id() -> None:
    """Primary actions row carries `data-test-id="dz-workspace-primary-actions"`
    — Playwright + the contract checker key off this attribute."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text(""),
            primary_actions=(WorkspacePrimaryAction(label="New ticket", route="/api/tickets/new"),),
        )
    )
    assert (
        '<div class="dz-workspace-primary-actions" data-test-id="dz-workspace-primary-actions">'
    ) in html


def test_workspace_shell_primary_actions_use_hx_boost_anchors() -> None:
    """Each primary action is an `<a class="dz-workspace-action" hx-boost="true">`
    — boost upgrades it to an HTMX swap so the navigation doesn't
    blow away the workspace shell. ADR-0050 3a also tags it with an
    `hx-headers` `X-Dz-Usage-Action` carrying `<workspace>|<route>` so the
    boosted click records a usage event server-side."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text(""),
            primary_actions=(WorkspacePrimaryAction(label="New", route="/api/new"),),
        )
    )
    assert '<a href="/api/new" hx-boost="true" class="dz-workspace-action"' in html
    assert ">New</a>" in html
    # ADR-0050 3a: the boosted anchor carries its (surface|action) identity.
    assert "X-Dz-Usage-Action" in html
    assert "d|/api/new" in html


def test_workspace_shell_omits_overflow_menu_when_empty() -> None:
    """3a (#1491): no overflow actions → no `More ⋯` menu (byte-stable for the
    common ≤budget heading)."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text(""),
            primary_actions=(WorkspacePrimaryAction(label="New", route="/api/new"),),
        )
    )
    assert "dz-workspace-more" not in html


def test_workspace_shell_renders_overflow_details_menu() -> None:
    """3a (#1491): demoted actions render in a native `<details>` `More ⋯`
    dropdown inside the primary-actions row (JS-free)."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text(""),
            primary_actions=(WorkspacePrimaryAction(label="New", route="/api/new"),),
            overflow_actions=(
                WorkspacePrimaryAction(label="Export", route="/api/export"),
                WorkspacePrimaryAction(label="Archive all", route="/api/archive"),
            ),
        )
    )
    # HM `menu` Hyperpart: native <details> disclosure, `.dz-menu` classes, no
    # ARIA menu roles. The `data-test-id` is kept as the stable selector.
    assert '<details class="dz-menu" data-test-id="dz-workspace-more">' in html
    assert '<a href="/api/export" hx-boost="true" class="dz-menu__item"' in html
    assert ">Archive all</a>" in html
    assert 'role="menu"' not in html and 'role="menuitem"' not in html
    # The overflow menu lives inside the primary-actions row.
    assert html.index("dz-workspace-primary-actions") < html.index("dz-workspace-more")


def test_workspace_shell_primary_actions_carry_plus_icon_svg() -> None:
    """Each primary action has a leading `+` SVG icon — the path
    `M12 4v16m8-8H4` is the framework's plus-icon glyph."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text(""),
            primary_actions=(WorkspacePrimaryAction(label="Add", route="/api/add"),),
        )
    )
    assert 'd="M12 4v16m8-8H4"' in html
    assert 'aria-hidden="true"' in html


def test_workspace_shell_renders_body_slot_after_heading() -> None:
    """The body Fragment is rendered AFTER the heading section and
    BEFORE the closing `</div>` of the outer wrapper."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text("BODY-SLOT"),
        )
    )
    heading_end = html.index("</div>")  # closes dz-workspace-heading
    body_pos = html.index("BODY-SLOT")
    assert body_pos > heading_end


def test_workspace_shell_escapes_action_route_attribute() -> None:
    """Action routes are escaped as attribute values so a malicious
    URL can't break out of the `href` attribute."""
    html = _render(
        WorkspaceShell(
            workspace_name="d",
            title="X",
            body=Text(""),
            primary_actions=(WorkspacePrimaryAction(label="X", route='/api"><script>'),),
        )
    )
    assert "<script>" not in html
    assert "&#x22;" in html or "&quot;" in html or '\\"' in html
