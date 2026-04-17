"""Tests for contract checker — HTML assertion engine."""

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
    <div data-dz-region-name="tasks" class="rounded-md border bg-white">
      <article class="rounded-md border bg-gray-50">
        <h3>Card</h3>
      </article>
    </div>
    """

    _FLAT_CARD_HTML = """
    <div data-dz-region-name="tasks">
      <article class="rounded-md border bg-white">
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
            SAMPLE_LIST_HTML
            + '<div class="rounded-md border"><div class="rounded-md bg-white">nested</div></div>'
        )
        result = check_contract(contract, nested_list_html)
        # List contract is still satisfied even with a stray nested-chrome
        # pattern below it — the gate doesn't apply to this contract type.
        assert result.status == "passed", result.error


class TestFindNestedChromes:
    """Direct tests of the nested-chrome scanner helper."""

    def test_detects_rounded_plus_border_nested(self) -> None:
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = '<div class="rounded-md border"><article class="rounded-lg bg-blue-50">inner</article></div>'
        assert find_nested_chromes(html) == [("div", "article")]

    def test_ignores_rounded_without_surface(self) -> None:
        # rounded-md alone is not "chrome" — must also have border or bg.
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<div class="rounded-md"><article class="rounded-md border bg-white">x</article></div>'
        )
        assert find_nested_chromes(html) == []

    def test_ignores_siblings(self) -> None:
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<section class="rounded-md border"><p>a</p></section>'
            '<section class="rounded-md bg-white"><p>b</p></section>'
        )
        assert find_nested_chromes(html) == []

    def test_reports_one_pair_per_inner_chrome(self) -> None:
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<section class="rounded-md border">'
            '<div class="rounded-md bg-white">a</div>'
            '<div class="rounded-md border">b</div>'
            "</section>"
        )
        # Two inner chromes under one outer chrome = 2 pairs.
        result = find_nested_chromes(html)
        assert len(result) == 2
        assert all(outer == "section" for outer, _ in result)

    def test_accepts_arbitrary_value_rounded(self) -> None:
        # Regression for the #794 follow-up: Dazzle's own templates use
        # arbitrary-value rounded classes like `rounded-[4px]` and
        # `rounded-[6px]` (region_card macro + grid.html). The initial
        # fix missed this because it only recognised fixed-scale
        # `rounded-md` / `rounded-lg` / etc.
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<div class="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-[6px]">'
            '<div class="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-[4px]">'
            "item</div></div>"
        )
        assert find_nested_chromes(html) == [("div", "div")]

    def test_side_border_is_not_chrome(self) -> None:
        # A left-side accent border (used for attention states) is an
        # accent stripe, not a card edge — must not trigger nesting
        # detection against an outer chrome.
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<div class="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-[6px]">'
            '<div class="rounded-[4px] p-3 border-l-4 border-l-[hsl(var(--primary))]">'
            "item</div></div>"
        )
        assert find_nested_chromes(html) == []

    def test_fixed_grid_region_shape(self) -> None:
        # The shape that grid.html renders AFTER the #794-followup fix:
        # region_card outer is chrome, inner items are plain pads. No
        # nesting. This is the reference model that QA should validate.
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        html = (
            '<div data-dz-region data-dz-region-name="system_status" '
            'class="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-[6px]">'
            '<div class="p-3">'
            "<h3>System Status</h3>"
            '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">'
            '<div class="rounded-[4px] p-3 cursor-pointer hover:bg-[hsl(var(--muted)/0.4)]">'
            "<h4>api-gateway</h4></div>"
            '<div class="rounded-[4px] p-3 cursor-pointer hover:bg-[hsl(var(--muted)/0.4)]">'
            "<h4>auth-service</h4></div>"
            "</div></div></div>"
        )
        assert find_nested_chromes(html) == []
