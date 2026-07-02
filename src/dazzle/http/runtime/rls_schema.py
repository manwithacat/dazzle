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
    parameter`` abort. The read is also wrapped in ``NULLIF(.., '')`` so the
    pooled empty-string GUC state collapses to NULL → deny, never a raising
    ``''::uuid`` (a 500 instead of a clean deny, #1400).
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

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import TenancyMode
from dazzle.http.runtime.query_builder import quote_identifier

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.http.runtime.predicate_compiler import EntityTypeResolver
    from dazzle.http.specs.entity import EntitySpec as _BackEntitySpec

# Fixed framework GUC name for the per-transaction tenant context (companion §6).
# This is deliberately INDEPENDENT of the app's partition_key column: the runtime
# (``pg_backend._set_tenant_context``) always sets ``dazzle.tenant_id``, so the
# fence must always READ ``dazzle.tenant_id`` — only the fenced *column* varies
# per app. Tying the GUC name to the partition_key (e.g. ``dazzle.org_id``) would
# make the fence read a GUC the runtime never sets → silent total-deny (C-2).
# pg_backend imports this same constant so the two never drift.
TENANT_GUC = "dazzle.tenant_id"

# Fixed framework GUC name for the host-resolved tenant id (#1394). This is the
# ``request.state.tenant.id`` from the #1289 ``tenant_host`` resolver — DELIBERATELY
# distinct from ``TENANT_GUC`` (``dazzle.tenant_id``), which carries the RLS
# row-tenancy discriminator. The two CAN diverge (a host-tenant app need not use
# RLS row-tenancy, and vice-versa), so ``current_tenant`` scope predicates must
# never read ``dazzle.tenant_id`` — that could bind the wrong tenant. The runtime
# (``pg_backend._set_host_tenant_context``) sets this from the host tenant context
# var; a scope policy body reads ``current_setting('dazzle.host_tenant_id', true)``.
# An unset GUC reads NULL → the predicate fails closed (deny), mirroring the user
# GUCs. Both sides derive the name from THIS constant so they can never drift.
HOST_TENANT_GUC = "dazzle.host_tenant_id"

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

# Closed udt_name → cast-type map for :func:`physical_cast_overrides`. Only
# udt names in this map produce an override; anything else falls back to the
# logical resolver (fail-safe: never emit an unrecognised token into a
# ``::<type>`` cast). The values feed ``_guc_read``'s ``::{pg_type}`` channel,
# so this map must stay closed — no passthrough of raw catalog strings.
_UDT_TO_CAST: dict[str, str] = {
    "text": "text",
    "varchar": "text",
    "bpchar": "text",
    "citext": "text",
    "uuid": "uuid",
    "bool": "boolean",
    "int2": "integer",
    "int4": "integer",
    "int8": "bigint",
    "float4": "real",
    "float8": "double precision",
    "numeric": "numeric",
    "date": "date",
    "timestamp": "timestamp",
    "timestamptz": "timestamptz",
    "json": "json",
    "jsonb": "jsonb",
}


def physical_cast_overrides(rows: Any) -> dict[tuple[str, str], str]:
    """Normalise ``information_schema.columns`` rows into a cast-override map.

    ``rows`` is an iterable of ``SELECT table_name, column_name, udt_name FROM
    information_schema.columns WHERE table_schema = current_schema()`` results.
    Both row shapes in the framework are accepted: mappings (the ``dazzle db``
    CLI's psycopg connection uses dict rows) and sequences (SQLAlchemy ``Row``).
    Returns ``{(table, column): cast_type}`` for every column whose ``udt_name``
    is in the closed :data:`_UDT_TO_CAST` map; unrecognised udts are skipped so
    the logical resolver stays in charge.

    Why this exists (#1531): the scope-policy GUC cast must match the PHYSICAL
    column type, not the logical schema. When the two drift — e.g. a
    ``belongs_to`` column created TEXT pre-#1522 while the logical schema now
    says uuid — a logical-only cast produces ``text = uuid`` and ``CREATE
    POLICY`` fails on the production upgrade path.
    """
    overrides: dict[tuple[str, str], str] = {}
    for row in rows:
        if isinstance(row, Mapping):
            table_name, column_name, udt_name = (
                row["table_name"],
                row["column_name"],
                row["udt_name"],
            )
        else:
            table_name, column_name, udt_name = row[0], row[1], row[2]
        cast = _UDT_TO_CAST.get(str(udt_name).lower())
        if cast is not None:
            overrides[(str(table_name), str(column_name))] = cast
    return overrides


def build_all_rls_ddl(
    appspec: Any,
    entities: list[Any],
    *,
    physical_types: dict[tuple[str, str], str] | None = None,
) -> list[str]:
    """Build the full RLS DDL set for an appspec — the shared partitioner (Phase D).

    The single, DB-free source of the tenant fence + per-verb scope / baseline
    policy DDL. Both the dev ``create_all`` apply
    (:meth:`dazzle.http.runtime.server.DazzleBackendApp._apply_rls_policies`) and
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
        physical_types: Optional ``{(table, column): cast_type}`` map from the
            LIVE database (see :func:`physical_cast_overrides`). When provided,
            a column's GUC cast is resolved from the physical column type, with
            the logical resolver as fallback for columns not in the map — so a
            policy never casts against a type the table doesn't actually have
            (#1531). DB-free consumers (``dazzle inspect rls``, the drift gate,
            unit tests) omit it and get pure logical resolution, unchanged.

    Returns:
        A flat list of idempotent DDL statements. Empty list when there is no
        tenancy, the isolation mode is not ``shared_schema``, or no entity is
        tenant-scoped — so the builder is a no-op for every non-tenant app and
        for every other isolation mode, matching the old apply behaviour.

    Raises:
        ValueError: A scoped entity carries scope rules but ``appspec.fk_graph``
            is ``None`` (cannot compile the policy body).
    """
    from dazzle.http.runtime.predicate_compiler import build_entity_type_resolver
    from dazzle.http.runtime.sa_schema import scoped_entity_names

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
    logical_types = build_entity_type_resolver(entities)
    entity_types: EntityTypeResolver = logical_types
    if physical_types:
        overrides = physical_types

        def _physical_first(entity_name: str, field_name: str) -> str:
            physical = overrides.get((entity_name, field_name))
            if physical is None:
                return logical_types(entity_name, field_name)
            try:
                logical = logical_types(entity_name, field_name)
            except ValueError:
                logical = None
            if logical is not None and logical != physical:
                logger.warning(
                    "RLS cast for %s.%s follows the live column type %r; the logical "
                    "schema says %r — run `dazzle db revision` to generate the "
                    "column-type migration and close the drift (#1531)",
                    entity_name,
                    field_name,
                    physical,
                    logical,
                )
            return physical

        entity_types = _physical_first

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


@dataclass(frozen=True)
class PolicyDescriptor:
    """One expected RLS policy on a tenant-scoped table — the shape-level view.

    This is the shared, DB-free description of a single policy the framework
    generates for a tenant-scoped entity. It is the *shape* (name + table +
    command verb + permissive/restrictive + provenance), deliberately NOT the
    compiled predicate body — exactly the granularity the inspector reports and
    the drift gate compares against live ``pg_policies`` (per the plan's
    "shape-based, not qual-text" contract).

    Both ``dazzle inspect rls`` (Phase D Task 3) and the RLS drift gate
    (``detect_rls_drift``, Task 4) consume this so the "expected policy set"
    never diverges between the surface that shows it and the gate that verifies
    it.

    Attributes:
        entity: The entity / table name the policy is on (unquoted IR name).
        name: The policy name — ``tenant_fence`` / ``tenant_baseline`` (Phase B)
            or ``scope_select`` / ``scope_insert`` / ``scope_update`` /
            ``scope_delete`` (Phase C).
        cmd: The SQL command the policy applies to — ``ALL`` for the fence /
            baseline, or ``SELECT`` / ``INSERT`` / ``UPDATE`` / ``DELETE`` for a
            per-verb scope policy. Matches ``pg_policies.cmd`` — the view returns
            human-readable ``ALL`` for a ``FOR ALL`` policy (the underlying
            ``pg_policy.polcmd`` catalog uses ``*``, but the view translates it,
            so the drift comparison needs no normalization).
        permissive: ``True`` for a ``PERMISSIVE`` policy (baseline + every
            scope policy), ``False`` for the ``RESTRICTIVE`` ``tenant_fence``.
            Matches ``pg_policies.permissive`` (``'PERMISSIVE'`` / ``'RESTRICTIVE'``).
        source: Provenance — ``"framework"`` for the fence / baseline (a fixed
            framework construction), ``"scope-rule"`` for a per-verb policy
            derived from a DSL ``scope:`` rule.
    """

    entity: str
    name: str
    cmd: str
    permissive: bool
    source: str


# SQL verb per scope-policy name — the inverse of :data:`_SCOPE_POLICY_NAME`,
# used by :func:`describe_rls_policies` to attach the right ``cmd`` to each
# scope policy a scoped entity gets.
_SCOPE_NAME_TO_VERB: dict[str, str] = {
    "scope_select": "SELECT",
    "scope_insert": "INSERT",
    "scope_update": "UPDATE",
    "scope_delete": "DELETE",
}


def describe_rls_policies(appspec: Any, entities: list[Any]) -> list[PolicyDescriptor]:
    """Describe the expected RLS policy set for an appspec — the shared shape view.

    The DB-free, shape-level companion to :func:`build_all_rls_ddl`: instead of
    DDL strings it returns one :class:`PolicyDescriptor` per policy the framework
    *would* create, computed from the SAME per-entity partition logic
    (``scoped_entity_names`` + the scoped-vs-flat split). ``dazzle inspect rls``
    lists these; the drift gate compares them against live ``pg_policies``.

    Per tenant-scoped entity:

    - **scoped entity** (≥1 ``access.scopes`` rule) → the restrictive
      ``tenant_fence`` (framework) plus one permissive ``scope_<verb>`` per
      verb that has ≥1 scope rule (read + list both → ``scope_select``); the
      permissive ``tenant_baseline`` is intentionally absent.
    - **tenant-flat entity** (no scope rules) → the restrictive ``tenant_fence``
      (framework) + the permissive ``tenant_baseline`` (framework).

    Returns an empty list for every non-tenant app, every non-``shared_schema``
    isolation mode, and every app with no tenant-scoped entity — matching
    :func:`build_all_rls_ddl`.

    Args:
        appspec: The application IR (``.tenancy``, ``.domain.entities``).
        entities: The converted back-spec entities (each with ``.name`` and an
            optional ``.access.scopes``) — the list iterated for the
            scoped-vs-flat partition, mirroring :func:`build_all_rls_ddl`.

    Returns:
        A flat list of :class:`PolicyDescriptor`, ordered by entity name then by
        a stable per-entity policy order (fence first, then baseline or the
        scope policies in SELECT/INSERT/UPDATE/DELETE order).
    """
    from dazzle.http.runtime.sa_schema import scoped_entity_names

    tenancy = getattr(appspec, "tenancy", None)
    if tenancy is None or tenancy.isolation.mode != TenancyMode.SHARED_SCHEMA:
        return []

    pk = tenancy.isolation.partition_key
    scoped = scoped_entity_names(appspec.domain.entities, pk)
    if not scoped:
        return []

    descriptors: list[PolicyDescriptor] = []
    for entity in sorted((e for e in entities if e.name in scoped), key=lambda e: e.name):
        access = getattr(entity, "access", None)
        has_scopes = access is not None and bool(getattr(access, "scopes", None))

        # The restrictive tenant fence is present on EVERY tenant-scoped table
        # (both scoped and tenant-flat) — see _enable_force_fence.
        descriptors.append(
            PolicyDescriptor(
                entity=entity.name,
                name="tenant_fence",
                cmd="ALL",
                permissive=False,
                source="framework",
            )
        )

        if not has_scopes:
            # Tenant-flat → permissive framework baseline.
            descriptors.append(
                PolicyDescriptor(
                    entity=entity.name,
                    name="tenant_baseline",
                    cmd="ALL",
                    permissive=True,
                    source="framework",
                )
            )
            continue

        # Scoped → one permissive scope policy per verb that has ≥1 rule. The
        # verb set per entity is computed exactly as build_rls_scope_policy_ddl
        # does: read + list both fold into SELECT.
        _op_value_to_verb = {
            "read": "SELECT",
            "list": "SELECT",
            "create": "INSERT",
            "update": "UPDATE",
            "delete": "DELETE",
        }
        covered_verbs: set[str] = set()
        for rule in access.scopes:  # type: ignore[union-attr]  # has_scopes guards access is not None
            op = rule.operation
            op_val = op.value if hasattr(op, "value") else str(op)
            verb = _op_value_to_verb.get(op_val)
            if verb is not None:
                covered_verbs.add(verb)

        # Emit in the same stable order build_rls_scope_policy_ddl uses.
        for policy_name, verb in _SCOPE_NAME_TO_VERB.items():
            if verb in covered_verbs:
                descriptors.append(
                    PolicyDescriptor(
                        entity=entity.name,
                        name=policy_name,
                        cmd=verb,
                        permissive=True,
                        source="scope-rule",
                    )
                )

    return descriptors


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
    # NULLIF(.., '') collapses the pooled empty-string GUC state to NULL → deny,
    # rather than letting a bare ``''::uuid`` RAISE during policy evaluation (a 500
    # instead of a clean deny, #1400). The runtime only ever set_config()s a real
    # tenant id or no-ops (NULL), but a placeholder GUC on a pooled connection can
    # revert to '' across leases — fail-closed must cover that state too. Mirrors
    # the host-GUC hardening in ``predicate_compiler._guc_read_host_tenant`` (#1394).
    fence_body = f"{col} = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
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
    entity: _BackEntitySpec,
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
    :func:`~dazzle.http.runtime.predicate_compiler.compile_predicate_policy`:

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

    A scope rule whose body can't be compiled to a policy (a relational
    EXISTS-join / dotted-junction ``via`` binding, or an unresolvable GUC cast —
    not supported in policy mode) does NOT abort (#1447): the verb it governs
    degrades to a permissive within-tenant policy (fence-only) and a warning is
    logged, leaving that verb's scope to the app layer. The ``tenant_fence`` always
    applies, so cross-tenant isolation holds regardless.

    Raises:
        ValueError: If *entity* has no scope rules (use
            :func:`build_rls_policy_ddl` for tenant-flat entities).
    """
    from dazzle.http.runtime.predicate_compiler import compile_predicate_policy

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
    # Verbs whose scope is not RLS-policy-expressible (a relational EXISTS-join /
    # dotted-junction binding, or an unresolvable GUC cast — #1447). Such a verb
    # degrades to a permissive within-tenant policy (fence-only); its scope stays
    # app-layer. We can't emit only the *compilable* OR-branches for the verb: RLS
    # policies are user-agnostic, so dropping the relational branch would wrongly
    # deny a persona matched ONLY by that branch (e.g. `parent` via ParentContact).
    degraded_verbs: dict[str, list[str]] = {}
    for rule in access.scopes:
        op = rule.operation
        op_val = op.value if hasattr(op, "value") else str(op)
        verb = _op_value_to_verb.get(op_val)
        if verb is None:  # pragma: no cover - the operation set is closed
            continue
        try:
            body = compile_predicate_policy(
                rule.predicate, entity.name, fk_graph, entity_types=entity_types
            )
        except ValueError as exc:
            personas = ", ".join(getattr(rule, "personas", None) or []) or "*"
            degraded_verbs.setdefault(verb, []).append(f"{op_val} (as {personas})")
            logger.warning(
                "RLS: scope rule %s.%s (as %s) is not RLS-policy-expressible (%s) — "
                "deferring the %s-verb scope on %s to the app layer; the tenant_fence "
                "still applies (cross-tenant isolation holds).",
                entity.name,
                op_val,
                personas,
                exc,
                verb,
                entity.name,
            )
            continue
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

        if verb in degraded_verbs:
            # At least one rule for this verb isn't RLS-expressible (#1447). The
            # whole verb falls back to a permissive within-tenant policy so the
            # tenant_fence (restrictive, ANDed) is the only DB gate; the app-layer
            # scope filter remains the authority for this verb. Permissive-true is
            # NOT a weakening: cross-tenant rows are still denied by the fence.
            statements.append(_scope_policy_create(policy_name, table, verb, "true"))
            continue

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
