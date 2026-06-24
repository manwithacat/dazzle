"""RBAC verifier — Layer 2 of the RBAC verification framework.

Provides types for representing verification results, the core `compare_cell()`
comparison function, `VerificationReport` with JSON serialisation, and the
`verify()` async function that boots the app in-process against a disposable
PostgreSQL database, seeds role users and baseline rows, probes every
(role, entity, operation) matrix cell, and reports PASS/VIOLATION/WARNING per cell.

This module re-exports every public symbol from the two sub-modules so all
existing ``from dazzle.rbac.verifier import X`` import statements continue
to work unchanged.
"""

from __future__ import annotations  # required: forward reference

import logging
from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec

# ---------------------------------------------------------------------------
# Re-exports from verification_harness (private helpers — also re-exported
# so callers that reach into private symbols via `from dazzle.rbac.verifier
# import _X` keep working without modification)
# ---------------------------------------------------------------------------
from dazzle.rbac.verification_harness import (
    _CSRF_COOKIE,
    _CSRF_HEADER,
    _PROBE_VERBS,
    _SUPERUSER_EMAIL,
    _SUPERUSER_PASSWORD,
    _VERIFIER_PASSWORD,
    _build_asgi_app,
    _BuiltApp,
    _create_capable_role,
    _csrf_headers,
    _DisposableDatabase,
    _minimal_body_for_entity,
    _minimal_flow_inputs,
    _open_role_client,
    _probe_all_cells,
    _probe_atomic_flows,
    _probe_cell,
    _probe_transport,
    _ProbeResult,
    _scope_create_overlay,
    _seed_baseline_rows,
    _seed_role_users,
    _verifier_app_context,
    _VerifierContext,
)

# ---------------------------------------------------------------------------
# Re-exports from verification_types (pure result types — cheap to import)
# ---------------------------------------------------------------------------
from dazzle.rbac.verification_types import (
    CellResult,
    VerificationReport,
    VerifiedCell,
    VerifiedFlow,
    compare_cell,
    compare_flow,
)

__all__ = [
    # Public types
    "CellResult",
    "VerifiedCell",
    "VerifiedFlow",
    "VerificationReport",
    "compare_cell",
    "compare_flow",
    "verify",
    # Re-exported private helpers (importers rely on these)
    "_SUPERUSER_EMAIL",
    "_SUPERUSER_PASSWORD",
    "_VERIFIER_PASSWORD",
    "_BuiltApp",
    "_CSRF_COOKIE",
    "_CSRF_HEADER",
    "_DisposableDatabase",
    "_ProbeResult",
    "_PROBE_VERBS",
    "_VerifierContext",
    "_build_asgi_app",
    "_create_capable_role",
    "_csrf_headers",
    "_minimal_body_for_entity",
    "_minimal_flow_inputs",
    "_open_role_client",
    "_probe_all_cells",
    "_probe_atomic_flows",
    "_probe_cell",
    "_probe_transport",
    "_scope_create_overlay",
    "_seed_baseline_rows",
    "_seed_role_users",
    "_verifier_app_context",
]

_logger = logging.getLogger(__name__)


async def verify(
    project_root: Path,
    *,
    server_database_url: str | None = None,
) -> VerificationReport:
    """Run Layer-2 dynamic RBAC verification.

    Provisions a disposable database, boots the app in-process, probes
    every (role, entity, operation) matrix cell as the relevant role, and
    compares observed behaviour against the static matrix.
    """
    import importlib.metadata
    import os
    from datetime import UTC, datetime

    from dazzle.rbac.audit import NullAuditSink, set_audit_sink
    from dazzle.rbac.matrix import generate_access_matrix

    try:
        version = importlib.metadata.version("dazzle-dsl")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    now = datetime.now(UTC).isoformat()

    server_url = server_database_url or os.environ.get("DATABASE_URL")
    if not server_url:
        raise RuntimeError(
            "dynamic RBAC verification requires a PostgreSQL server — set "
            "DATABASE_URL (the verifier creates and drops its own scratch DB)."
        )

    appspec = load_project_appspec(project_root)
    matrix = generate_access_matrix(appspec)

    cells: list[VerifiedCell] = []
    flows: list[VerifiedFlow] = []
    try:
        async with _DisposableDatabase(server_url) as db_url:
            async with _verifier_app_context(project_root, db_url) as ctx:
                creds = await _seed_role_users(ctx.auth_store, roles=list(matrix.roles))
                # All probe/seed clients ride a transport over the same booted
                # app, but with raise_app_exceptions=False so a server-side 500
                # surfaces as a status code instead of crashing the run.
                transport = _probe_transport(ctx.transport)
                # Baseline rows are seeded by a create-capable role-user, not
                # the roles-less bootstrap superuser (which every create gate
                # rejects with 403).
                baseline = await _seed_baseline_rows(
                    transport=transport,
                    base_url="http://verifier.local",
                    matrix=matrix,
                    creds=creds,
                    entities=list(matrix.entities),
                    appspec=ctx.appspec,
                )
                cells = await _probe_all_cells(ctx, matrix, creds, baseline, transport=transport)
                # #1314 — probe atomic-flow routes (POST /api/atomic/<name>) to
                # verify each flow's `permit: execute` gate. Additive to `cells`;
                # per-step scope correctness is integration-tested separately.
                flows = await _probe_atomic_flows(
                    matrix,
                    creds,
                    baseline,
                    transport=transport,
                    appspec=ctx.appspec,
                )
    except Exception as exc:
        # App-boot / database-provisioning failure — return an empty report
        # rather than raising, so callers can render a consistent result.
        # The `error` field disambiguates this from a clean run of an app
        # with zero cells: a zeroed report with `error` set means the
        # verifier could not run, not that everything passed.
        _logger.error("verify() boot failed: %s", exc, exc_info=True)
        return VerificationReport(
            app_name=str(project_root),
            timestamp=now,
            dazzle_version=version,
            matrix=matrix,
            cells=[],
            total=0,
            passed=0,
            violated=0,
            warnings=0,
            error=repr(exc),
        )
    finally:
        set_audit_sink(NullAuditSink())

    passed = sum(1 for c in cells if c.result == CellResult.PASS)
    violated = sum(1 for c in cells if c.result == CellResult.VIOLATION)
    warnings = sum(1 for c in cells if c.result == CellResult.WARNING)
    return VerificationReport(
        app_name=str(project_root),
        timestamp=now,
        dazzle_version=version,
        matrix=matrix,
        cells=cells,
        total=len(cells),
        passed=passed,
        violated=violated,
        warnings=warnings,
        flows=flows,
    )
