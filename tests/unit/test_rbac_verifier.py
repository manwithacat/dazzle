"""Tests for RBAC verifier types and comparison logic (Layer 2)."""

import json
from pathlib import Path

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
    def test_filtered_200_partial_count_is_pass(self):
        # count < total and count > 0
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 3, total=10) == CellResult.PASS

    def test_filtered_200_count_equals_total_is_violation(self):
        # count == total → unfiltered → VIOLATION
        assert (
            compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 10, total=10) == CellResult.VIOLATION
        )

    def test_filtered_200_count_zero_is_warning(self):
        # count == 0 → WARNING (might be over-filtering)
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 0, total=10) == CellResult.WARNING

    def test_filtered_200_no_count_is_warning(self):
        # No count available — can't determine filtering.
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, None) == CellResult.WARNING

    def test_filtered_non_200_is_warning(self):
        # 403 for PERMIT_FILTERED is not in the main table.
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 403, None) == CellResult.WARNING

    def test_filtered_count_one_of_many_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT_FILTERED, 200, 1, total=100) == CellResult.PASS


class TestCompareCellPermitUnprotected:
    def test_unprotected_200_is_pass(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 200, None) == CellResult.PASS

    def test_unprotected_403_is_violation(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 403, None) == CellResult.VIOLATION

    def test_unprotected_500_is_warning(self):
        assert compare_cell(PolicyDecision.PERMIT_UNPROTECTED, 500, None) == CellResult.WARNING


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
