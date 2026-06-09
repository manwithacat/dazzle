"""Pure result types for the RBAC Layer-2 verifier.

Contains only the types and comparison logic that have no httpx/psycopg
dependency, so they can be imported cheaply on every ``dazzle`` CLI
invocation without pulling in the full verification harness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
class VerifiedFlow:
    """Verification result for one ``(atomic flow, role)`` permit-gate probe (#1314).

    The dynamic verifier probes ``POST /api/atomic/<name>`` per projected flow
    (``AccessMatrix.atomic_flows``) as each role and checks the flow's
    ``permit: execute`` gate: a non-permitted role must be rejected (403) by the
    role gate, a permitted role must clear it. This verifies the
    ``AtomicFlowProjection.roles`` claim — the *permit* path. Per-step
    ``scope: create:`` / ``scope: update:`` correctness (own-scope commits /
    foreign-scope 403/404 + rollback) is enforced inside the flow transaction
    and is covered end-to-end against real Postgres in
    ``tests/integration/test_scope_runtime_pg.py``; it is deliberately *not*
    re-asserted here (the generic verifier cannot seed scope-parent rows).
    """

    flow: str
    role: str
    expected: PolicyDecision  # PERMIT if role ∈ flow.permit_execute, else DENY
    observed_status: int
    result: CellResult
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "flow": self.flow,
            "role": self.role,
            "expected": self.expected.value,
            "observed_status": self.observed_status,
            "result": self.result.value,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VerifiedFlow:
        return cls(
            flow=d["flow"],
            role=d["role"],
            expected=PolicyDecision(d["expected"]),
            observed_status=d["observed_status"],
            result=CellResult(d["result"]),
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
    flows: list[VerifiedFlow] = field(default_factory=list)
    """Atomic-flow permit-gate probe results (#1314), additive to the CRUD
    ``cells``. The cell counts (``total``/``passed``/``violated``/``warnings``)
    stay CRUD-only so existing consumers are unchanged; flow violations are
    surfaced separately by the CLI and folded into its exit-code gate."""

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
            "flows": [f.to_dict() for f in self.flows],
        }

    def save(self, path: Path) -> None:
        """Serialise the report to *path* as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, default=str), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> VerificationReport:
        """Deserialise a report previously saved with `.save()`."""
        raw = json.loads(path.read_text(encoding="utf-8"))

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
        flows = [VerifiedFlow.from_dict(f) for f in raw.get("flows", [])]

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
            flows=flows,
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


def compare_flow(
    expected: PolicyDecision,
    observed_status: int,
    *,
    role_gate_rejected: bool,
) -> CellResult:
    """Compare an atomic-flow probe against the flow's permit-gate expectation (#1314).

    The verifier probes ``POST /api/atomic/<name>`` per role and checks only the
    flow's ``permit: execute`` role gate (the ``AtomicFlowProjection.roles``
    claim). ``role_gate_rejected`` is True when a 403 came from the *role* gate
    (its detail names the required roles) rather than from per-step scope
    enforcement — the role gate fires before any body/scope processing.

    Truth table
    -----------
    DENY (role ∉ permit)   + 403 role-gate             → PASS    (correctly rejected by the gate)
    DENY                   + 403 non-role-gate         → WARNING (rejected, but by scope not the gate —
                                                                  the gate may be bypassed; flag for review)
    DENY                   + 200                        → VIOLATION (unpermitted role executed the flow)
    DENY                   + other                      → WARNING (inconclusive, e.g. 422 body gap)
    PERMIT (role ∈ permit) + 403 role-gate             → VIOLATION (permitted role wrongly rejected)
    PERMIT                 + 200 / 400 / 403-scope / 404 → PASS  (role gate cleared; downstream is
                                                                  scope/data, integration-tested)
    PERMIT                 + other (422 / 5xx)          → WARNING (probe couldn't construct a scenario)

    The DENY+403 case requires the *role-gate* marker for PASS: an unpermitted
    role is hit by the role gate before any scope check, so a 403 from scope
    instead (``role_gate_rejected=False``) means the gate may have been bypassed
    and scope incidentally saved it — a blind spot a verifier must surface, not
    pass. Per-step scope correctness is NOT decided here — see ``VerifiedFlow``.
    """
    if expected == PolicyDecision.DENY:
        if observed_status == 200:
            return CellResult.VIOLATION
        if observed_status == 403:
            return CellResult.PASS if role_gate_rejected else CellResult.WARNING
        return CellResult.WARNING

    # Any PERMIT* variant: the role holds the execute grant.
    if role_gate_rejected:
        return CellResult.VIOLATION
    if observed_status in (200, 400, 403, 404):
        return CellResult.PASS
    return CellResult.WARNING
