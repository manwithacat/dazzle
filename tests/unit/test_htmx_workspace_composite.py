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
