"""Tests for UX contract data models."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.testing.ux.contracts import (
    ContractKind,
    CreateFormContract,
    ListPageContract,
    RBACContract,
    WorkspaceContract,
    generate_contracts,
)


def test_list_page_contract_id_is_deterministic() -> None:
    c1 = ListPageContract(entity="Task", surface="task_list", fields=["title", "completed"])
    c2 = ListPageContract(entity="Task", surface="task_list", fields=["title", "completed"])
    assert len(c1.contract_id) == 12
    assert c1.contract_id == c2.contract_id


def test_list_page_contract_kind() -> None:
    c = ListPageContract(entity="Task", surface="task_list", fields=["title"])
    assert c.kind == ContractKind.LIST_PAGE


def test_rbac_contract_id_includes_persona() -> None:
    c1 = RBACContract(entity="Task", persona="admin", operation="read", expected_present=True)
    c2 = RBACContract(entity="Task", persona="viewer", operation="read", expected_present=False)
    assert c1.contract_id != c2.contract_id


def test_create_form_contract() -> None:
    c = CreateFormContract(
        entity="Task", required_fields=["title"], all_fields=["title", "completed"]
    )
    assert c.kind == ContractKind.CREATE_FORM
    assert c.url_path == "/app/task/create"


def test_workspace_contract() -> None:
    c = WorkspaceContract(workspace="task_board", regions=["main", "sidebar"], fold_count=2)
    assert c.kind == ContractKind.WORKSPACE
    assert c.url_path == "/app/workspaces/task_board"


class TestContractGeneration:
    def setup_method(self) -> None:
        self.appspec = load_project_appspec(Path("examples/simple_task").resolve())

    def test_generates_list_page_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        list_pages = [c for c in contracts if c.kind == ContractKind.LIST_PAGE]
        assert len(list_pages) >= 2
        task_list = next(c for c in list_pages if c.entity == "Task")
        assert "title" in task_list.fields

    def test_generates_create_form_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        create_forms = [c for c in contracts if c.kind == ContractKind.CREATE_FORM]
        entity_names = {c.entity for c in create_forms}
        assert "Task" in entity_names
        assert len(entity_names) == len(create_forms)  # No duplicates

    def test_generates_detail_view_with_transitions(self) -> None:
        contracts = generate_contracts(self.appspec)
        detail = next(
            c for c in contracts if c.kind == ContractKind.DETAIL_VIEW and c.entity == "Task"
        )
        assert len(detail.transitions) > 0
        assert detail.has_delete is True

    def test_generates_workspace_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        workspaces = [c for c in contracts if c.kind == ContractKind.WORKSPACE]
        ws_names = {c.workspace for c in workspaces}
        assert "task_board" in ws_names

    def test_generates_rbac_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        rbac = [c for c in contracts if c.kind == ContractKind.RBAC]
        permitted = [c for c in rbac if c.expected_present]
        forbidden = [c for c in rbac if not c.expected_present]
        assert len(permitted) > 0
        assert len(forbidden) > 0

    def test_no_framework_entities_in_contracts(self) -> None:
        contracts = generate_contracts(self.appspec)
        entities = {c.entity for c in contracts if hasattr(c, "entity") and c.entity}
        assert "AIJob" not in entities
        assert "SystemHealth" not in entities
