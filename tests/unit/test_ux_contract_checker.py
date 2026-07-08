"""Tests for contract checker — HTML assertion engine."""

import pytest

from dazzle.testing.ux.contract_checker import check_contract
from dazzle.testing.ux.contracts import (
    CreateFormContract,
    DetailViewContract,
    ListPageContract,
    RBACContract,
    WorkspaceContract,
)

SAMPLE_LIST_HTML = """
<table data-dazzle-table="Task">
  <thead><tr>
    <th data-dz-col="title"><a hx-get="/tasks?sort=title">Title</a></th>
    <th data-dz-col="status">Status</th>
  </tr></thead>
  <tbody>
    <tr hx-get="/app/task/abc123" hx-target="body">
      <td data-dz-col="title">Test</td>
      <td data-dz-col="status">todo</td>
    </tr>
  </tbody>
</table>
<a href="/app/task/create">+ New Task</a>
<input hx-get="/tasks" hx-trigger="keyup changed delay:300ms" />
"""

SAMPLE_FORM_HTML = """
<form hx-post="/tasks">
  <input name="title" type="text" required />
  <textarea name="description"></textarea>
  <button type="submit">Create</button>
</form>
"""

SAMPLE_DETAIL_HTML = """
<h2>Task Detail</h2>
<div data-dazzle-entity="Task">
  <span data-dazzle-field="title">Test</span>
  <span data-dazzle-field="status">todo</span>
</div>
<a href="/app/task/abc123/edit">Edit</a>
<button hx-delete="/tasks/abc123" hx-confirm="Delete?">Delete</button>
<button hx-put="/tasks/abc123" hx-vals='{"status":"in_progress"}'>Start</button>
"""

SAMPLE_WORKSPACE_HTML = """
<div data-dz-region-name="tasks" hx-get="/api/workspaces/task_board/regions/tasks" hx-trigger="load"></div>
<div data-dz-region-name="comments" hx-get="/api/workspaces/task_board/regions/comments" hx-trigger="intersect once"></div>
<aside id="dz-detail-drawer"></aside>
"""


class TestCheckListPage:
    def test_passes_valid_list_page(self) -> None:
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title", "status"])
        result = check_contract(contract, SAMPLE_LIST_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_table(self) -> None:
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title"])
        result = check_contract(contract, "<div>No table here</div>")
        assert result.status == "failed"
        assert "data-dazzle-table" in result.error

    def test_passes_without_create_link(self) -> None:
        """Create link is persona-dependent — verified by RBAC contracts, not list page."""
        html = (
            '<table data-dazzle-table="Task"><tbody><tr hx-get="/app/task/1"></tr></tbody></table>'
        )
        contract = ListPageContract(entity="Task", surface="task_list", fields=[])
        result = check_contract(contract, html)
        assert result.status == "passed", result.error


class TestCheckCreateForm:
    def test_passes_valid_form(self) -> None:
        contract = CreateFormContract(
            entity="Task", required_fields=["title"], all_fields=["title", "description"]
        )
        result = check_contract(contract, SAMPLE_FORM_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_required_field(self) -> None:
        contract = CreateFormContract(
            entity="Task", required_fields=["title", "priority"], all_fields=["title", "priority"]
        )
        result = check_contract(contract, SAMPLE_FORM_HTML)
        assert result.status == "failed"
        assert "priority" in result.error


class TestCheckDetailView:
    def test_passes_valid_detail(self) -> None:
        contract = DetailViewContract(
            entity="Task",
            fields=["title", "status"],
            has_edit=True,
            has_delete=True,
            transitions=["todo\u2192in_progress"],
        )
        result = check_contract(contract, SAMPLE_DETAIL_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_delete_button(self) -> None:
        html = "<h2>Detail</h2><div data-dazzle-entity='Task'></div>"
        contract = DetailViewContract(
            entity="Task", fields=[], has_edit=False, has_delete=True, transitions=[]
        )
        result = check_contract(contract, html)
        assert result.status == "failed"
        assert "delete" in result.error.lower()


class TestCheckWorkspace:
    def test_passes_valid_workspace(self) -> None:
        contract = WorkspaceContract(
            workspace="task_board", regions=["tasks", "comments"], fold_count=1
        )
        result = check_contract(contract, SAMPLE_WORKSPACE_HTML)
        assert result.status == "passed", result.error

    def test_fails_missing_region(self) -> None:
        contract = WorkspaceContract(
            workspace="task_board", regions=["tasks", "missing_region"], fold_count=2
        )
        result = check_contract(contract, SAMPLE_WORKSPACE_HTML)
        assert result.status == "failed"
        assert "missing_region" in result.error

    def test_passes_dashboard_with_regions_only_in_layout_json(self) -> None:
        """Regression test for #803: dashboard workspaces emit their
        region wrappers client-side via Alpine's `<template x-for>`, so
        the SSR HTML has no `data-dz-region-name` attrs — but the
        `dz-workspace-layout` JSON data island declares them. Treat
        that JSON as satisfying the contract."""
        dashboard_html = """
        <div class="p-4" x-data="dzDashboardBuilder()">
          <script type="application/json" id="dz-workspace-layout">
            {"cards": [
              {"id": "card-0", "region": "grade_distribution", "col_span": 6},
              {"id": "card-1", "region": "class_performance", "col_span": 6},
              {"id": "card-2", "region": "marking_pipeline", "col_span": 12}
            ], "catalog": [], "workspace_name": "teacher_workspace"}
          </script>
          <template x-for="card in cards"><div :data-card-id="card.id"></div></template>
        </div>
        """
        contract = WorkspaceContract(
            workspace="teacher_workspace",
            regions=["grade_distribution", "class_performance", "marking_pipeline"],
            fold_count=3,
        )
        result = check_contract(contract, dashboard_html)
        assert result.status == "passed", result.error

    def test_fails_dashboard_missing_region_in_layout_json(self) -> None:
        """If a region is declared by the contract but the layout JSON
        doesn't mention it (and no `data-dz-region-name` attr exists),
        the contract must still fail — that's a real regression."""
        dashboard_html = """
        <div class="p-4" x-data="dzDashboardBuilder()">
          <script type="application/json" id="dz-workspace-layout">
            {"cards": [{"id": "card-0", "region": "only_one", "col_span": 6}],
             "catalog": [], "workspace_name": "ws"}
          </script>
        </div>
        """
        contract = WorkspaceContract(
            workspace="ws", regions=["only_one", "not_declared"], fold_count=2
        )
        result = check_contract(contract, dashboard_html)
        assert result.status == "failed"
        assert "not_declared" in result.error


class TestCheckRBAC:
    def test_passes_when_expected_present_and_found(self) -> None:
        contract = RBACContract(
            entity="Task", persona="admin", operation="delete", expected_present=True
        )
        result = check_contract(contract, SAMPLE_DETAIL_HTML)
        assert result.status == "passed"

    def test_fails_when_expected_present_but_missing(self) -> None:
        contract = RBACContract(
            entity="Task", persona="admin", operation="delete", expected_present=True
        )
        result = check_contract(contract, "<h2>Detail</h2>")
        assert result.status == "failed"

    def test_passes_when_expected_absent_and_missing(self) -> None:
        contract = RBACContract(
            entity="Task", persona="member", operation="delete", expected_present=False
        )
        result = check_contract(contract, "<h2>Detail</h2><a href='/app/task/1/edit'>Edit</a>")
        assert result.status == "passed"

    def test_fails_when_expected_absent_but_found(self) -> None:
        contract = RBACContract(
            entity="Task", persona="member", operation="delete", expected_present=False
        )
        result = check_contract(contract, SAMPLE_DETAIL_HTML)
        assert result.status == "failed"


# ---------------------------------------------------------------------------
# Shape-nesting gate (issue #794)
# ---------------------------------------------------------------------------


class TestNestedCardChrome:
    """The shape-nesting gate flags card-within-a-card layouts on workspace
    and detail contracts — a chrome layer (rounded + border/bg) nested
    inside another chrome layer."""

    _NESTED_CARD_HTML = """
    <div data-dz-region-name="tasks" class="dz-card">
      <article class="dz-card">
        <h3>Card</h3>
      </article>
    </div>
    """

    _FLAT_CARD_HTML = """
    <div data-dz-region-name="tasks">
      <article class="dz-card">
        <h3>Card</h3>
      </article>
    </div>
    """

    def test_workspace_contract_fails_on_nested_chrome(self) -> None:
        contract = WorkspaceContract(workspace="task_board", regions=["tasks"])
        result = check_contract(contract, self._NESTED_CARD_HTML)
        assert result.status == "failed"
        assert result.error is not None
        assert "Nested card chrome" in result.error

    def test_workspace_contract_passes_on_flat_chrome(self) -> None:
        contract = WorkspaceContract(workspace="task_board", regions=["tasks"])
        result = check_contract(contract, self._FLAT_CARD_HTML)
        assert result.status == "passed", result.error

    def test_list_contract_does_not_run_nesting_check(self) -> None:
        # List contracts show tables, not cards — the nesting gate is
        # scoped to Workspace/DetailView contracts.
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title"])
        nested_list_html = (
            SAMPLE_LIST_HTML + '<div class="dz-card"><div class="dz-card">nested</div></div>'
        )
        result = check_contract(contract, nested_list_html)
        # List contract is still satisfied even with a stray nested-chrome
        # pattern below it — the gate doesn't apply to this contract type.
        assert result.status == "passed", result.error


class TestFindNestedChromes:
    """Direct tests of the nested-chrome scanner helper."""

    # Card chrome is the exact `dz-card` token (ADR-0049 substrate). The legacy
    # Tailwind rounded+border heuristic was retired in HMC-002b (every card surface
    # the framework emits is semantic `dz-card`; 0 emitters/fixtures produce Tailwind
    # card chrome), so these cases use the production vocabulary. The primary
    # Card-in-Card guarantee is structural (containers.py Card.__post_init__); this
    # scanner is defence-in-depth for raw-HTML region bodies that bypass it.
    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            # Nested dz-card surfaces → detected pair.
            (
                '<div class="dz-card"><article class="dz-card">inner</article></div>',
                [("div", "article")],
            ),
            # dz-card-wrapper is the positioner, NOT a surface; sub-parts
            # (dz-card-header/-body) are not surfaces either — single chrome layer.
            (
                '<div data-card-id="c0" class="dz-card-wrapper is-animating" tabindex="0">'
                '<article class="dz-card" role="article">'
                '<div class="dz-card-header"><h3 class="dz-card-title">Total Tasks</h3></div>'
                '<div class="dz-card-body" id="region-metrics-c0">'
                '<div data-dz-region data-dz-region-name="metrics"><p>5</p></div>'
                "</div></article></div>",
                [],
            ),
            # Sibling dz-card surfaces are not nested — not flagged.
            (
                '<section class="dz-card"><p>a</p></section>'
                '<section class="dz-card"><p>b</p></section>',
                [],
            ),
            # Dashboard slot article.dz-card > bare region body — single chrome layer.
            (
                '<div data-card-id="card-0" class="dz-card-wrapper">'
                '<article class="dz-card">'
                '<h3 id="card-title-card-0">Grade Distribution</h3>'
                '<div class="dz-card-body">'
                '<div data-dz-region data-dz-region-name="grade_distribution" '
                'id="region-grade_distribution">'
                "<p>chart body goes here</p>"
                "</div></div></article></div>",
                [],
            ),
            # The #794 regression on the raw-HTML bypass path: a region body emits its
            # OWN dz-card surface inside the dashboard slot's article.dz-card → nested.
            (
                '<div data-card-id="c0" class="dz-card-wrapper" tabindex="0">'
                '<article class="dz-card">'
                '<div class="dz-card-body" id="region-metrics-c0">'
                '<div class="dz-card dz-card--border-md"><h3>Total Tasks</h3><p>chart</p></div>'
                "</div></article></div>",
                [("article", "div")],
            ),
            # Standalone Card primitive: dz-card surface with dz-card__body sub-part
            # (a BEM element, NOT a second surface) → single chrome layer, clean.
            (
                '<div class="dz-card dz-card--radius-md dz-card--border-md">'
                '<div class="dz-card__header"><h3>Title</h3></div>'
                '<div class="dz-card__body"><p>body</p></div>'
                "</div>",
                [],
            ),
        ],
        ids=[
            "test_detects_nested_dz_card",
            "test_wrapper_and_subparts_are_not_chrome",
            "test_ignores_siblings",
            "test_dashboard_slot_with_bare_region_is_clean",
            "test_region_emitting_own_dz_card_is_nested",
            "test_standalone_card_bem_subparts_are_clean",
        ],
    )
    def test_find_nested_chromes(self, html: str, expected: list) -> None:
        """find_nested_chromes() detects card-within-card chrome nesting."""
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        assert find_nested_chromes(html) == expected

    def test_reports_one_pair_per_inner_chrome(self) -> None:
        # Two inner chromes under one outer chrome = 2 pairs.
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<section class="dz-card">'
            '<div class="dz-card">a</div>'
            '<div class="dz-card">b</div>'
            "</section>"
        )
        result = find_nested_chromes(html)
        assert len(result) == 2
        assert all(outer == "section" for outer, _ in result)


class TestFindDuplicateTitlesInCards:
    """Gate on AegisMark's #794 second counter:
    ``page.get_by_text("Grade Distribution").count() → 3``.

    A card with the same heading text more than once = the header
    is printed twice (once from the dashboard slot, again from the
    region partial). Scanner catches the pair before the composite
    shape gate even looks at chrome.
    """

    def test_detects_duplicate_title_in_nested_cards(self) -> None:
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        html = (
            '<div data-card-id="card-0">'
            '<article class="dz-card">'
            "<h3>Grade Distribution</h3>"
            '<div class="dz-card">'
            "<h3>Grade Distribution</h3>"
            "</div></article></div>"
        )
        dupes = find_duplicate_titles_in_cards(html)
        assert dupes, "scanner missed the duplicate title"
        assert all(t == "Grade Distribution" for _, t in dupes)

    def test_single_title_per_card_is_clean(self) -> None:
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        html = (
            '<div data-card-id="card-0">'
            '<article class="dz-card">'
            "<h3>Grade Distribution</h3>"
            "<p>content</p>"
            "</article></div>"
        )
        assert find_duplicate_titles_in_cards(html) == []

    def test_sibling_cards_with_same_title_are_independent(self) -> None:
        # Two distinct cards each naming themselves "Alerts" is valid
        # (a dashboard with multiple alert regions). Only duplicates
        # *within* the same card should flag.
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        html = (
            '<article class="dz-card"><h3>Alerts</h3></article>'
            '<article class="dz-card"><h3>Alerts</h3></article>'
        )
        assert find_duplicate_titles_in_cards(html) == []

    def test_whitespace_and_casing_normalised(self) -> None:
        # `<h3>\n  Grade Distribution  </h3>` must match
        # `<h3>Grade Distribution</h3>` — the AegisMark counter is
        # page.get_by_text which already normalises whitespace.
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        html = (
            '<article class="dz-card">'
            "<h3>Grade Distribution</h3>"
            "<h3>\n  Grade Distribution  </h3>"
            "</article>"
        )
        dupes = find_duplicate_titles_in_cards(html)
        assert dupes == [("article", "Grade Distribution")]

    def test_different_titles_in_same_card_are_fine(self) -> None:
        # A card might legitimately contain multiple headings (section
        # labels, sub-group names). Only *repeated* text should flag.
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        html = '<article class="dz-card"><h3>Summary</h3><h4>Details</h4><h4>Metrics</h4></article>'
        assert find_duplicate_titles_in_cards(html) == []

    def test_dashboard_slot_plus_region_with_duplicate_title(self) -> None:
        # Exact shape AegisMark reported — dashboard card header
        # renders the title and the region partial (pre-#794-followup
        # region_card macro) renders it again inside.
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        before_fix_html = (
            '<div data-card-id="card-0">'
            '<article class="dz-card">'
            '<h3 id="card-title-card-0">Grade Distribution</h3>'
            "<div>"
            '<div data-dz-region class="dz-card">'
            "<h3>Grade Distribution</h3><p>chart</p>"
            "</div></div></article></div>"
        )
        dupes = find_duplicate_titles_in_cards(before_fix_html)
        assert dupes, "must catch the dashboard + region title duplicate"
        assert any(t == "Grade Distribution" for _, t in dupes)

    def test_bare_region_card_does_not_duplicate(self) -> None:
        # Post-#794-followup: region_card emits no heading, so the
        # dashboard slot's title is the only one in the composite.
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        after_fix_html = (
            '<div data-card-id="card-0">'
            '<article class="dz-card">'
            '<h3 id="card-title-card-0">Grade Distribution</h3>'
            "<div>"
            '<div data-dz-region id="region-grade_distribution">'
            "<p>chart body</p>"
            "</div></div></article></div>"
        )
        assert find_duplicate_titles_in_cards(after_fix_html) == []


class TestFindHiddenPrimaryActions:
    """Gate on issue #801 / #799: primary actions (Remove/Delete/…)
    whose only visibility path is pointer hover are inaccessible on
    touch and hard to discover with a keyboard. Scanner flags them.
    """

    def test_opacity_zero_hover_only_is_flagged(self) -> None:
        from dazzle.testing.ux.contract_checker import find_hidden_primary_actions

        html = (
            '<div class="opacity-0 group-hover:opacity-100">'
            '<button aria-label="Remove card">x</button>'
            "</div>"
        )
        hidden = find_hidden_primary_actions(html)
        assert len(hidden) == 1
        assert hidden[0][0] == "Remove card"
        assert "hover" in hidden[0][1]

    @pytest.mark.parametrize(
        "html",
        [
            (
                '<div class="opacity-0 group-hover:opacity-100 focus-within:opacity-100">'
                '<button aria-label="Remove card">x</button>'
                "</div>"
            ),
            '<div><button aria-label="Delete item">x</button></div>',
            (
                '<div x-show="open" class="opacity-0"><button aria-label="Close panel">x</button></div>'
            ),
            (
                '<div class="opacity-0 group-hover:opacity-100">'
                '<button aria-label="Submit form">ok</button>'
                "</div>"
            ),
            '<div class="opacity-0 group-hover:opacity-100"><button>x</button></div>',
            (
                '<div class="opacity-60 group-hover:opacity-100 group-focus-within:opacity-100">'
                '<button aria-label="Remove card">x</button>'
                "</div>"
            ),
        ],
        ids=[
            "test_focus_within_reveal_not_flagged",
            "test_always_visible_not_flagged",
            "test_alpine_modal_not_flagged",
            "test_non_primary_action_not_flagged",
            "test_button_without_aria_label_not_flagged",
            "test_post_799_fix_shape_passes",
        ],
    )
    def test_not_flagged(self, html: str) -> None:
        from dazzle.testing.ux.contract_checker import find_hidden_primary_actions

        assert find_hidden_primary_actions(html) == []

    def test_link_button_role_matches(self) -> None:
        # An <a role="button"> that behaves as a button must be
        # treated the same as a <button>.
        from dazzle.testing.ux.contract_checker import find_hidden_primary_actions

        html = (
            '<div class="opacity-0 group-hover:opacity-100">'
            '<a role="button" aria-label="Delete entry">x</a>'
            "</div>"
        )
        hidden = find_hidden_primary_actions(html)
        assert len(hidden) == 1
        assert hidden[0][0] == "Delete entry"

    def test_opacity_zero_on_button_itself(self) -> None:
        # The button carries opacity-0 directly — same class of problem.
        from dazzle.testing.ux.contract_checker import find_hidden_primary_actions

        html = (
            '<button class="opacity-0 group-hover:opacity-100" aria-label="Remove card">x</button>'
        )
        hidden = find_hidden_primary_actions(html)
        assert len(hidden) == 1
        assert "button itself" in hidden[0][1]

    def test_multiple_hidden_actions_all_reported(self) -> None:
        from dazzle.testing.ux.contract_checker import find_hidden_primary_actions

        html = (
            '<div class="opacity-0 group-hover:opacity-100">'
            '<button aria-label="Remove one">a</button>'
            '<button aria-label="Delete two">b</button>'
            '<button aria-label="Archive three">c</button>'
            "</div>"
        )
        hidden = find_hidden_primary_actions(html)
        assert len(hidden) == 3
        labels = {h[0] for h in hidden}
        assert labels == {"Remove one", "Delete two", "Archive three"}


class TestRBACEntityScoping:
    """#1292: create/edit href matching must be scoped to the contract's
    entity, so a cross-entity create link no longer satisfies (false-positive)
    a different entity's RBAC contract."""

    def test_href_helper_scopes_to_entity(self) -> None:
        from dazzle.testing.ux.contract_checker import _href_targets_entity_op

        # Correct entity, both route shapes.
        assert _href_targets_entity_op("/app/system/create", "System", "create")
        assert _href_targets_entity_op("/system_create", "System", "create")
        assert _href_targets_entity_op("/app/system/123/edit", "System", "edit")
        # Cross-entity create must NOT match a System contract.
        assert not _href_targets_entity_op("/app/alert/create", "System", "create")
        # Entity-name prefix collision must NOT match (systemhealth vs system).
        assert not _href_targets_entity_op("/app/systemhealth/create", "System", "create")
        # Right entity, wrong verb.
        assert not _href_targets_entity_op("/app/system/123/edit", "System", "create")

    def test_cross_entity_create_link_does_not_satisfy_contract(self) -> None:
        contract = RBACContract(
            entity="System", persona="ops_engineer", operation="create", expected_present=True
        )
        html = '<a href="/app/alert/create">New Alert</a>'  # different entity
        result = check_contract(contract, html)
        assert result.status == "failed"

    def test_same_entity_create_link_satisfies_contract(self) -> None:
        contract = RBACContract(
            entity="System", persona="admin", operation="create", expected_present=True
        )
        html = '<a href="/app/system/create">Register System</a>'
        result = check_contract(contract, html)
        assert result.status == "passed", result.error
