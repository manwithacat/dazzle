"""Tests for RBAC verifier types and comparison logic (Layer 2)."""

import json
from pathlib import Path

import pytest

from dazzle.rbac.audit import AccessDecisionRecord
from dazzle.rbac.matrix import AccessMatrix, PolicyDecision, PolicyWarning
from dazzle.rbac.verifier import CellResult, VerificationReport, VerifiedCell, compare_cell

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_record(**overrides) -> AccessDecisionRecord:
    defaults = {
        "timestamp": "2026-03-18T12:00:00Z",
        "request_id": "req-001",
        "user_id": "user-42",
        "roles": ["viewer"],
        "entity": "Shape",
        "operation": "read",
        "allowed": True,
        "effect": "permit",
        "matched_rule": "viewer_can_read_shape",
        "record_id": None,
        "tier": "entity",
    }
    defaults.update(overrides)
    return AccessDecisionRecord(**defaults)


def make_cell(
    *,
    role: str = "viewer",
    entity: str = "Shape",
    operation: str = "read",
    expected: PolicyDecision = PolicyDecision.PERMIT,
    observed_status: int = 200,
    observed_count: int | None = None,
    result: CellResult = CellResult.PASS,
    detail: str = "",
    audit_records: list[AccessDecisionRecord] | None = None,
) -> VerifiedCell:
    return VerifiedCell(
        role=role,
        entity=entity,
        operation=operation,
        expected=expected,
        observed_status=observed_status,
        observed_count=observed_count,
        result=result,
        audit_records=audit_records or [],
        detail=detail,
    )


def make_matrix() -> AccessMatrix:
    cells = {
        ("viewer", "Shape", "read"): PolicyDecision.PERMIT,
        ("admin", "Shape", "delete"): PolicyDecision.PERMIT,
        ("guest", "Shape", "list"): PolicyDecision.DENY,
    }
    warnings = [
        PolicyWarning(
            kind="orphan_role",
            entity="*",
            role="guest",
            operation="*",
            message="Persona 'guest' is not referenced in any permission rule",
        )
    ]
    return AccessMatrix(
        cells=cells,
        warnings=warnings,
        roles=["viewer", "admin", "guest"],
        entities=["Shape"],
        operations=["list", "read", "create", "update", "delete"],
    )


def make_report(**overrides) -> VerificationReport:
    defaults: dict = {
        "app_name": "shapes_app",
        "timestamp": "2026-03-18T12:00:00Z",
        "dazzle_version": "0.42.0",
        "matrix": None,
        "cells": [],
        "total": 0,
        "passed": 0,
        "violated": 0,
        "warnings": 0,
    }
    defaults.update(overrides)
    return VerificationReport(**defaults)


# ---------------------------------------------------------------------------
# compare_cell — exhaustive 9-case table
# ---------------------------------------------------------------------------


class TestCompareCellDeny:
    def test_deny_403_is_pass(self):
        assert compare_cell(PolicyDecision.DENY, 403, None) == CellResult.PASS

    def test_deny_200_is_violation(self):
        assert compare_cell(PolicyDecision.DENY, 200, None) == CellResult.VIOLATION

    def test_deny_500_is_warning(self):
        # Edge case — not in main table, treated as WARNING.
        assert compare_cell(PolicyDecision.DENY, 500, None) == CellResult.WARNING


class TestCompareCellPermit:
    def test_permit_200_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT, 200, None) == CellResult.PASS

    def test_permit_403_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT, 403, None) == CellResult.VIOLATION

    def test_permit_500_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT, 500, None) == CellResult.WARNING


class TestCompareCellPermitFiltered:
    @pytest.mark.parametrize(
        ("status", "count", "kwargs", "expected"),
        [
            (200, 3, {"total": 10}, CellResult.PASS),
            (200, 10, {"total": 10}, CellResult.VIOLATION),
            (200, 0, {"total": 10}, CellResult.WARNING),
            (200, None, {}, CellResult.WARNING),
            (403, None, {}, CellResult.WARNING),
            (200, 1, {"total": 100}, CellResult.PASS),
        ],
        ids=[
            "test_filtered_200_partial_count_is_pass",
            "test_filtered_200_count_equals_total_is_violation",
            "test_filtered_200_count_zero_is_warning",
            "test_filtered_200_no_count_is_warning",
            "test_filtered_non_200_is_warning",
            "test_filtered_count_one_of_many_is_pass",
        ],
    )
    def test_compare_cell_permit_filtered(self, status, count, kwargs, expected):
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, status, count, **kwargs) == expected


class TestCompareCellPermitUnprotected:
    def test_unprotected_200_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 200, None) == CellResult.PASS

    def test_unprotected_403_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 403, None) == CellResult.VIOLATION

    def test_unprotected_500_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 500, None) == CellResult.WARNING


class TestCompareCellPermitScoped:
    """`PERMIT_SCOPED` — access granted, rows filtered by a `scope:` rule.

    The matrix generator emits PERMIT_SCOPED for every scope-block-governed
    cell; before #1171 Task 6 `compare_cell` had no case for it, so all such
    cells fell through to an inconclusive WARNING.
    """

    def test_scoped_200_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT_SCOPED, 200, None) == CellResult.PASS

    def test_scoped_403_is_violation(self):
        # A scoped grant that 403s contradicts the permit decision.
        assert compare_cell(PolicyDecision.PERMIT_SCOPED, 403, None) == CellResult.VIOLATION

    @pytest.mark.parametrize("operation", ["read", "update", "delete"])
    def test_scoped_404_on_single_id_op_is_pass(self, operation):
        # 404 on a single-id op = the scope filter correctly hid a row the
        # role does not own. Definitively correct RBAC, so PASS.
        assert (
            compare_cell(PolicyDecision.PERMIT_SCOPED, 404, None, operation=operation)
            == CellResult.PASS
        )

    def test_scoped_404_on_list_is_warning(self):
        # 404 on list is not the scoped-out signal — inconclusive.
        assert (
            compare_cell(PolicyDecision.PERMIT_SCOPED, 404, None, operation="list")
            == CellResult.WARNING
        )

    def test_scoped_404_without_operation_is_warning(self):
        # No operation hint — cannot claim a definitive scoped-out PASS.
        assert compare_cell(PolicyDecision.PERMIT_SCOPED, 404, None) == CellResult.WARNING

    def test_scoped_500_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT_SCOPED, 500, None) == CellResult.WARNING


class TestCompareCellPermitNoScope:
    """`PERMIT_NO_SCOPE` — permitted but no matching `scope:` rule (config gap).

    The only definitive verdict the verifier can add is that a 403 still
    contradicts the permit grant; everything else stays WARNING.
    """

    def test_no_scope_403_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT_NO_SCOPE, 403, None) == CellResult.VIOLATION

    def test_no_scope_200_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT_NO_SCOPE, 200, None) == CellResult.WARNING

    def test_no_scope_404_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT_NO_SCOPE, 404, None) == CellResult.WARNING


# ---------------------------------------------------------------------------
# _create_capable_role — baseline-seeding role selection (#1171 Task 6)
# ---------------------------------------------------------------------------


def _matrix(cells: dict[tuple[str, str, str], PolicyDecision]) -> AccessMatrix:
    """Build an AccessMatrix from an explicit cell map for unit tests.

    Roles/entities/operations are derived from the cell keys (sorted for a
    stable order); no warnings are attached.
    """
    roles = sorted({k[0] for k in cells})
    entities = sorted({k[1] for k in cells})
    operations = sorted({k[2] for k in cells})
    return AccessMatrix(
        cells=cells,
        warnings=[],
        roles=roles,
        entities=entities,
        operations=operations,
    )


class TestCreateCapableRole:
    """`_create_capable_role` picks a role that can seed an entity's baseline
    row, or returns None when the entity is legitimately un-seedable.

    The None path is a load-bearing degradation contract: an entity no role
    can create stays un-seeded, so its read/update/delete cells have no
    baseline row to target and correctly remain WARNING rather than producing
    a false verdict.
    """

    def test_returns_role_with_create_permit(self):
        from dazzle.rbac.verifier import _create_capable_role

        m = _matrix(
            {
                ("admin", "Widget", "create"): PolicyDecision.PERMIT,
                ("viewer", "Widget", "create"): PolicyDecision.DENY,
            }
        )
        assert _create_capable_role(m, "Widget") == "admin"

    def test_accepts_any_permit_family_decision(self):
        # PERMIT_SCOPED / PERMIT_NO_SCOPE / PERMIT_UNPROTECTED all satisfy the
        # create gate — the helper matches the whole PERMIT* family.
        from dazzle.rbac.verifier import _create_capable_role

        for decision in (
            PolicyDecision.PERMIT_SCOPED,
            PolicyDecision.PERMIT_NO_SCOPE,
            PolicyDecision.PERMIT_UNPROTECTED,
            PolicyDecision.PERMIT_FILTERED,
        ):
            m = _matrix({("editor", "Widget", "create"): decision})
            assert _create_capable_role(m, "Widget") == "editor", decision

    def test_returns_none_when_no_role_can_create(self):
        # Every role is DENY on create — the entity is un-seedable. This is the
        # framework/admin-entity case (no CRUD surface, read-only exposure).
        from dazzle.rbac.verifier import _create_capable_role

        m = _matrix(
            {
                ("admin", "SystemHealth", "create"): PolicyDecision.DENY,
                ("viewer", "SystemHealth", "create"): PolicyDecision.DENY,
            }
        )
        assert _create_capable_role(m, "SystemHealth") is None

    def test_returns_none_for_unknown_entity(self):
        # An entity absent from the matrix has no create cell — matrix.get()
        # returns DENY, so the helper yields None (un-seedable).
        from dazzle.rbac.verifier import _create_capable_role

        m = _matrix({("admin", "Widget", "create"): PolicyDecision.PERMIT})
        assert _create_capable_role(m, "Gadget") is None

    def test_first_capable_role_follows_matrix_role_order(self):
        # When multiple roles can create, the first in matrix.roles order wins
        # — deterministic but declaration-order-dependent.
        from dazzle.rbac.verifier import _create_capable_role

        m = AccessMatrix(
            cells={
                ("manager", "Widget", "create"): PolicyDecision.PERMIT,
                ("admin", "Widget", "create"): PolicyDecision.PERMIT,
            },
            warnings=[],
            # Explicit role order: manager declared before admin.
            roles=["manager", "admin"],
            entities=["Widget"],
            operations=["create"],
        )
        assert _create_capable_role(m, "Widget") == "manager"


# ---------------------------------------------------------------------------
# _scope_create_overlay — scope: create: probe-body fidelity (#1174)
# ---------------------------------------------------------------------------


def _entity_with_create_scope(predicate, personas=("*",), entity_name="Widget"):
    """Build a minimal AppSpec carrying one entity whose `scope: create:` rule
    has the given compiled predicate. Used to exercise `_scope_create_overlay`
    without booting the full linker."""
    from dazzle.core.ir import (
        AccessSpec,
        AppSpec,
        DomainSpec,
        EntitySpec,
        PermissionKind,
        ScopeRule,
    )

    entity = EntitySpec(
        name=entity_name,
        title=entity_name,
        fields=[],
        access=AccessSpec(
            permissions=[],
            scopes=[
                ScopeRule(
                    operation=PermissionKind.CREATE,
                    condition=None,
                    personas=list(personas),
                    predicate=predicate,
                )
            ],
        ),
    )
    return AppSpec(name="test_app", domain=DomainSpec(entities=[entity]))


class TestScopeCreateOverlay:
    """`_scope_create_overlay` builds the create-body field values that satisfy
    an entity's `scope: create:` predicate — the fix for #1174, where the
    verifier's minimal probe body omitted optional scope-referenced fields
    (FeedbackReport's `reported_by`) and 403'd a correct-by-design create.
    """

    def test_user_attr_email_resolves_to_role_email(self):
        # The FeedbackReport regression shape: `reported_by = current_user.email`.
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.rbac.verifier import _scope_create_overlay

        appspec = _entity_with_create_scope(
            UserAttrCheck(field="reported_by", op=CompOp.EQ, user_attr="email")
        )
        overlay = _scope_create_overlay(
            "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
        )
        assert overlay == {"reported_by": "m@x.test"}

    def test_bare_current_user_resolves_to_auth_id(self):
        from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef
        from dazzle.rbac.verifier import _scope_create_overlay

        appspec = _entity_with_create_scope(
            ColumnCheck(field="created_by", op=CompOp.EQ, value=ValueRef(current_user=True))
        )
        overlay = _scope_create_overlay(
            "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
        )
        assert overlay == {"created_by": "u-1"}

    def test_literal_constraint_is_overlaid(self):
        from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef
        from dazzle.rbac.verifier import _scope_create_overlay

        appspec = _entity_with_create_scope(
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="draft"))
        )
        overlay = _scope_create_overlay(
            "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
        )
        assert overlay == {"status": "draft"}

    def test_unresolvable_user_attr_is_skipped(self):
        # `current_user.org` needs a seeded domain User row the generic probe
        # does not have — the field is left unset, the cell stays a WARNING.
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.rbac.verifier import _scope_create_overlay

        appspec = _entity_with_create_scope(
            UserAttrCheck(field="org", op=CompOp.EQ, user_attr="org")
        )
        overlay = _scope_create_overlay(
            "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
        )
        assert overlay == {}

    def test_and_composite_overlays_every_child(self):
        from dazzle.core.ir.predicates import (
            BoolComposite,
            BoolOp,
            ColumnCheck,
            CompOp,
            UserAttrCheck,
            ValueRef,
        )
        from dazzle.rbac.verifier import _scope_create_overlay

        predicate = BoolComposite(
            op=BoolOp.AND,
            children=[
                UserAttrCheck(field="reported_by", op=CompOp.EQ, user_attr="email"),
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="new")),
            ],
        )
        appspec = _entity_with_create_scope(predicate)
        overlay = _scope_create_overlay(
            "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
        )
        assert overlay == {"reported_by": "m@x.test", "status": "new"}

    def test_non_matching_role_yields_no_overlay(self):
        # The create-scope rule binds only `admin`; a `member` probe matches no
        # rule, so there is nothing to overlay (the create will default-deny).
        from dazzle.core.ir.predicates import CompOp, UserAttrCheck
        from dazzle.rbac.verifier import _scope_create_overlay

        appspec = _entity_with_create_scope(
            UserAttrCheck(field="reported_by", op=CompOp.EQ, user_attr="email"),
            personas=("admin",),
        )
        overlay = _scope_create_overlay(
            "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
        )
        assert overlay == {}

    def test_simple_task_feedbackreport_create_scope_is_satisfiable(self):
        # End-to-end against the real regression app: the FeedbackReport
        # `*`-persona create scope resolves to `reported_by = <role email>`.
        from pathlib import Path

        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.rbac.verifier import _scope_create_overlay

        appspec = load_project_appspec(Path("examples/simple_task"))
        overlay = _scope_create_overlay(
            "FeedbackReport",
            appspec,
            role="member",
            user_email="verify-member@dazzle.test",
            user_id="u-1",
        )
        assert overlay == {"reported_by": "verify-member@dazzle.test"}


# ---------------------------------------------------------------------------
# VerifiedCell
# ---------------------------------------------------------------------------


class TestVerifiedCell:
    def test_to_dict_round_trip(self):
        record = make_record()
        cell = make_cell(audit_records=[record], detail="test detail")
        d = cell.to_dict()

        assert d["role"] == "viewer"
        assert d["entity"] == "Shape"
        assert d["operation"] == "read"
        assert d["expected"] == "PERMIT"
        assert d["observed_status"] == 200
        assert d["observed_count"] is None
        assert d["result"] == "PASS"
        assert len(d["audit_records"]) == 1
        assert d["audit_records"][0]["user_id"] == "user-42"
        assert d["detail"] == "test detail"

    def test_from_dict_restores_cell(self):
        original = make_cell(
            role="admin",
            entity="Circle",
            operation="delete",
            expected=PolicyDecision.DENY,
            observed_status=403,
            result=CellResult.PASS,
            detail="expected deny, got 403",
        )
        restored = VerifiedCell.from_dict(original.to_dict())

        assert restored.role == "admin"
        assert restored.entity == "Circle"
        assert restored.operation == "delete"
        assert restored.expected == PolicyDecision.DENY
        assert restored.observed_status == 403
        assert restored.result == CellResult.PASS
        assert restored.detail == "expected deny, got 403"
        assert restored.audit_records == []

    def test_from_dict_with_audit_records(self):
        record = make_record(request_id="req-xyz")
        cell = make_cell(audit_records=[record])
        restored = VerifiedCell.from_dict(cell.to_dict())

        assert len(restored.audit_records) == 1
        assert restored.audit_records[0].request_id == "req-xyz"


# ---------------------------------------------------------------------------
# VerificationReport — save / load round-trip
# ---------------------------------------------------------------------------


class TestVerificationReportSerialization:
    def test_to_json_minimal(self):
        report = make_report()
        d = report.to_json()

        assert d["app_name"] == "shapes_app"
        assert d["timestamp"] == "2026-03-18T12:00:00Z"
        assert d["dazzle_version"] == "0.42.0"
        assert d["matrix"] is None
        assert d["cells"] == []
        assert d["total"] == 0

    def test_to_json_with_matrix(self):
        report = make_report(matrix=make_matrix())
        d = report.to_json()

        assert d["matrix"] is not None
        assert "roles" in d["matrix"]
        assert "viewer" in d["matrix"]["roles"]

    def test_save_creates_file(self, tmp_path: Path):
        report = make_report()
        path = tmp_path / "report.json"
        report.save(path)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["app_name"] == "shapes_app"

    def test_save_creates_parent_directories(self, tmp_path: Path):
        report = make_report()
        path = tmp_path / "nested" / "deep" / "report.json"
        report.save(path)
        assert path.exists()

    def test_load_round_trip_minimal(self, tmp_path: Path):
        report = make_report()
        path = tmp_path / "report.json"
        report.save(path)
        loaded = VerificationReport.load(path)

        assert loaded.app_name == report.app_name
        assert loaded.timestamp == report.timestamp
        assert loaded.dazzle_version == report.dazzle_version
        assert loaded.matrix is None
        assert loaded.cells == []
        assert loaded.total == 0

    def test_load_round_trip_with_cells(self, tmp_path: Path):
        cells = [
            make_cell(role="viewer", result=CellResult.PASS),
            make_cell(
                role="admin", result=CellResult.VIOLATION, detail="access denied unexpectedly"
            ),
        ]
        report = make_report(cells=cells, total=2, passed=1, violated=1)
        path = tmp_path / "report.json"
        report.save(path)
        loaded = VerificationReport.load(path)

        assert len(loaded.cells) == 2
        assert loaded.cells[0].role == "viewer"
        assert loaded.cells[0].result == CellResult.PASS
        assert loaded.cells[1].role == "admin"
        assert loaded.cells[1].result == CellResult.VIOLATION
        assert loaded.cells[1].detail == "access denied unexpectedly"
        assert loaded.passed == 1
        assert loaded.violated == 1

    def test_load_round_trip_with_matrix(self, tmp_path: Path):
        matrix = make_matrix()
        report = make_report(matrix=matrix)
        path = tmp_path / "report.json"
        report.save(path)
        loaded = VerificationReport.load(path)

        assert loaded.matrix is not None
        assert loaded.matrix.roles == ["viewer", "admin", "guest"]
        assert loaded.matrix.entities == ["Shape"]
        assert loaded.matrix.get("viewer", "Shape", "read") == PolicyDecision.PERMIT
        assert loaded.matrix.get("admin", "Shape", "delete") == PolicyDecision.PERMIT
        assert loaded.matrix.get("guest", "Shape", "list") == PolicyDecision.DENY

    def test_load_round_trip_preserves_warnings(self, tmp_path: Path):
        matrix = make_matrix()
        report = make_report(matrix=matrix)
        path = tmp_path / "report.json"
        report.save(path)
        loaded = VerificationReport.load(path)

        assert loaded.matrix is not None
        assert len(loaded.matrix.warnings) == 1
        assert loaded.matrix.warnings[0].kind == "orphan_role"
        assert loaded.matrix.warnings[0].role == "guest"

    def test_load_round_trip_with_audit_records(self, tmp_path: Path):
        record = make_record(request_id="req-saved")
        cell = make_cell(audit_records=[record])
        report = make_report(cells=[cell], total=1, passed=1)
        path = tmp_path / "report.json"
        report.save(path)
        loaded = VerificationReport.load(path)

        assert len(loaded.cells[0].audit_records) == 1
        assert loaded.cells[0].audit_records[0].request_id == "req-saved"
