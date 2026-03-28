"""Tests for UX contract data models."""

from __future__ import annotations

from dazzle.testing.ux.contracts import (
    ContractKind,
    CreateFormContract,
    ListPageContract,
    RBACContract,
    WorkspaceContract,
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
