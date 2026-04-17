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
