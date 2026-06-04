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

from typing import TYPE_CHECKING, Any

from dazzle.back.runtime.query_builder import quote_identifier

if TYPE_CHECKING:
    from dazzle.back.runtime.predicate_compiler import EntityTypeResolver
    from dazzle.core.ir.fk_graph import FKGraph

# Fixed framework GUC name for the per-transaction tenant context (companion §6).
# This is deliberately INDEPENDENT of the app's partition_key column: the runtime
# (``pg_backend._set_tenant_context``) always sets ``dazzle.tenant_id``, so the
# fence must always READ ``dazzle.tenant_id`` — only the fenced *column* varies
# per app. Tying the GUC name to the partition_key (e.g. ``dazzle.org_id``) would
# make the fence read a GUC the runtime never sets → silent total-deny (C-2).
# pg_backend imports this same constant so the two never drift.
TENANT_GUC = "dazzle.tenant_id"

# The fixed GUC name prefix for per-request user attributes that the intra-tenant
# scope policies read (Phase C). A scope policy body reads
# ``current_setting('dazzle.user_<attr>', true)`` and the runtime
# (``pg_backend._set_rls_user_attrs``) sets ``set_config('dazzle.user_<attr>', …)``
# — the name the policy READS must equal the name the runtime SETS or the
# predicate silently total-denies. Both sides derive that name from THIS one
# constant (predicate_compiler imports it for the policy body; pg_backend imports
# it for set_config, with a module-load assert) so they can never drift (mirrors
# the TENANT_GUC drift-guard, C-2). ``current_user`` → ``dazzle.user_id``; a named
# attribute ``a`` → ``dazzle.user_<a>``.
USER_GUC_PREFIX = "dazzle.user_"


def build_all_rls_ddl(appspec: Any, entities: list[Any]) -> list[str]:
    """Build the full RLS DDL set for an appspec — the shared partitioner (Phase D).

    The single, DB-free source of the tenant fence + per-verb scope / baseline
    policy DDL. Both the dev ``create_all`` apply
    (:meth:`dazzle.back.runtime.server.DazzleBackendApp._apply_rls_policies`) and
    Phase D's prod-apply / ``dazzle inspect rls`` / drift gate consume this so the
    generated policy set never diverges across the paths that apply, inspect, and
    verify it.

    The partitioning (lifted verbatim from the old inline ``_apply_rls_policies``):

    - **scoped entity** (≥1 ``entity.access.scopes`` rule) → Phase C per-verb
      policies via :func:`build_rls_scope_policy_ddl`; the permissive
      ``tenant_baseline`` is dropped (a verb without a scope rule is denied).
    - **tenant-flat entity** (no scope rules) → Phase B's fence + permissive
      ``tenant_baseline`` via :func:`build_rls_policy_ddl`.

    A scope rule without an FK graph cannot compile a policy body → fail loud
    (``ValueError``) rather than silently fall back to a permissive baseline,
    which would widen the intra-tenant authorization the scope rule enforces.

    Args:
        appspec: The application IR (or any object exposing ``.tenancy``,
            ``.domain.entities``, and ``.fk_graph``).
        entities: The converted back-spec entities (``server._entities``) — each
            carries ``.access.scopes`` with compiled ``.predicate`` and the field
            list used by the type resolver. This is the list iterated for the
            scoped-vs-flat partition.

    Returns:
        A flat list of idempotent DDL statements. Empty list when there is no
        tenancy, the isolation mode is not ``shared_schema``, or no entity is
        tenant-scoped — so the builder is a no-op for every non-tenant app and
        for every other isolation mode, matching the old apply behaviour.

    Raises:
        ValueError: A scoped entity carries scope rules but ``appspec.fk_graph``
            is ``None`` (cannot compile the policy body).
    """
    from dazzle.back.runtime.predicate_compiler import build_entity_type_resolver
    from dazzle.back.runtime.sa_schema import scoped_entity_names
    from dazzle.core.ir import TenancyMode

    tenancy = getattr(appspec, "tenancy", None)
    if tenancy is None or tenancy.isolation.mode != TenancyMode.SHARED_SCHEMA:
        return []

    pk = tenancy.isolation.partition_key
    scoped = scoped_entity_names(appspec.domain.entities, pk)
    if not scoped:
        return []

    fk_graph = getattr(appspec, "fk_graph", None)
    # Lazy (entity, field) -> pg-type resolver for the GUC casts in scope policy
    # bodies — built once over the back-spec entities (the shape
    # compile_predicate_policy + build_entity_type_resolver expect). Computes a
    # column's type only when a policy references it.
    entity_types = build_entity_type_resolver(entities)

    # Partition the tenant-scoped entities into "has scope rules" (Phase C
    # per-verb policies) vs "tenant-flat" (Phase B baseline). A scope rule
    # without an FK graph cannot compile a policy body → fail loud rather than
    # silently fall back to a permissive baseline (which would widen the
    # intra-tenant authorization the scope rule meant to enforce).
    statements: list[str] = []
    flat_names: list[str] = []
    for entity in entities:
        if entity.name not in scoped:
            continue
        access = getattr(entity, "access", None)
        has_scopes = access is not None and bool(getattr(access, "scopes", None))
        if has_scopes:
            if fk_graph is None:
                raise ValueError(
                    f"RLS scope policy for {entity.name!r} requires the FK "
                    "graph (appspec.fk_graph) but it is missing"
                )
            statements.extend(
                build_rls_scope_policy_ddl(entity, fk_graph, entity_types, partition_key=pk)
            )
        else:
            flat_names.append(entity.name)

    # Tenant-flat entities keep Phase B's fence + permissive baseline.
    statements.extend(build_rls_policy_ddl(sorted(flat_names), partition_key=pk))

    return statements


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

    for name in tenant_scoped_names:
        table = quote_identifier(name)

        # §1.2 + §1.3 — ENABLE/FORCE + restrictive tenant fence (shared with the
        # scoped-entity path so the two never drift).
        statements.extend(_enable_force_fence(table, partition_key))

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


def _enable_force_fence(table: str, partition_key: str) -> list[str]:
    """ENABLE + FORCE RLS and the restrictive ``tenant_fence`` for *table*.

    Shared by :func:`build_rls_policy_ddl` (tenant-flat) and
    :func:`build_rls_scope_policy_ddl` (scoped) so the fence is constructed in
    exactly one place. *table* is already a quoted identifier. See companion
    §1.2 (ENABLE/FORCE) + §1.3 (restrictive fence; missing-ok ``current_setting``
    → fail-closed). The fence reads the fixed :data:`TENANT_GUC`, never the
    partition_key-derived name (C-2).
    """
    col = quote_identifier(partition_key)
    fence_body = f"{col} = current_setting('{TENANT_GUC}', true)::uuid"
    return [
        # §1.2 — re-run-safe; no IF NOT EXISTS needed.
        # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless (cf. search_schema.py / pg_backend.py)
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        # §1.3 — restrictive tenant fence (ANDed with everything; the tenant
        # ring). Drop-before-create for idempotence (no CREATE POLICY IF NOT
        # EXISTS in Postgres).
        # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
        f"DROP POLICY IF EXISTS tenant_fence ON {table}",
        # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless
        (
            f"CREATE POLICY tenant_fence ON {table}\n"
            f"    AS RESTRICTIVE\n"
            f"    FOR ALL\n"
            f"    USING      ({fence_body})\n"
            f"    WITH CHECK ({fence_body})"
        ),
    ]


# Map a PostgreSQL command verb → the scope-policy name + clause shape. The
# read/list → SELECT union is handled in :func:`build_rls_scope_policy_ddl`
# (companion §2.1) before this map is consulted; the SELECT entry here carries
# the policy name + the FOR keyword only.
#: Policy name per SQL verb (companion §1.4(b)).
_SCOPE_POLICY_NAME: dict[str, str] = {
    "SELECT": "scope_select",
    "INSERT": "scope_insert",
    "UPDATE": "scope_update",
    "DELETE": "scope_delete",
}


def build_rls_scope_policy_ddl(
    entity: Any,
    fk_graph: FKGraph,
    entity_types: EntityTypeResolver,
    *,
    partition_key: str,
) -> list[str]:
    """Emit per-verb intra-tenant scope policy DDL for a *scoped* entity (§1.4(b)).

    A scoped entity is one with ≥1 ``entity.access.scopes`` rule. The emitted
    DDL keeps Phase B's ENABLE/FORCE + restrictive ``tenant_fence`` (via
    :func:`_enable_force_fence`), **drops** the permissive ``tenant_baseline``
    (scoped entities are governed by per-verb policies, not a blanket
    baseline), and emits one permissive policy per **permitted verb**, the body
    compiled from the scope predicate algebra via
    :func:`~dazzle.back.runtime.predicate_compiler.compile_predicate_policy`:

    - ``scope_select`` — ``FOR SELECT`` ``USING (<OR of read + list>)`` (the
      read/list → SELECT union, companion §2.1).
    - ``scope_insert`` — ``FOR INSERT`` ``WITH CHECK (<create>)`` (USING is not
      consulted for INSERT).
    - ``scope_update`` — ``FOR UPDATE`` ``USING (<update>) WITH CHECK (<update>)``.
    - ``scope_delete`` — ``FOR DELETE`` ``USING (<delete>)``.

    A verb with NO scope rule emits **no** policy → that verb is denied
    (companion §1.4; net effect per verb is ``(OR of permissive scope policies)
    AND tenant_fence``, and an empty OR is deny-all for that verb). The
    ``DROP POLICY IF EXISTS`` is still emitted for every scope-policy name so
    re-apply is idempotent even when a previously-covered verb loses its rule.

    Multiple scope rules for the same verb (multiple personas — the linker keeps
    one ``ScopeRule`` per ``scope:`` line) have their predicate bodies **ORed**
    together in that verb's policy.

    Args:
        entity: The scoped entity (must have ``access.scopes``; raises if not).
        fk_graph: The FK graph for path/exists resolution in policy bodies.
        entity_types: ``(entity, field) -> pg_type`` resolver for GUC casts.
        partition_key: The tenant discriminator column (fence only; the GUC the
            fence reads is the fixed :data:`TENANT_GUC`).

    Returns:
        A flat list of idempotent DDL statements.

    Raises:
        ValueError: If *entity* has no scope rules (use
            :func:`build_rls_policy_ddl` for tenant-flat entities), or if a
            policy body can't be compiled (e.g. an unresolvable GUC cast type,
            or a dotted-junction ``via`` binding — not yet supported in policy
            mode; both fail loud rather than emit a wrong/absent policy).
    """
    from dazzle.back.runtime.predicate_compiler import compile_predicate_policy

    access = entity.access
    if access is None or not access.scopes:
        raise ValueError(
            f"build_rls_scope_policy_ddl: entity {entity.name!r} has no scope "
            "rules; use build_rls_policy_ddl for tenant-flat entities"
        )

    table = quote_identifier(entity.name)

    # Group compiled predicate bodies by SQL verb. read + list both → SELECT
    # (companion §2.1), ORed; multiple rules per verb also OR together. The
    # operation is matched by its lowercase *value* (``"read"``/``"list"``/…)
    # so this accepts either the core-IR ``PermissionKind`` or the back-spec
    # ``AccessOperationKind`` (identical values) without importing either.
    verb_bodies: dict[str, list[str]] = {v: [] for v in _SCOPE_POLICY_NAME}
    _op_value_to_verb = {
        "read": "SELECT",
        "list": "SELECT",
        "create": "INSERT",
        "update": "UPDATE",
        "delete": "DELETE",
    }
    for rule in access.scopes:
        op = rule.operation
        op_val = op.value if hasattr(op, "value") else str(op)
        verb = _op_value_to_verb.get(op_val)
        if verb is None:  # pragma: no cover - the operation set is closed
            continue
        body = compile_predicate_policy(
            rule.predicate, entity.name, fk_graph, entity_types=entity_types
        )
        verb_bodies[verb].append(body)

    statements: list[str] = _enable_force_fence(table, partition_key)

    # §1.4(b) — scoped entities drop the permissive baseline; per-verb policies
    # govern instead. Drop only (never recreated here).
    statements.append(
        f"DROP POLICY IF EXISTS tenant_baseline ON {table}"
    )  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless

    # Per-verb permissive scope policies, in a stable order. The DROP is always
    # emitted (idempotent re-apply); the CREATE only when the verb has ≥1 rule.
    for verb, policy_name in _SCOPE_POLICY_NAME.items():
        statements.append(
            f"DROP POLICY IF EXISTS {policy_name} ON {table}"
        )  # nosemgrep: closed templated DDL over IR-controlled identifiers, parameterless

        bodies = verb_bodies[verb]
        if not bodies:
            continue  # no rule for this verb → no policy → verb denied (§1.4)

        # OR the bodies of all rules for this verb. A single body is emitted
        # bare; multiple are each parenthesised and ORed.
        combined = bodies[0] if len(bodies) == 1 else " OR ".join(f"({b})" for b in bodies)

        statements.append(_scope_policy_create(policy_name, table, verb, combined))

    return statements


def _scope_policy_create(policy_name: str, table: str, verb: str, body: str) -> str:
    """Render one ``CREATE POLICY`` for a verb's combined scope predicate body.

    Clause shape per verb (companion §1.4(b)):

    - ``SELECT`` / ``DELETE`` → ``USING`` only (USING gates the visible/target
      rows; WITH CHECK is not consulted for these verbs).
    - ``INSERT`` → ``WITH CHECK`` only (USING is not consulted for INSERT).
    - ``UPDATE`` → ``USING`` (which rows may be targeted) + ``WITH CHECK`` (the
      post-image), both the same scope body.

    *table* is already a quoted identifier; *policy_name* / *verb* are fixed
    framework constants; *body* is a param-free policy fragment built by the
    predicate compiler's policy mode (GUC reads + safely-inlined literals).
    """
    if verb == "INSERT":
        clauses = f"    WITH CHECK ({body})"
    elif verb == "UPDATE":
        clauses = f"    USING      ({body})\n    WITH CHECK ({body})"
    else:  # SELECT / DELETE
        clauses = f"    USING ({body})"

    # nosemgrep: closed templated DDL over IR-controlled identifiers; body is a
    # param-free policy fragment from the predicate compiler's policy mode
    # (current_setting GUC reads + literals inlined via _inline_sql_literal).
    return f"CREATE POLICY {policy_name} ON {table}\n    AS PERMISSIVE\n    FOR {verb}\n{clauses}"


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
