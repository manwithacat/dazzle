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


def test_workspace_contract_id_includes_persona_and_expected_present() -> None:
    """Regression for #835 — contract identity now keys on (workspace, persona,
    expected_present) so the generator can emit one row per (workspace, persona)
    pair without collisions."""
    base = WorkspaceContract(workspace="my_work", regions=["tasks"], fold_count=0)
    admin_allowed = WorkspaceContract(
        workspace="my_work", regions=["tasks"], fold_count=0, persona="admin", expected_present=True
    )
    admin_denied = WorkspaceContract(
        workspace="my_work",
        regions=["tasks"],
        fold_count=0,
        persona="admin",
        expected_present=False,
    )
    member_allowed = WorkspaceContract(
        workspace="my_work",
        regions=["tasks"],
        fold_count=0,
        persona="member",
        expected_present=True,
    )
    # Persona differentiates:
    assert admin_allowed.contract_id != member_allowed.contract_id
    # expected_present differentiates:
    assert admin_allowed.contract_id != admin_denied.contract_id
    # The legacy persona-less shape is also distinct from the new per-persona shape.
    assert base.contract_id != admin_allowed.contract_id


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

    def test_workspace_contracts_fan_out_by_persona(self) -> None:
        """Regression for #835 — the generator emits one WorkspaceContract per
        (workspace, persona) pair with expected_present derived from
        ``workspace_allowed_personas``. Before this fix the generator emitted
        one contract per workspace with no persona field, producing spurious
        403 failures whenever the admin driver hit a persona-scoped
        workspace (EX-026)."""
        contracts = generate_contracts(self.appspec)
        workspaces = [c for c in contracts if c.kind == ContractKind.WORKSPACE]

        # Every contract carries a persona.
        assert all(c.persona for c in workspaces), (
            "WorkspaceContract.persona must be populated after #835"
        )

        # simple_task's admin_dashboard declares `access: persona(admin)`.
        # Admin must be expected to access it; non-admin personas must be
        # expected to 403.
        admin_only = [c for c in workspaces if c.workspace == "admin_dashboard"]
        assert admin_only, "fixture missing — expected an admin_dashboard workspace"
        by_persona = {c.persona: c.expected_present for c in admin_only}
        assert by_persona.get("admin") is True, "admin must be expected to access admin_dashboard"
        non_admin = [pid for pid, present in by_persona.items() if pid != "admin"]
        assert non_admin, "expected non-admin personas in the fan-out"
        for pid in non_admin:
            assert by_persona[pid] is False, (
                f"persona {pid} should not be expected to access admin_dashboard — "
                f"got expected_present=True"
            )

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
