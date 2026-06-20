"""#1204 — Dashboard Remove-card button is permission-gated.

The Remove-card × button on dashboard cards was previously rendered
unconditionally, leaking edit-mode chrome into normal persona views.
Two qa-trial personas (ops_dashboard / oncall_engineer cycle 120 and
contact_manager / small_firm_owner cycle 151) independently flagged it
as workspace noise that eroded their trust.

This module pins the gating contract on three layers:

  1. `DashboardCard.edit_enabled` (default False) controls whether the
     `dz-card-actions` div is emitted at all by `_emit_dashboard_card`.
  2. `DashboardGrid.edit_enabled` (default False) controls the
     `data-grid-editable` attribute on the grid container —
     the contract the JS dashboard-builder reads when it injects cards
     dynamically.
  3. `render_workspace_content_typed(can_edit_layout=...)` threads the
     value from the page-route call site (resolved from the existing
     `is_superuser` check) through to both fields.

Safe default = False everywhere: opt-in, not opt-out."""

from __future__ import annotations

from dazzle.render.fragment import (
    DashboardCard,
    DashboardGrid,
    FragmentRenderer,
)


def _make_card(*, edit_enabled: bool = False) -> DashboardCard:
    return DashboardCard(
        card_id="card-0",
        name="metrics",
        title="Revenue Metrics",
        display="LIST",
        col_span=6,
        row_order=0,
        hx_endpoint="/api/workspaces/dash/regions/metrics",
        edit_enabled=edit_enabled,
    )


def _render(fragment: object) -> str:
    return FragmentRenderer().render(fragment)


class TestDashboardCardEditGating:
    """`_emit_dashboard_card` gates the dz-card-actions div on edit_enabled."""

    def test_default_is_false(self) -> None:
        # The safe default — opt-in, not opt-out.
        card = _make_card()
        assert card.edit_enabled is False

    def test_edit_disabled_omits_actions_div(self) -> None:
        html = _render(_make_card(edit_enabled=False))
        assert "dz-card-actions" not in html
        assert 'aria-label="Remove card"' not in html
        assert 'data-test-id="dz-card-remove"' not in html
        # Header is still present — only the actions block is gated.
        assert 'data-test-id="dz-card-drag-handle"' in html
        assert "Revenue Metrics" in html

    def test_edit_enabled_emits_actions_div(self) -> None:
        html = _render(_make_card(edit_enabled=True))
        assert "dz-card-actions" in html
        assert 'aria-label="Remove card"' in html
        assert 'data-test-id="dz-card-remove"' in html


class TestDashboardGridEditableAttr:
    """`_emit_dashboard_grid` emits `data-grid-editable` mirroring
    `edit_enabled` — the contract the JS dashboard-builder reads."""

    def test_default_is_false(self) -> None:
        grid = DashboardGrid()
        assert grid.edit_enabled is False

    def test_grid_disabled_emits_false(self) -> None:
        html = _render(DashboardGrid(cards=(), edit_enabled=False))
        assert 'data-grid-editable="false"' in html
        assert 'data-grid-editable="true"' not in html

    def test_grid_enabled_emits_true(self) -> None:
        html = _render(DashboardGrid(cards=(), edit_enabled=True))
        assert 'data-grid-editable="true"' in html
        assert 'data-grid-editable="false"' not in html


class TestRenderWorkspaceContentTypedGating:
    """End-to-end through `render_workspace_content_typed` — the public
    entry point the page route calls."""

    def _build_workspace_ctx(self) -> object:
        # Build a minimal WorkspaceContext with one region. We import
        # locally because the workspace_renderer module is heavy and
        # tests that don't need it shouldn't pay the import cost.
        from dazzle.page.runtime.workspace_renderer import WorkspaceContext

        # Construct via dict — WorkspaceContext is a pydantic model.
        return WorkspaceContext(
            name="dash",
            title="Dashboard",
            regions=[
                {
                    "name": "metrics",
                    "title": "Revenue Metrics",
                    "display": "list",
                    "source": "Invoice",
                    "col_span": 6,
                    "eyebrow": "",
                    "notice": {},
                }
            ],
            fold_count=1,
        )

    def test_default_no_remove_buttons(self) -> None:
        from dazzle.page.runtime.workspace_renderer import (
            render_workspace_content_typed,
        )

        ws = self._build_workspace_ctx()
        html = render_workspace_content_typed(
            workspace=ws,
            catalog=[],
            fold_count=1,
            primary_actions=[],
        )
        assert 'aria-label="Remove card"' not in html
        assert "dz-card-actions" not in html
        # Grid attribute still present, but disabled.
        assert 'data-grid-editable="false"' in html

    def test_can_edit_layout_false_no_remove_buttons(self) -> None:
        from dazzle.page.runtime.workspace_renderer import (
            render_workspace_content_typed,
        )

        ws = self._build_workspace_ctx()
        html = render_workspace_content_typed(
            workspace=ws,
            catalog=[],
            fold_count=1,
            primary_actions=[],
            can_edit_layout=False,
        )
        assert 'aria-label="Remove card"' not in html
        assert 'data-grid-editable="false"' in html

    def test_can_edit_layout_true_emits_remove_buttons(self) -> None:
        from dazzle.page.runtime.workspace_renderer import (
            render_workspace_content_typed,
        )

        ws = self._build_workspace_ctx()
        html = render_workspace_content_typed(
            workspace=ws,
            catalog=[],
            fold_count=1,
            primary_actions=[],
            can_edit_layout=True,
        )
        assert 'aria-label="Remove card"' in html
        assert 'data-test-id="dz-card-remove"' in html
        assert 'data-grid-editable="true"' in html
