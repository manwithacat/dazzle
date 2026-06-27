"""Single source of truth for every database artifact the framework manages.

Each artifact declares five orthogonal facts an agent would otherwise reconstruct
from scattered ADRs + code: class, creator (where the DDL lives), boot_entry (the
independent startup path that must self-gate, or None for orchestrator-only),
owner, RLS posture, baseline membership, and boot-DDL gating. The executable
contract in tests/unit/test_db_artifact_contract.py keeps these honest.

Reference: docs/reference/db-artifacts.md · ADR-0047 · ADR-0044 (baseline mechanism).

Layer note: this module is pure data — creator/boot_entry are DOTTED STRINGS,
resolved lazily by the contract test and the inspect command, so the registry
never imports the http.* modules it names (db/ stays below http/).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactClass(StrEnum):
    FRAMEWORK_INTERNAL = "framework_internal"  # in the ADR-0044 baseline; owner-created
    EVENT_BUS_TRANSPORT = "event_bus_transport"  # {prefix}* ; excluded; self-creating
    OPS_DB = "ops_db"  # separate ops database; own lifecycle
    APP_ENTITY = "app_entity"  # per-DSL; migration-engine generated
    TENANT_REGISTRY = "tenant_registry"  # public.tenants + per-tenant schemas


class Ownership(StrEnum):
    OWNER_ROLE = "owner_role"  # dazzle_owner owns; runtime serves as non-owner
    RUNTIME_SELF = "runtime_self"  # the creating connection owns what it makes
    N_A = "n_a"


class RlsPosture(StrEnum):
    FENCED = "fenced"  # ENABLE + FORCE ROW LEVEL SECURITY
    NON_FENCED = "non_fenced"  # no RLS today
    NOT_APPLICABLE = "not_applicable"  # separate DB / transport / per-tenant


@dataclass(frozen=True)
class Artifact:
    name: str
    cls: ArtifactClass
    creator: str
    boot_entry: str | None
    owner: Ownership
    rls: RlsPosture
    in_baseline: bool
    boot_ddl_gated: bool
    notes: str = ""
    is_pattern: bool = False
    known_ungated_issue: str | None = None  # registered independent boot path that is
    # CURRENTLY ungated, tracked by a GH issue (#1495-sibling). The contract documents
    # it as debt instead of failing; flip boot_ddl_gated True + clear this when fixed.


_AUTH_CREATOR = "dazzle.http.runtime.auth.store.ensure_auth_core_tables"
_AUTH_BOOT = "dazzle.http.runtime.auth.store.AuthStore._init_db"
_ORCH = "dazzle.http.runtime.framework_schema._ensure_framework_schema_ddl"

_AUTH_TABLES = (
    "users",
    "sessions",
    "memberships",
    "organizations",
    "membership_events",
    "invitations",
    "connections",
    "connection_secret_events",
    "scim_groups",
    "scim_group_members",
    "saml_consumed_assertions",
    "password_reset_tokens",
    "magic_links",
    "email_verification_tokens",
    "user_preferences",
    "join_requests",
)


def _fw(
    name: str,
    creator: str,
    *,
    boot_entry: str | None,
    rls: RlsPosture = RlsPosture.NON_FENCED,
    notes: str = "",
    known_ungated_issue: str | None = None,
) -> Artifact:
    # A boot path is "gated" iff it exists AND is not flagged as known-ungated debt.
    gated = boot_entry is not None and known_ungated_issue is None
    return Artifact(
        name=name,
        cls=ArtifactClass.FRAMEWORK_INTERNAL,
        creator=creator,
        boot_entry=boot_entry,
        owner=Ownership.OWNER_ROLE,
        rls=rls,
        in_baseline=True,
        boot_ddl_gated=gated,
        notes=notes,
        known_ungated_issue=known_ungated_issue,
    )


DB_ARTIFACTS: tuple[Artifact, ...] = (
    # ── framework internal (in the ADR-0044 baseline) ──────────────────────
    _fw("_dazzle_params", _ORCH, boot_entry=None, notes="orchestrator-only"),
    *[_fw(t, _AUTH_CREATOR, boot_entry=_AUTH_BOOT) for t in _AUTH_TABLES],
    _fw(
        "process_runs",
        _ORCH,
        boot_entry="dazzle.core.process.pg_state.PgProcessStateStore._ensure",
    ),
    _fw(
        "process_tasks",
        _ORCH,
        boot_entry="dazzle.core.process.pg_state.PgProcessStateStore._ensure",
    ),
    _fw(
        "_dazzle_audit_log",
        "dazzle.http.runtime.audit_log.ensure_audit_log_table",
        boot_entry="dazzle.http.runtime.audit_log.AuditLogger._init_db",
    ),
    _fw(
        "_dazzle_atomic_audit",
        _ORCH,
        boot_entry=None,
        notes="orchestrator-only; lazy ensure in mutation path is no-op when table exists",
    ),
    _fw(
        "dazzle_files",
        "dazzle.http.runtime.file_storage.ensure_file_storage_tables",
        boot_entry="dazzle.http.runtime.file_storage.FileMetadataStore._init_db",
    ),
    # refresh_tokens / devices / _grants — independent boot paths, now GATED
    # (#1496/#1498/#1497 fixed: each self-gates with skip_boot_schema_ddl()).
    _fw(
        "refresh_tokens",
        "dazzle.http.runtime.token_store.ensure_refresh_token_tables",
        boot_entry="dazzle.http.runtime.token_store.TokenStore._init_db",
    ),
    _fw(
        "devices",
        "dazzle.http.runtime.device_registry.ensure_device_tables",
        boot_entry="dazzle.http.runtime.device_registry.DeviceRegistry._init_db",
    ),
    _fw(
        "_grants",
        "dazzle.http.runtime.grant_store.ensure_grant_tables",
        boot_entry="dazzle.http.runtime.grant_store.GrantStore._ensure_tables",
    ),
    _fw(
        "_grant_events",
        "dazzle.http.runtime.grant_store.ensure_grant_tables",
        boot_entry="dazzle.http.runtime.grant_store.GrantStore._ensure_tables",
    ),
    # otp / recovery — truly orchestrator-only (no independent boot path).
    _fw("_dazzle_otp_codes", "dazzle.http.runtime.otp_store.ensure_otp_tables", boot_entry=None),
    _fw(
        "_dazzle_recovery_codes",
        "dazzle.http.runtime.recovery_codes.ensure_recovery_code_tables",
        boot_entry=None,
    ),
    _fw(
        "_dazzle_event_inbox",
        "dazzle.http.events.inbox.EventInbox.create_table",
        boot_entry="dazzle.http.events.inbox.EventInbox.create_table",
    ),
    _fw(
        "_dazzle_event_outbox",
        "dazzle.http.events.outbox.EventOutbox.create_table",
        boot_entry="dazzle.http.events.outbox.EventOutbox.create_table",
    ),
    # _dazzle_outbox (channel delivery) — #1499 fixed: added to the ADR-0044 baseline
    # (orchestrator delegates to ensure_outbox_table) and the boot path now self-gates.
    _fw(
        "_dazzle_outbox",
        "dazzle.http.channels.outbox.ensure_outbox_table",
        boot_entry="dazzle.http.channels.outbox.OutboxRepository._ensure_table",
    ),
    # ── event-bus transport (excluded; dynamic prefix; self-creating) ──────
    *[
        Artifact(
            name=n,
            cls=ArtifactClass.EVENT_BUS_TRANSPORT,
            creator="dazzle.http.events.postgres_bus.PostgresBus._create_tables",
            boot_entry=None,
            owner=Ownership.RUNTIME_SELF,
            rls=RlsPosture.NOT_APPLICABLE,
            in_baseline=False,
            boot_ddl_gated=False,
            notes="dynamic {prefix}; excluded from baseline",
            is_pattern=True,
        )
        for n in ("{prefix}events", "{prefix}consumer_offsets", "{prefix}dlq")
    ],
    # ── ops database (separate DB; own lifecycle) ──────────────────────────
    # Represented as ONE class-descriptor row: the ops tables (ops_credentials,
    # health_checks, api_calls, analytics_events, event_log, retention_config,
    # deployment_history, spec_versions, …) live on a SEPARATE database
    # (ops_integration) the app owns, created across several stores
    # (ops_database / deploy_history / spec_versioning). They are NOT app-DB
    # framework tables and not subject to the non-owner RLS posture, so the
    # completeness sweep allowlists their modules rather than policing them.
    Artifact(
        name="<ops_integration tables>",
        cls=ArtifactClass.OPS_DB,
        creator="dazzle.http.runtime.ops_database",
        boot_entry=None,
        owner=Ownership.RUNTIME_SELF,
        rls=RlsPosture.NOT_APPLICABLE,
        in_baseline=False,
        boot_ddl_gated=False,
        notes="separate ops_integration DB; own lifecycle (ops_database / "
        "deploy_history / spec_versioning stores)",
        is_pattern=True,
    ),
    # ── dynamic classes (described, not enumerated) ────────────────────────
    Artifact(
        name="<app entities>",
        cls=ArtifactClass.APP_ENTITY,
        creator="dazzle.db.migration_engine.generate_revision",
        boot_entry=None,
        owner=Ownership.OWNER_ROLE,
        rls=RlsPosture.FENCED,
        in_baseline=False,
        boot_ddl_gated=False,
        notes="per-DSL; created by alembic migrations the engine generates; "
        "tenant-scoped entities are RLS-fenced",
        is_pattern=True,
    ),
    Artifact(
        name="public.tenants / <tenant schemas>",
        cls=ArtifactClass.TENANT_REGISTRY,
        creator="dazzle.http.runtime.tenant",
        boot_entry=None,
        owner=Ownership.OWNER_ROLE,
        rls=RlsPosture.NOT_APPLICABLE,
        in_baseline=False,
        boot_ddl_gated=False,
        notes="tenant registry + per-tenant schemas; separate lifecycle",
        is_pattern=True,
    ),
)


def in_baseline_tables() -> frozenset[str]:
    """THE single source of the in-scope framework table set (ADR-0044)."""
    return frozenset(a.name for a in DB_ARTIFACTS if a.in_baseline and not a.is_pattern)


def framework_boot_entries() -> tuple[Artifact, ...]:
    """Artifacts with an independent startup path (gated or tracked-ungated debt)."""
    return tuple(a for a in DB_ARTIFACTS if a.boot_entry is not None)


def concrete_creators() -> frozenset[str]:
    """Every concrete DDL-issuing dotted-ref the registry accounts for."""
    refs: set[str] = set()
    for a in DB_ARTIFACTS:
        refs.add(a.creator)
        if a.boot_entry is not None:
            refs.add(a.boot_entry)
    return frozenset(refs)
