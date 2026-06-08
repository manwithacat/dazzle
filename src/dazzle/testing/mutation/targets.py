"""Registry of security-critical mutation targets + their kill-rate floors.

The ``dazzle sentinel mutate --suite security`` gate runs each target and fails if any
falls below its floor — so a drop in test *strength* (not just coverage) is caught.

Floors are set a few points below the measured 2026-06-08 baseline (see
``docs/proposals/mutation-audit-findings.md``) to absorb new-code churn without flapping,
while still catching a real regression. Paths are repo-root-relative.

IMPORTANT: the SQL-generation targets (``needs_pg=True``) are pinned mainly by the Postgres
enforcement suite — their floors ASSUME ``DATABASE_URL`` is set so those ``*_pg.py`` tests
actually run. Measured unit-only, they score ~5-8× lower. The CLI skips a ``needs_pg``
target (with a warning) when ``DATABASE_URL`` is absent rather than failing spuriously.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dazzle.testing.mutation.engine import Mutant


@dataclass(frozen=True)
class MutationTarget:
    module: str  # repo-root-relative path to the module under test
    tests: tuple[str, ...]  # pytest targets that pin it
    floor: int  # minimum acceptable kill-rate (%)
    needs_pg: bool = False  # tests include PG enforcement; requires DATABASE_URL
    note: str = ""


# Baselines measured 2026-06-08 (with PG where needs_pg):
#   connection_crypto 83% | rbac/matrix 69% | csrf 84% | rls_schema 60% | predicate 45%
SECURITY_TARGETS: tuple[MutationTarget, ...] = (
    MutationTarget(
        module="src/dazzle/back/runtime/auth/connection_crypto.py",
        tests=(
            "tests/unit/test_connection_crypto.py",
            "tests/unit/test_fuzz_small_parsers.py::TestConnectionCryptoRoundTrip",
        ),
        floor=80,
        note="secret-at-rest AES-GCM",
    ),
    MutationTarget(
        module="src/dazzle/rbac/matrix.py",
        tests=("tests/unit/test_rbac_matrix.py",),
        floor=65,
        note="static RBAC matrix",
    ),
    MutationTarget(
        module="src/dazzle/back/runtime/csrf.py",
        tests=(
            "tests/unit/test_csrf_session_binding_phase1.py",
            "tests/unit/test_csrf_origin_gate_phase2.py",
            "tests/unit/test_csrf_disposition_phase3.py",
            "tests/unit/test_csrf_policy_report_phase3.py",
            "tests/unit/test_csrf_exempt_paths.py",
            "tests/unit/test_csrf_trusted_origins_config.py",
            "tests/unit/test_csrf_wiring_1337.py",
            "tests/unit/test_csrf_middleware_defers_to_route_cookie.py",
            "tests/unit/test_consent_csrf_exempt.py",
        ),
        floor=80,
        note="CSRF middleware",
    ),
    MutationTarget(
        module="src/dazzle/back/runtime/rls_schema.py",
        tests=(
            "tests/unit/test_rls_schema.py",
            "tests/integration/test_rls_enforcement_pg.py",
            "tests/integration/test_rls_scope_enforcement_pg.py",
            "tests/integration/test_rls_apply_and_drift_pg.py",
        ),
        floor=55,
        needs_pg=True,
        note="RLS DDL generation (PG-pinned)",
    ),
    MutationTarget(
        module="src/dazzle/back/runtime/predicate_compiler.py",
        tests=(
            "tests/unit/test_predicate_compiler.py",
            "tests/integration/test_scope_runtime_pg.py",
            "tests/integration/test_scope_parent_lock_pg.py",
            "tests/integration/test_rls_scope_enforcement_pg.py",
        ),
        floor=40,
        needs_pg=True,
        note="scope→SQL compiler (PG-pinned)",
    ),
)


@dataclass
class SuiteOutcome:
    target: MutationTarget
    kill_rate: float
    floor: int
    passed: bool
    skipped: bool = False
    survivors: list[Mutant] = field(default_factory=list)


# Gate exit codes — distinct so a skip can never masquerade as a clean pass.
GATE_OK = 0  # every target measured and at/above its floor
GATE_FLOOR_BREACH = 1  # at least one measured target below its floor
GATE_INCOMPLETE = 2  # a target was skipped (e.g. needs_pg without DATABASE_URL)


def suite_exit_code(outcomes: list[SuiteOutcome]) -> int:
    """Decide the gate's exit code. A floor breach (1) outranks an incomplete run (2);
    a skipped target NEVER yields 0 — leaving a security module unmeasured must be visible,
    not silently green (a misconfigured CI without DATABASE_URL would otherwise pass)."""
    if any(not o.passed and not o.skipped for o in outcomes):
        return GATE_FLOOR_BREACH
    if any(o.skipped for o in outcomes):
        return GATE_INCOMPLETE
    return GATE_OK
