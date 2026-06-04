"""RLS policy + role DDL generation (RLS tenancy Phase B).

Pure DDL-string generators for PostgreSQL row-level security. No DB access,
no IR types beyond a list of entity-name strings + the partition-key string —
only closed, templated DDL over framework-controlled identifiers (entity names
come from the IR, never from user input). This honours the ADR tenet that
business logic never lives in the engine: the policy bodies are a fixed
construction (tenant fence + permissive baseline), not a compiled predicate.

The authoritative artefact spec is
``docs/superpowers/specs/2026-06-04-rls-tenancy-generation-rules.md``:

  * §1.2 — ``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` (FORCE subjects the table
    owner to the policies, closing the owner-bypass hole).
  * §1.3 — the restrictive ``tenant_fence``. The ``true`` (missing-ok) argument
    to ``current_setting`` is load-bearing: an unset GUC then yields text
    ``NULL`` → ``NULL::uuid`` → the predicate is ``NULL`` (not true), so the row
    is excluded. This is fail-closed for reads (``USING``) and writes
    (``WITH CHECK``) alike, rather than a hard ``unrecognized configuration
    parameter`` abort.
  * §1.4 — the permissive ``tenant_baseline``. A fenced table with no permissive
    policy is *deny-all* (restrictive policies only subtract); the baseline
    ``USING (true)`` makes the effective set exactly the tenant's rows.
  * §3 — the three-role model: ``dazzle_owner`` (NOLOGIN), ``dazzle_app``
    (LOGIN, never BYPASSRLS), ``dazzle_bypass`` (LOGIN BYPASSRLS).

``CREATE POLICY`` has no ``IF NOT EXISTS`` form, so each policy is dropped
(``DROP POLICY IF EXISTS``) before being recreated, making re-apply safe;
``ENABLE``/``FORCE`` are inherently re-run-safe.

The role DDL is for the test fixture + deploy docs — it is **not** auto-run on
boot (roles are cluster-level, not per-app). Passwords are never embedded; the
LOGIN roles are created without a password and deploy sets it out of band
(an optional ``app_password`` / ``bypass_password`` is accepted purely so the
real-PG test fixture can provision loginable roles).
"""

from __future__ import annotations

from dazzle.back.runtime.query_builder import quote_identifier

# Fixed framework GUC name for the per-transaction tenant context (companion §6).
# This is deliberately INDEPENDENT of the app's partition_key column: the runtime
# (``pg_backend._set_tenant_context``) always sets ``dazzle.tenant_id``, so the
# fence must always READ ``dazzle.tenant_id`` — only the fenced *column* varies
# per app. Tying the GUC name to the partition_key (e.g. ``dazzle.org_id``) would
# make the fence read a GUC the runtime never sets → silent total-deny (C-2).
# pg_backend imports this same constant so the two never drift.
TENANT_GUC = "dazzle.tenant_id"


def build_rls_policy_ddl(
    tenant_scoped_names: list[str],
    *,
    partition_key: str,
) -> list[str]:
    """Emit idempotent RLS policy DDL for the given tenant-scoped entities.

    For each entity, in order: ``ENABLE`` + ``FORCE ROW LEVEL SECURITY``, then a
    drop-before-create of the restrictive ``tenant_fence`` and the permissive
    ``tenant_baseline``. See module docstring + companion §1.2-1.4.

    Args:
        tenant_scoped_names: Entity (table) names to fence. Framework-controlled
            identifiers from the IR — never user input.
        partition_key: The tenant discriminator *column* (e.g. ``"tenant_id"``).
            Drives the fenced column only — the GUC the fence reads is always the
            fixed framework constant :data:`TENANT_GUC` (``dazzle.tenant_id``),
            never derived from this, so the runtime and fence cannot disagree on
            the GUC name (C-2).

    Returns:
        A flat list of DDL statements. Empty list when there are no entities.
    """
    statements: list[str] = []

    col = quote_identifier(partition_key)
    # missing-ok current_setting → fail-closed (companion §1.3). Used verbatim
    # for both USING and WITH CHECK on the fence. The GUC name is the FIXED
    # framework constant (not the partition_key) so it matches what the runtime
    # sets via set_config — see TENANT_GUC.
    fence_body = f"{col} = current_setting('{TENANT_GUC}', true)::uuid"

    for name in tenant_scoped_names:
        table = quote_identifier(name)

        # §1.2 — re-run-safe; no IF NOT EXISTS needed.
        statements.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
        )  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless (cf. search_schema.py / pg_backend.py)
        statements.append(
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
        )  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless

        # §1.3 — restrictive tenant fence (ANDed with everything; the tenant
        # ring). Drop-before-create for idempotence (no CREATE POLICY IF NOT
        # EXISTS in Postgres).
        statements.append(
            f"DROP POLICY IF EXISTS tenant_fence ON {table}"
        )  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
        statements.append(  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
            f"CREATE POLICY tenant_fence ON {table}\n"
            f"    AS RESTRICTIVE\n"
            f"    FOR ALL\n"
            f"    USING      ({fence_body})\n"
            f"    WITH CHECK ({fence_body})"
        )

        # §1.4 — permissive baseline. Without ≥1 permissive policy the fenced
        # table is deny-all, invisible even to a correctly-scoped session. The
        # baseline exists ONLY to make the table not deny-all; its
        # ``WITH CHECK (true)`` is safe because the RESTRICTIVE tenant_fence is
        # ANDed over every permissive policy, so the net write check is the
        # fence's tenant_id match — the baseline never widens it.
        statements.append(
            f"DROP POLICY IF EXISTS tenant_baseline ON {table}"
        )  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
        statements.append(  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
            f"CREATE POLICY tenant_baseline ON {table}\n"
            f"    AS PERMISSIVE\n"
            f"    FOR ALL\n"
            f"    USING (true)\n"
            f"    WITH CHECK (true)"
        )

    return statements


def build_rls_role_ddl(
    *,
    app_password: str | None = None,
    bypass_password: str | None = None,
) -> list[str]:
    """Emit idempotent DDL for the three-role model (companion §3).

    - ``dazzle_owner`` — NOLOGIN; owns schema + tables, runs DDL migrations.
      Subject to RLS for DML under FORCE, but DDL is unaffected.
    - ``dazzle_app`` — LOGIN, **never** BYPASSRLS. The runtime role; subject to
      every policy. A missing tenant context denies (fail-closed).
    - ``dazzle_bypass`` — LOGIN, BYPASSRLS. Explicitly outside the fence for
      excision / cross-tenant analytics / ops.

    Each ``CREATE ROLE`` is wrapped in a ``DO`` block guarded by
    ``IF NOT EXISTS (SELECT FROM pg_roles ...)`` so re-running is safe. Passwords
    are never embedded by default; pass ``app_password`` / ``bypass_password``
    only from the test fixture that needs loginable roles. ``dazzle_app`` can
    never receive BYPASSRLS regardless of arguments.

    This DDL is for the test fixture + deploy docs — it is **not** auto-run on
    boot (roles are cluster-level).

    Returns:
        A list of DDL statements (DO blocks + GRANTs).
    """
    statements: list[str] = [
        _guarded_create_role("dazzle_owner", "NOLOGIN"),
        _guarded_create_role(
            "dazzle_app",
            _login_options(app_password),  # never BYPASSRLS
        ),
        _guarded_create_role(
            "dazzle_bypass",
            _login_options(bypass_password) + " BYPASSRLS",
        ),
        # Schema USAGE. On PostgreSQL 15+ (CVE-2022-2625) the public schema no
        # longer grants USAGE to PUBLIC, so the LOGIN roles cannot resolve any
        # object in ``public`` — the table privileges below are inert without it.
        "GRANT USAGE ON SCHEMA public TO dazzle_app, dazzle_bypass",
        # Table privileges. RLS still applies on top of these for dazzle_app;
        # dazzle_bypass holds BYPASSRLS so the grants are its only gate.
        "GRANT SELECT, INSERT, UPDATE, DELETE\n"
        "    ON ALL TABLES IN SCHEMA public TO dazzle_app, dazzle_bypass",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public\n"
        "    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dazzle_app, dazzle_bypass",
    ]
    return statements


def _login_options(password: str | None) -> str:
    """LOGIN clause for a loginable role, with an optional literal password.

    The password is only ever a fixture-supplied test value; production deploys
    omit it and set it out of band. A single-quote in the value is escaped so
    the DDL stays well-formed.
    """
    if password is None:
        return "LOGIN"
    escaped = password.replace("'", "''")
    return f"LOGIN PASSWORD '{escaped}'"


def _guarded_create_role(role: str, options: str) -> str:
    """A ``DO`` block that creates ``role`` with ``options`` iff it is absent.

    ``role`` is a fixed framework constant (never user input), so it is
    interpolated directly into both the guard and the ``CREATE ROLE``.
    """
    return (
        "DO $$\n"
        "BEGIN\n"
        f"    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN\n"
        f"        CREATE ROLE {role} {options};\n"
        "    END IF;\n"
        "END\n"
        "$$"
    )
