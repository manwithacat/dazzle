"""Tests for RBAC verifier types and comparison logic (Layer 2)."""

import json
from pathlib import Path

import pytest

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    UserAttrCheck,
    ValueRef,
)
from dazzle.rbac.audit import AccessDecisionRecord
from dazzle.rbac.matrix import AccessMatrix, PolicyDecision, PolicyWarning
from dazzle.rbac.verifier import (
    CellResult,
    VerificationReport,
    VerifiedCell,
    compare_cell,
)

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
# compare_cell — the full decision x status table
# ---------------------------------------------------------------------------

_D = PolicyDecision
_R = CellResult


@pytest.mark.parametrize(
    ("decision", "status", "count", "kwargs", "expected"),
    [
        # DENY: 403 is the pass signal; 500 is outside the main table -> WARNING.
        pytest.param(_D.DENY, 403, None, {}, _R.PASS, id="deny-403-pass"),
        pytest.param(_D.DENY, 200, None, {}, _R.VIOLATION, id="deny-200-violation"),
        pytest.param(_D.DENY, 500, None, {}, _R.WARNING, id="deny-500-warning"),
        # PERMIT
        pytest.param(_D.PERMIT, 200, None, {}, _R.PASS, id="permit-200-pass"),
        pytest.param(_D.PERMIT, 403, None, {}, _R.VIOLATION, id="permit-403-violation"),
        pytest.param(_D.PERMIT, 500, None, {}, _R.WARNING, id="permit-500-warning"),
        # PERMIT_FILTERED: verdict hinges on observed count vs total.
        pytest.param(
            _D.PERMIT_FILTERED, 200, 3, {"total": 10}, _R.PASS, id="filtered-200-partial-pass"
        ),
        pytest.param(
            _D.PERMIT_FILTERED,
            200,
            10,
            {"total": 10},
            _R.VIOLATION,
            id="filtered-200-count-equals-total-violation",
        ),
        pytest.param(
            _D.PERMIT_FILTERED, 200, 0, {"total": 10}, _R.WARNING, id="filtered-200-zero-warning"
        ),
        pytest.param(
            _D.PERMIT_FILTERED, 200, None, {}, _R.WARNING, id="filtered-200-no-count-warning"
        ),
        pytest.param(_D.PERMIT_FILTERED, 403, None, {}, _R.WARNING, id="filtered-non-200-warning"),
        pytest.param(
            _D.PERMIT_FILTERED, 200, 1, {"total": 100}, _R.PASS, id="filtered-one-of-many-pass"
        ),
        # PERMIT_UNPROTECTED
        pytest.param(_D.PERMIT_UNPROTECTED, 200, None, {}, _R.PASS, id="unprotected-200-pass"),
        pytest.param(
            _D.PERMIT_UNPROTECTED, 403, None, {}, _R.VIOLATION, id="unprotected-403-violation"
        ),
        pytest.param(
            _D.PERMIT_UNPROTECTED, 500, None, {}, _R.WARNING, id="unprotected-500-warning"
        ),
        # PERMIT_SCOPED (#1171 Task 6): before it, every scoped cell fell
        # through to WARNING. 403 contradicts the grant; 404 on a single-id op
        # is the scope filter correctly hiding an unowned row -> PASS; 404 on
        # list, or with no operation hint, is inconclusive.
        pytest.param(_D.PERMIT_SCOPED, 200, None, {}, _R.PASS, id="scoped-200-pass-1171"),
        pytest.param(_D.PERMIT_SCOPED, 403, None, {}, _R.VIOLATION, id="scoped-403-violation"),
        *[
            pytest.param(
                _D.PERMIT_SCOPED, 404, None, {"operation": op}, _R.PASS, id=f"scoped-404-{op}-pass"
            )
            for op in ("read", "update", "delete")
        ],
        pytest.param(
            _D.PERMIT_SCOPED,
            404,
            None,
            {"operation": "list"},
            _R.WARNING,
            id="scoped-404-list-warning",
        ),
        pytest.param(_D.PERMIT_SCOPED, 404, None, {}, _R.WARNING, id="scoped-404-no-op-warning"),
        pytest.param(_D.PERMIT_SCOPED, 500, None, {}, _R.WARNING, id="scoped-500-warning"),
        # PERMIT_NO_SCOPE (config gap): only a 403 is definitive.
        pytest.param(_D.PERMIT_NO_SCOPE, 403, None, {}, _R.VIOLATION, id="no-scope-403-violation"),
        pytest.param(_D.PERMIT_NO_SCOPE, 200, None, {}, _R.WARNING, id="no-scope-200-warning"),
        pytest.param(_D.PERMIT_NO_SCOPE, 404, None, {}, _R.WARNING, id="no-scope-404-warning"),
    ],
)
def test_compare_cell(decision, status, count, kwargs, expected):
    assert compare_cell(decision, status, count, **kwargs) == expected


# ---------------------------------------------------------------------------
# _create_capable_role — baseline-seeding role selection (#1171 Task 6)
# ---------------------------------------------------------------------------


def _matrix(
    cells: dict[tuple[str, str, str], PolicyDecision], roles: list[str] | None = None
) -> AccessMatrix:
    """Build an AccessMatrix from an explicit cell map for unit tests.

    Roles/entities/operations are derived from the cell keys (sorted for a
    stable order) unless ``roles`` pins an explicit order; no warnings.
    """
    return AccessMatrix(
        cells=cells,
        warnings=[],
        roles=roles if roles is not None else sorted({k[0] for k in cells}),
        entities=sorted({k[1] for k in cells}),
        operations=sorted({k[2] for k in cells}),
    )


@pytest.mark.parametrize(
    ("cells", "roles", "entity", "expected"),
    [
        pytest.param(
            {("admin", "Widget", "create"): _D.PERMIT, ("viewer", "Widget", "create"): _D.DENY},
            None,
            "Widget",
            "admin",
            id="role-with-create-permit",
        ),
        # The whole PERMIT* family satisfies the create gate.
        *[
            pytest.param(
                {("editor", "Widget", "create"): decision},
                None,
                "Widget",
                "editor",
                id=f"permit-family-{decision.name.lower()}",
            )
            for decision in (
                _D.PERMIT_SCOPED,
                _D.PERMIT_NO_SCOPE,
                _D.PERMIT_UNPROTECTED,
                _D.PERMIT_FILTERED,
            )
        ],
        # Every role DENY on create — un-seedable framework/admin entity.
        pytest.param(
            {
                ("admin", "SystemHealth", "create"): _D.DENY,
                ("viewer", "SystemHealth", "create"): _D.DENY,
            },
            None,
            "SystemHealth",
            None,
            id="no-role-can-create-none",
        ),
        # Entity absent from the matrix: matrix.get() returns DENY.
        pytest.param(
            {("admin", "Widget", "create"): _D.PERMIT},
            None,
            "Gadget",
            None,
            id="unknown-entity-none",
        ),
        # Several capable roles: first in matrix.roles order wins.
        pytest.param(
            {("manager", "Widget", "create"): _D.PERMIT, ("admin", "Widget", "create"): _D.PERMIT},
            ["manager", "admin"],
            "Widget",
            "manager",
            id="first-capable-role-follows-role-order",
        ),
    ],
)
def test_create_capable_role(cells, roles, entity, expected):
    """`_create_capable_role` picks a role that can seed an entity's baseline
    row, or returns None when the entity is legitimately un-seedable.

    The None path is a load-bearing degradation contract: an entity no role
    can create stays un-seeded, so its read/update/delete cells have no
    baseline row to target and correctly remain WARNING rather than producing
    a false verdict.
    """
    from dazzle.rbac.verifier import _create_capable_role

    assert _create_capable_role(_matrix(cells, roles), entity) == expected


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


_EMAIL_EQ = UserAttrCheck(field="reported_by", op=CompOp.EQ, user_attr="email")


@pytest.mark.parametrize(
    ("predicate", "personas", "expected"),
    [
        # The FeedbackReport regression shape: `reported_by = current_user.email`.
        pytest.param(_EMAIL_EQ, ("*",), {"reported_by": "m@x.test"}, id="user-attr-email-1174"),
        pytest.param(
            ColumnCheck(field="created_by", op=CompOp.EQ, value=ValueRef(current_user=True)),
            ("*",),
            {"created_by": "u-1"},
            id="bare-current-user-is-auth-id",
        ),
        pytest.param(
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="draft")),
            ("*",),
            {"status": "draft"},
            id="literal-constraint",
        ),
        # `current_user.org` needs a seeded domain User row the generic probe
        # lacks — left unset, the cell stays a WARNING.
        pytest.param(
            UserAttrCheck(field="org", op=CompOp.EQ, user_attr="org"),
            ("*",),
            {},
            id="unresolvable-user-attr-skipped",
        ),
        pytest.param(
            BoolComposite(
                op=BoolOp.AND,
                children=[
                    _EMAIL_EQ,
                    ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="new")),
                ],
            ),
            ("*",),
            {"reported_by": "m@x.test", "status": "new"},
            id="and-composite-overlays-every-child",
        ),
        # Rule binds only `admin`; a `member` probe matches no rule.
        pytest.param(_EMAIL_EQ, ("admin",), {}, id="non-matching-role-no-overlay"),
    ],
)
def test_scope_create_overlay(predicate, personas, expected):
    """`_scope_create_overlay` builds the create-body field values that satisfy
    an entity's `scope: create:` predicate — the fix for #1174, where the
    verifier's minimal probe body omitted optional scope-referenced fields
    (FeedbackReport's `reported_by`) and 403'd a correct-by-design create.
    """
    from dazzle.rbac.verifier import _scope_create_overlay

    appspec = _entity_with_create_scope(predicate, personas=personas)
    overlay = _scope_create_overlay(
        "Widget", appspec, role="member", user_email="m@x.test", user_id="u-1"
    )
    assert overlay == expected


def test_simple_task_feedbackreport_create_scope_is_satisfiable():
    # End-to-end against the real regression app: the FeedbackReport
    # `*`-persona create scope resolves to `reported_by = <role email>`.
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
