"""Tests for the UX reconciliation engine.

TDD tests — written before implementation.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.triples import ActionTriple, SurfaceFieldTriple, VerifiableTriple, WidgetKind
from dazzle.testing.ux.contracts import (
    CreateFormContract,
    DetailViewContract,
    EditFormContract,
    ListPageContract,
    RBACContract,
)
from dazzle.testing.ux.reconciler import (
    Diagnosis,
    DiagnosisKind,
    DSLLever,
    reconcile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_action(action: str, permission: str = "read") -> ActionTriple:
    return ActionTriple(action=action, permission=permission)


def _make_triple(
    entity: str = "Task",
    surface: str = "task_list",
    persona: str = "admin",
    mode: str = "list",
    actions: list[str] | None = None,
    fields: list[SurfaceFieldTriple] | None = None,
) -> VerifiableTriple:
    action_strs = actions or ["list"]
    return VerifiableTriple(
        entity=entity,
        surface=surface,
        persona=persona,
        surface_mode=mode,
        actions=[_make_action(a) for a in action_strs],
        fields=fields or [],
    )


def _make_field(name: str = "title", required: bool = False) -> SurfaceFieldTriple:
    return SurfaceFieldTriple(
        field_name=name,
        widget=WidgetKind.TEXT_INPUT,
        is_required=required,
        is_fk=False,
        ref_entity=None,
    )


# ---------------------------------------------------------------------------
# TestReconcileNoTriple
# ---------------------------------------------------------------------------


class TestReconcileNoTriple:
    """When triple is None the reconciler should diagnose a permission gap."""

    def test_no_triple_means_permission_gap(self) -> None:
        contract = RBACContract(
            entity="Task", persona="viewer", operation="delete", expected_present=True
        )
        contract.status = "failed"
        contract.error = "Expected delete but not found"

        diag = reconcile(
            contract=contract,
            triple=None,
            html="<div>no delete here</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.PERMISSION_GAP
        assert diag.contract_id == contract.contract_id
        assert "Task" in diag.triple
        assert len(diag.levers) >= 1
        assert "permit" in diag.levers[0].construct

    def test_no_triple_lever_targets_entity_access(self) -> None:
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title"])
        contract.status = "failed"
        contract.error = "Page not accessible"

        diag = reconcile(
            contract=contract,
            triple=None,
            html="<div>403</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.PERMISSION_GAP
        assert any("permit" in lv.construct for lv in diag.levers)


# ---------------------------------------------------------------------------
# TestReconcileActionMissing
# ---------------------------------------------------------------------------


class TestReconcileActionMissing:
    """RBAC contracts that expect an action present but find it absent."""

    def test_edit_link_missing_from_html(self) -> None:
        contract = RBACContract(
            entity="Task", persona="admin", operation="update", expected_present=True
        )
        contract.status = "failed"
        contract.error = "Expected edit link but not found in DOM"

        triple = _make_triple(persona="admin", actions=["list", "edit_link"])

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<div><table><tr><td>Title</td></tr></table></div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_MISSING
        assert diag.contract_id == contract.contract_id
        assert len(diag.levers) >= 1
        assert "permit" in diag.levers[0].construct

    def test_delete_button_present_unexpectedly(self) -> None:
        contract = RBACContract(
            entity="Task", persona="viewer", operation="delete", expected_present=False
        )
        contract.status = "failed"
        contract.error = "Found delete button but should not be present"

        triple = _make_triple(entity="Task", persona="viewer", actions=["list"])

        diag = reconcile(
            contract=contract,
            triple=triple,
            html='<div><button class="delete">Delete</button></div>',
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_UNEXPECTED
        assert diag.contract_id == contract.contract_id
        assert len(diag.levers) >= 1
        assert "access" in diag.levers[0].construct


# ---------------------------------------------------------------------------
# TestReconcileDetailView
# ---------------------------------------------------------------------------


class TestReconcileDetailView:
    """DetailViewContract failures that map to action-related diagnoses."""

    def test_detail_edit_missing(self) -> None:
        contract = DetailViewContract(
            entity="Task", fields=["title"], has_edit=True, has_delete=False
        )
        contract.status = "failed"
        contract.error = "Expected edit link but not found"

        triple = _make_triple(surface="task_detail", mode="view", actions=["edit_link"])

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<div>Task detail</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_MISSING

    def test_detail_delete_missing(self) -> None:
        contract = DetailViewContract(
            entity="Task", fields=["title"], has_edit=False, has_delete=True
        )
        contract.status = "failed"
        contract.error = "Expected delete button but not found"

        triple = _make_triple(surface="task_detail", mode="view", actions=["delete_button"])

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<div>Task detail</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_MISSING

    def test_detail_transition_missing(self) -> None:
        contract = DetailViewContract(
            entity="Task",
            fields=["title"],
            has_edit=False,
            has_delete=False,
            transitions=["open→closed"],
        )
        contract.status = "failed"
        contract.error = "Expected transition button but not found"

        triple = _make_triple(
            surface="task_detail", mode="view", actions=["transition:open->closed"]
        )

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<div>Task detail</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_MISSING


# ---------------------------------------------------------------------------
# TestReconcileFieldMissing
# ---------------------------------------------------------------------------


class TestReconcileFieldMissing:
    """Form contracts where a field is missing."""

    def test_create_form_field_missing(self) -> None:
        contract = CreateFormContract(
            entity="Task",
            required_fields=["title"],
            all_fields=["title", "description"],
        )
        contract.status = "failed"
        contract.error = "Missing field: description"

        triple = _make_triple(
            surface="task_create",
            mode="create",
            actions=["create_submit"],
            fields=[_make_field("title", required=True), _make_field("description")],
        )

        diag = reconcile(
            contract=contract,
            triple=triple,
            html='<form><input name="title"></form>',
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.FIELD_MISSING
        assert len(diag.levers) >= 1
        assert "section" in diag.levers[0].construct or "element" in diag.levers[0].construct

    def test_edit_form_field_missing(self) -> None:
        contract = EditFormContract(
            entity="Task",
            editable_fields=["title", "status"],
        )
        contract.status = "failed"
        contract.error = "Missing field: status"

        triple = _make_triple(
            surface="task_edit",
            mode="edit",
            actions=["edit_submit"],
            fields=[_make_field("title"), _make_field("status")],
        )

        diag = reconcile(
            contract=contract,
            triple=triple,
            html='<form><input name="title"></form>',
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.FIELD_MISSING


# ---------------------------------------------------------------------------
# TestReconcileTemplateBug
# ---------------------------------------------------------------------------


class TestReconcileTemplateBug:
    """Fallback: triple and contract agree but HTML is wrong → TEMPLATE_BUG."""

    def test_triple_and_contract_agree_html_wrong(self) -> None:
        contract = ListPageContract(
            entity="Task", surface="task_list", fields=["title", "completed"]
        )
        contract.status = "failed"
        contract.error = "Table column 'completed' not found in DOM"

        triple = _make_triple(
            actions=["list"],
            fields=[_make_field("title"), _make_field("completed")],
        )

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<table><th>Title</th></table>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.TEMPLATE_BUG
        assert diag.levers == []
        assert diag.contract_id == contract.contract_id

    def test_template_bug_includes_observation(self) -> None:
        contract = ListPageContract(entity="Task", surface="task_list", fields=["title"])
        contract.status = "failed"
        contract.error = "Table missing"

        triple = _make_triple(actions=["list"], fields=[_make_field("title")])

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<div>empty</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.TEMPLATE_BUG
        assert diag.observation != ""


# ---------------------------------------------------------------------------
# TestDiagnosisModel
# ---------------------------------------------------------------------------


class TestDiagnosisModel:
    """Verify the Diagnosis data model properties."""

    def test_diagnosis_is_frozen(self) -> None:
        diag = Diagnosis(
            contract_id="abc123",
            kind=DiagnosisKind.TEMPLATE_BUG,
            triple="Task.task_list.admin",
            observation="Column missing",
            expectation="Column present",
        )
        with pytest.raises((TypeError, ValueError)):
            diag.kind = DiagnosisKind.ACTION_MISSING  # type: ignore[misc]

    def test_dsl_lever_is_frozen(self) -> None:
        lever = DSLLever(
            construct="entity.Task.access.permit",
            current_value="",
            suggested_value="permit update for viewer",
            explanation="Add permit rule",
        )
        with pytest.raises((TypeError, ValueError)):
            lever.construct = "other"  # type: ignore[misc]

    def test_diagnosis_category_defaults_empty(self) -> None:
        diag = Diagnosis(
            contract_id="abc",
            kind=DiagnosisKind.TEMPLATE_BUG,
            triple="X.Y.Z",
            observation="obs",
            expectation="exp",
        )
        assert diag.category == ""


# ---------------------------------------------------------------------------
# TestReconcilerDiagnosis — synthetic failure cases
# ---------------------------------------------------------------------------


class TestReconcilerDiagnosis:
    """Synthetic failure tests ensuring the reconciler maps contract failures
    to the correct DiagnosisKind with accurate levers."""

    def test_rbac_action_missing_diagnosis(self) -> None:
        """RBAC contract expects action present → ACTION_MISSING when absent from HTML."""
        contract = RBACContract(
            entity="Task", persona="admin", operation="create", expected_present=True
        )
        contract.status = "failed"
        contract.error = "Expected create action but not found in DOM"

        triple = _make_triple(
            entity="Task",
            surface="task_list",
            persona="admin",
            actions=["list", "create_link"],
        )

        diag = reconcile(
            contract=contract,
            triple=triple,
            html="<div><table><tr><td>Title</td></tr></table></div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_MISSING
        assert diag.contract_id == contract.contract_id
        assert "Task" in diag.triple
        assert any("permit" in lv.construct for lv in diag.levers)

    def test_rbac_action_unexpected_diagnosis(self) -> None:
        """RBAC contract expects action absent → ACTION_UNEXPECTED when found in HTML."""
        contract = RBACContract(
            entity="Task", persona="viewer", operation="delete", expected_present=False
        )
        contract.status = "failed"
        contract.error = "Found delete button but viewer should not see it"

        triple = _make_triple(entity="Task", persona="viewer", actions=["list"])

        diag = reconcile(
            contract=contract,
            triple=triple,
            html='<div><button class="delete">Delete</button></div>',
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.ACTION_UNEXPECTED
        assert diag.contract_id == contract.contract_id
        assert any("access" in lv.construct for lv in diag.levers)

    def test_field_missing_diagnosis(self) -> None:
        """CreateFormContract with a missing field → FIELD_MISSING."""
        contract = CreateFormContract(
            entity="Task",
            required_fields=["title", "description"],
            all_fields=["title", "description", "status"],
        )
        contract.status = "failed"
        contract.error = "Missing field: status"

        triple = _make_triple(
            entity="Task",
            surface="task_create",
            mode="create",
            actions=["create_submit"],
            fields=[
                _make_field("title", required=True),
                _make_field("description"),
                _make_field("status"),
            ],
        )

        diag = reconcile(
            contract=contract,
            triple=triple,
            html='<form><input name="title"><textarea name="description"></textarea></form>',
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.FIELD_MISSING
        assert len(diag.levers) >= 1
        assert "section" in diag.levers[0].construct or "element" in diag.levers[0].construct

    def test_no_triple_returns_permission_gap(self) -> None:
        """When triple is None, reconciler must return PERMISSION_GAP."""
        contract = CreateFormContract(
            entity="Task",
            required_fields=["title"],
            all_fields=["title"],
        )
        contract.status = "failed"
        contract.error = "Page not accessible"

        diag = reconcile(
            contract=contract,
            triple=None,
            html="<div>403</div>",
            appspec_entities=[],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.PERMISSION_GAP
        assert "Task" in diag.triple
        assert len(diag.levers) >= 1

    def test_triple_suspect_widget_mismatch(self) -> None:
        """When triple widget disagrees with raw entity re-derivation → TRIPLE_SUSPECT."""
        from dazzle.core.ir.domain import EntitySpec
        from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind

        # Raw entity has a TEXT field (should be textarea)
        raw_field = FieldSpec(
            name="notes",
            type=FieldType(kind=FieldTypeKind.TEXT),
        )
        raw_entity = EntitySpec(
            name="Task",
            fields=[raw_field],
        )

        # Triple claims TEXT_INPUT (wrong — should be TEXTAREA for TEXT kind)
        wrong_field = SurfaceFieldTriple(
            field_name="notes",
            widget=WidgetKind.TEXT_INPUT,  # Deliberately wrong
            is_required=False,
            is_fk=False,
            ref_entity=None,
        )
        triple = _make_triple(
            entity="Task",
            surface="task_edit",
            mode="edit",
            actions=["edit_submit"],
            fields=[wrong_field],
        )

        contract = EditFormContract(entity="Task", editable_fields=["notes"])
        contract.status = "failed"
        contract.error = "Widget type mismatch for notes"
        # Set the field attr so the cross-check can find it
        contract.field = "notes"  # type: ignore[attr-defined]

        diag = reconcile(
            contract=contract,
            triple=triple,
            html='<form><input name="notes" type="text"></form>',
            appspec_entities=[raw_entity],
            appspec_surfaces=[],
        )

        assert diag.kind == DiagnosisKind.TRIPLE_SUSPECT
        assert "notes" in diag.observation
        assert "textarea" in diag.observation.lower() or "TEXTAREA" in diag.observation
