"""Unit tests for the workspace composite assembler.

``HtmxClient.get_workspace_composite`` fetches the initial workspace
page + the HTMX region content, then stitches them back together so
the contract-checker's shape-nesting gate sees the DOM a user actually
sees. The live-HTTP path requires a running server, but the stitching
logic itself is a pure function — verified here without a server.

This closes the blind spot that let #794 ship three times: the
contract checker was staring at a dashboard slot with a skeleton
inside, not a dashboard slot with a region_card inside.
"""

from __future__ import annotations

import re

from dazzle.testing.ux.htmx_client import (
    _extract_workspace_layout,
    apply_inner_swap,
    assemble_workspace_composite,
)


class TestExtractWorkspaceLayout:
    def test_parses_valid_layout_json(self) -> None:
        html = (
            '<script type="application/json" id="dz-workspace-layout">'
            '{"workspace_name": "teacher_workspace", '
            '"cards": [{"id": "card-0", "region": "grade_distribution", "title": "Grade Distribution"}]}'
            "</script>"
            '<div x-data="dzDashboardBuilder()"></div>'
        )
        layout = _extract_workspace_layout(html)
        assert layout is not None
        assert layout["workspace_name"] == "teacher_workspace"
        assert layout["cards"][0]["region"] == "grade_distribution"

    def test_returns_none_for_non_workspace_page(self) -> None:
        # A list page has no layout JSON
        assert _extract_workspace_layout("<html><body><table></table></body></html>") is None

    def test_returns_none_for_malformed_json(self) -> None:
        html = '<script type="application/json" id="dz-workspace-layout">{not valid json</script>'
        assert _extract_workspace_layout(html) is None


class TestAssembleWorkspaceComposite:
    def test_substitutes_region_into_card_slot(self) -> None:
        # Initial HTML has a card body skeleton with id="region-<name>-<card_id>"
        initial = (
            '<article class="dz-card">'
            "<h3>Grade Distribution</h3>"
            '<div class="px-4 pb-4" id="region-grade_distribution-card-0">'
            '<div class="animate-pulse">loading skeleton</div>'
            "</div></article>"
        )
        region_html = (
            '<div data-dz-region data-dz-region-name="grade_distribution" '
            'id="region-grade_distribution"><p>real chart body</p></div>'
        )
        composite = assemble_workspace_composite(
            initial, {("card-0", "grade_distribution"): region_html}
        )
        assert "real chart body" in composite
        assert "loading skeleton" not in composite

    def test_preserves_wrapper_attributes(self) -> None:
        # The outer slot wrapper (id, class, hx-get, etc.) is preserved
        # so HTMX attrs survive the substitution.
        initial = (
            '<div class="px-4 pb-4" id="region-x-card-1" '
            'hx-get="/api/workspaces/w/regions/x" hx-trigger="intersect once">'
            "<span>skeleton</span>"
            "</div>"
        )
        composite = assemble_workspace_composite(initial, {("card-1", "x"): "<p>real</p>"})
        assert 'hx-get="/api/workspaces/w/regions/x"' in composite
        assert 'hx-trigger="intersect once"' in composite
        assert "<p>real</p>" in composite
        assert "skeleton" not in composite

    def test_missing_region_leaves_skeleton(self) -> None:
        # If a region fetch failed (not in dict), the slot keeps its
        # original content so the composite stays well-formed.
        initial = '<div id="region-y-card-2"><span>placeholder</span></div>'
        composite = assemble_workspace_composite(initial, {})
        assert "placeholder" in composite

    def test_composite_catches_nested_chrome(self) -> None:
        # End-to-end: build a composite that matches the pre-#794-fix
        # shape (region_card emitting own chrome inside dashboard slot)
        # and confirm the shape-nesting scanner flags it.
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        initial = (
            '<div data-card-id="card-0">'
            '<article class="dz-card">'
            "<h3>Grade Distribution</h3>"
            '<div class="px-4 pb-4" id="region-grade_distribution-card-0">'
            '<div class="animate-pulse">loading</div>'
            "</div></article></div>"
        )
        # This is the bad shape — region_card with its own chrome
        bad_region_html = (
            '<div data-dz-region class="dz-card"><h3>Grade Distribution</h3><p>chart</p></div>'
        )
        composite = assemble_workspace_composite(
            initial, {("card-0", "grade_distribution"): bad_region_html}
        )
        nested = find_nested_chromes(composite)
        assert nested, (
            "scanner must flag the dashboard-slot + bad-region-card "
            "pair as nested chrome once the composite is assembled"
        )

    def test_poll_twice_body_only_keeps_single_region_hook(self) -> None:
        """ADR-0054: two inner swaps into the card body with body-only
        fragments must not nest data-dz-region or re-mint bare region ids.
        """
        slot = (
            '<div id="region-device_attention-card-0" '
            'data-dz-region data-dz-region-name="device_attention">'
            "<span>skeleton</span></div>"
        )
        body1 = '<div class="dz-queue-region"><span>row-a</span></div>'
        body2 = '<div class="dz-queue-region"><span>row-b</span></div>'
        after1 = apply_inner_swap(slot, "region-device_attention-card-0", body1)
        after2 = apply_inner_swap(after1, "region-device_attention-card-0", body2)
        assert "row-b" in after2
        # Count attribute token data-dz-region (not data-dz-region-name).
        hooks = re.findall(r"(?<![\w-])data-dz-region(?![\w-])", after2)
        assert len(hooks) == 1
        assert 'id="region-device_attention"' not in after2
        assert after2.count('id="region-device_attention-card-0"') == 1

    def test_poll_targeting_bare_id_rewrapping_nests_region_hooks(self) -> None:
        """The pre-fix antipattern: first response re-wraps chrome with bare
        id; subsequent polls target that bare id and nest wrappers.
        """
        slot = (
            '<div id="region-device_attention-card-0" '
            'data-dz-region data-dz-region-name="device_attention">'
            "<span>skeleton</span></div>"
        )
        rewrap = (
            '<div data-dz-region data-dz-region-name="device_attention" '
            'id="region-device_attention"><span>poll</span></div>'
        )
        after1 = apply_inner_swap(slot, "region-device_attention-card-0", rewrap)
        after2 = apply_inner_swap(after1, "region-device_attention", rewrap)
        hooks = re.findall(r"(?<![\w-])data-dz-region(?![\w-])", after2)
        assert len(hooks) >= 3
        assert after2.count('id="region-device_attention"') >= 2

    def test_composite_clean_shape_passes(self) -> None:
        # Same structure but with body-only region content (ADR-0054).
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        initial = (
            '<div data-card-id="card-0">'
            '<article class="dz-card">'
            "<h3>Grade Distribution</h3>"
            '<div class="px-4 pb-4" id="region-grade_distribution-card-0" '
            'data-dz-region data-dz-region-name="grade_distribution">'
            '<div class="animate-pulse">loading</div>'
            "</div></article></div>"
        )
        # Body-only fragment (slot owns data-dz-region / id)
        good_region_html = '<div class="dz-chart-body"><p>chart body</p></div>'
        composite = assemble_workspace_composite(
            initial, {("card-0", "grade_distribution"): good_region_html}
        )
        assert find_nested_chromes(composite) == []
        assert 'id="region-grade_distribution"' not in composite


class TestInheritedLoadTriggerGate:
    """#1802: under htmx 4 `implicitInheritance` a verb control with no trigger
    of its own inherits an ancestor's `load` / `every` / `revealed` /
    `intersect` and fires by itself. Every rendered slot that self-fetches
    must keep that trigger off the ancestors of what it swaps in — checked on
    the stitched (post-swap) DOM, with a confirm-gated verb button in the
    swapped content."""

    @staticmethod
    def _verb_button() -> str:
        from dazzle.render.fragment import URL, Button, FragmentRenderer, TargetSelector

        return FragmentRenderer().render(
            Button(
                label="Release class",
                variant="secondary",
                visibility="visible",
                hx_post=URL("/api/assessment-event/e1/release-class"),
                hx_target=TargetSelector("#release-result"),
                hx_swap="innerHTML",
                hx_confirm="Release every script?",
            )
        )

    def test_scanner_flags_a_verb_under_a_load_trigger(self) -> None:
        from dazzle.testing.ux.contract_checker import find_inherited_load_triggers

        pre_fix = (
            '<tbody hx-get="/api/rows" hx-trigger="load, dz-grid:refresh">'
            f'<tr><td id="peek-content-1">{self._verb_button()}</td></tr></tbody>'
        )
        found = find_inherited_load_triggers(pre_fix)
        assert len(found) == 1
        assert 'hx-post="/api/assessment-event/e1/release-class"' in found[0][1]

    def test_list_with_peek_panel(self) -> None:
        from dazzle.render.fragment import FragmentRenderer
        from dazzle.render.fragment.primitives import RowCapabilities, Table
        from dazzle.render.fragment.renderer._data_row import render_data_row
        from dazzle.testing.ux.contract_checker import find_inherited_load_triggers

        skeleton = FragmentRenderer().render(
            Table(
                columns=("Title",),
                rows=(),
                skeleton=True,
                tbody_id="dt-task-body",
                hx_endpoint="/api/task",
                refresh_interval=30,
            )
        )
        row = render_data_row(
            ({"key": "title", "type": "str"},),
            {"id": "t1", "title": "Sample"},
            RowCapabilities(drill=True, delete=True, update=True, peek="expand"),
            entity_name="Task",
            api_endpoint="/api/task",
            detail_url_template="/app/task/{id}",
        )
        html = apply_inner_swap(skeleton, "dt-task-body", row)
        html = apply_inner_swap(html, "peek-content-t1", self._verb_button())
        assert "Release class" in html
        assert "hx-disinherit" not in html
        assert find_inherited_load_triggers(html) == []

    def test_workspace_region_slots(self) -> None:
        from dazzle.page.runtime.dual_pane_master_detail import render_master_detail_shell
        from dazzle.render.fragment import URL, FragmentRenderer, LazyTabPanel
        from dazzle.render.fragment.primitives import DashboardCard, LazyTab
        from dazzle.testing.ux.contract_checker import find_inherited_load_triggers

        region = f'<div class="dz-queue-region">{self._verb_button()}</div>'
        r = FragmentRenderer()
        card_kwargs: tuple[dict[str, object], ...] = (
            {"eager": True},
            {"eager": False},
            {"eager": True, "refresh_interval": 30},
            {"ssr_html": "<p>first paint</p>", "refresh_interval": 30},
        )
        slots: list[tuple[str, str]] = []
        for i, kw in enumerate(card_kwargs):
            card = DashboardCard(
                card_id=f"card-{i}",
                name="queue",
                title="Queue",
                display="queue",
                col_span=6,
                row_order=i,
                hx_endpoint="/api/workspaces/w/regions/queue",
                **kw,  # type: ignore[arg-type]
            )
            slots.append((r.render(card), f"region-queue-card-{i}"))
        tabs_html = r.render(
            LazyTabPanel(
                region_name="related",
                tabs=(
                    LazyTab(key="a", label="A", endpoint=URL("/api/a"), eager=True),
                    LazyTab(key="b", label="B", endpoint=URL("/api/b")),
                ),
            )
        )
        slots += [(tabs_html, "tab-related-a"), (tabs_html, "tab-related-b")]
        shell = render_master_detail_shell(
            list_region="queue",
            list_title="Queue",
            list_endpoint="/api/workspaces/w/regions/queue",
            detail_region="detail",
            detail_title="Detail",
            detail_endpoint_base="/api/workspaces/w/regions/detail",
        )
        slots.append((shell, "region-queue-card-list"))
        for initial, slot_id in slots:
            html = apply_inner_swap(initial, slot_id, region)
            assert "Release class" in html, slot_id
            assert find_inherited_load_triggers(html) == [], slot_id
