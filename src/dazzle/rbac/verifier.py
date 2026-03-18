"""RBAC verifier — Layer 2 of the RBAC verification framework.

Provides types for representing verification results, the core `compare_cell()`
comparison function, and `VerificationReport` with JSON serialisation.

The full `verify()` async function (which starts a live server and probes
endpoints) is stubbed here. The types and comparison logic are the critical
pieces for unit testing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from dazzle.rbac.audit import AccessDecisionRecord
from dazzle.rbac.matrix import AccessMatrix, PolicyDecision


class CellResult(StrEnum):
    """The verification outcome for a single (role, entity, operation) cell."""

    PASS = "PASS"
    """Observed behaviour matches the expected policy decision."""

    VIOLATION = "VIOLATION"
    """Observed behaviour contradicts the expected policy decision."""

    WARNING = "WARNING"
    """Observed behaviour is technically consistent but warrants review."""


@dataclass
class VerifiedCell:
    """Verification result for a single (role, entity, operation) triple."""

    role: str
    entity: str
    operation: str
    expected: PolicyDecision
    observed_status: int
    observed_count: int | None
    result: CellResult
    audit_records: list[AccessDecisionRecord]
    detail: str

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "role": self.role,
            "entity": self.entity,
            "operation": self.operation,
            "expected": self.expected.value,
            "observed_status": self.observed_status,
            "observed_count": self.observed_count,
            "result": self.result.value,
            "audit_records": [r.to_dict() for r in self.audit_records],
            "detail": self.detail,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VerifiedCell:
        records = [AccessDecisionRecord(**r) for r in d.get("audit_records", [])]
        return cls(
            role=d["role"],
            entity=d["entity"],
            operation=d["operation"],
            expected=PolicyDecision(d["expected"]),
            observed_status=d["observed_status"],
            observed_count=d.get("observed_count"),
            result=CellResult(d["result"]),
            audit_records=records,
            detail=d.get("detail", ""),
        )


@dataclass
class VerificationReport:
    """Full RBAC verification report produced by `verify()`."""

    app_name: str
    timestamp: str
    dazzle_version: str
    matrix: AccessMatrix | None
    cells: list[VerifiedCell]
    total: int
    passed: int
    violated: int
    warnings: int

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serialisable representation of the report."""
        matrix_json = self.matrix.to_json() if self.matrix is not None else None
        return {
            "app_name": self.app_name,
            "timestamp": self.timestamp,
            "dazzle_version": self.dazzle_version,
            "matrix": matrix_json,
            "cells": [c.to_dict() for c in self.cells],
            "total": self.total,
            "passed": self.passed,
            "violated": self.violated,
            "warnings": self.warnings,
        }

    def save(self, path: Path) -> None:
        """Serialise the report to *path* as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> VerificationReport:
        """Deserialise a report previously saved with `.save()`."""
        raw = json.loads(path.read_text())

        # Reconstruct AccessMatrix if present.
        matrix: AccessMatrix | None = None
        if raw.get("matrix") is not None:
            m = raw["matrix"]
            cells_dict: dict[tuple[str, str, str], PolicyDecision] = {}
            for c in m.get("cells", []):
                cells_dict[(c["role"], c["entity"], c["operation"])] = PolicyDecision(c["decision"])
            from dazzle.rbac.matrix import PolicyWarning

            warnings = [
                PolicyWarning(
                    kind=w["kind"],
                    entity=w["entity"],
                    role=w["role"],
                    operation=w["operation"],
                    message=w["message"],
                )
                for w in m.get("warnings", [])
            ]
            matrix = AccessMatrix(
                cells=cells_dict,
                warnings=warnings,
                roles=m.get("roles", []),
                entities=m.get("entities", []),
                operations=m.get("operations", []),
            )

        cells = [VerifiedCell.from_dict(c) for c in raw.get("cells", [])]

        return cls(
            app_name=raw["app_name"],
            timestamp=raw["timestamp"],
            dazzle_version=raw["dazzle_version"],
            matrix=matrix,
            cells=cells,
            total=raw["total"],
            passed=raw["passed"],
            violated=raw["violated"],
            warnings=raw["warnings"],
        )


def compare_cell(
    expected: PolicyDecision,
    observed_status: int,
    observed_count: int | None,
    *,
    total: int | None = None,
) -> CellResult:
    """Compare an observed HTTP response against an expected policy decision.

    Comparison table
    ----------------
    DENY            + 403                              → PASS
    DENY            + 200                              → VIOLATION
    PERMIT          + 200                              → PASS
    PERMIT          + 403                              → VIOLATION
    PERMIT_FILTERED + 200 + 0 < count < total          → PASS
    PERMIT_FILTERED + 200 + count == total             → VIOLATION  (unfiltered)
    PERMIT_FILTERED + 200 + count == 0                 → WARNING
    PERMIT_UNPROTECTED + 200                           → PASS
    PERMIT_UNPROTECTED + 403                           → VIOLATION

    Any (expected, observed) combination not explicitly listed above
    is treated as WARNING.
    """
    if expected == PolicyDecision.DENY:
        if observed_status == 403:
            return CellResult.PASS
        if observed_status == 200:
            return CellResult.VIOLATION
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT:
        if observed_status == 200:
            return CellResult.PASS
        if observed_status == 403:
            return CellResult.VIOLATION
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT_FILTERED:
        if observed_status == 200:
            if observed_count is None:
                # Can't determine filtering without a count — treat as warning.
                return CellResult.WARNING
            if total is not None and observed_count == total:
                return CellResult.VIOLATION  # unfiltered
            if observed_count == 0:
                return CellResult.WARNING
            return CellResult.PASS
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT_UNPROTECTED:
        if observed_status == 200:
            return CellResult.PASS
        if observed_status == 403:
            return CellResult.VIOLATION
        return CellResult.WARNING

    return CellResult.WARNING


async def verify(
    project_root: Path,
    *,
    host: str = "localhost",
    port: int = 8000,
) -> VerificationReport:
    """Run Layer 2 dynamic RBAC verification against a live server.

    This is a stub — the full server lifecycle + HTTP probing implementation
    is deferred to a follow-up task.  Returns a placeholder report with zero
    cells so that callers can handle the result type consistently.
    """
    import importlib.metadata
    from datetime import UTC, datetime

    try:
        version = importlib.metadata.version("dazzle-dsl")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    return VerificationReport(
        app_name=str(project_root),
        timestamp=datetime.now(UTC).isoformat(),
        dazzle_version=version,
        matrix=None,
        cells=[],
        total=0,
        passed=0,
        violated=0,
        warnings=0,
    )
