"""Pure result types for the RBAC Layer-2 verifier.

Contains only the types and comparison logic that have no httpx/psycopg
dependency, so they can be imported cheaply on every ``dazzle`` CLI
invocation without pulling in the full verification harness.
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
    error: str | None = None
    """Boot/provisioning failure message, or None on a successful run.

    A zeroed report (total=0) with `error` set means verification could
    not run — distinct from a clean run of an app with no cells.
    """

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
            "error": self.error,
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
            error=raw.get("error"),
        )


def compare_cell(
    expected: PolicyDecision,
    observed_status: int,
    observed_count: int | None,
    *,
    total: int | None = None,
    operation: str | None = None,
) -> CellResult:
    """Compare an observed HTTP response against an expected policy decision.

    Comparison table
    ----------------
    DENY               + 403                           → PASS
    DENY               + 200                           → VIOLATION
    PERMIT             + 200                            → PASS
    PERMIT             + 403                            → VIOLATION
    PERMIT_SCOPED      + 200                            → PASS
    PERMIT_SCOPED      + 403                            → VIOLATION
    PERMIT_SCOPED      + 404 on a single-id op          → PASS  (scoped out)
    PERMIT_NO_SCOPE    + 403                            → VIOLATION
    PERMIT_NO_SCOPE    + 200/404                        → WARNING (config gap)
    PERMIT_FILTERED    + 200 + 0 < count < total        → PASS
    PERMIT_FILTERED    + 200 + count == total           → VIOLATION  (unfiltered)
    PERMIT_FILTERED    + 200 + count == 0               → WARNING
    PERMIT_UNPROTECTED + 200                            → PASS
    PERMIT_UNPROTECTED + 403                            → VIOLATION

    Any (expected, observed) combination not explicitly listed above
    is treated as WARNING.

    ``operation`` is the matrix operation name (``read``/``update``/``delete``/
    ``list``/``create``).  It only matters for ``PERMIT_SCOPED``: a 404 on a
    single-id op means the scope filter legitimately hid the baseline row from
    a role that does not own it — that is *correct* RBAC behaviour, so it
    counts as PASS rather than an inconclusive WARNING.
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

    if expected == PolicyDecision.PERMIT_SCOPED:
        # Access is granted by `permit:` and rows are scoped by a `scope:`
        # rule. A 403 contradicts the grant. A 200 confirms it. A 404 on a
        # single-id op (read/update/delete) is the scope filter correctly
        # hiding a row the role does not own — definitively correct, PASS.
        if observed_status == 200:
            return CellResult.PASS
        if observed_status == 403:
            return CellResult.VIOLATION
        if observed_status == 404 and operation in ("read", "update", "delete"):
            return CellResult.PASS
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT_NO_SCOPE:
        # `permit:` grants access but no matching `scope:` rule exists — the
        # role sees 0 rows. The matrix already flags this as a config gap; the
        # only definitive verdict the verifier can add is that a 403 still
        # contradicts the permit grant.
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
