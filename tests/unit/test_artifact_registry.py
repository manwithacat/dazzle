"""#1495 follow-on — the DB-artifact registry is the single source of truth.

`in_baseline_tables()` must reproduce exactly the 30 framework tables that
`ensure_framework_schema` creates (the ADR-0044 in-scope set). This pins the
collapse: framework_schema_snapshot.IN_SCOPE_TABLES becomes registry-derived.
"""

from __future__ import annotations

from dazzle.db.artifact_registry import (
    DB_ARTIFACTS,
    Artifact,
    ArtifactClass,
    in_baseline_tables,
)

# The 30 framework tables, verbatim from framework_schema_snapshot.IN_SCOPE_TABLES.
_EXPECTED_BASELINE = frozenset(
    {
        "_dazzle_params",
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
        "process_runs",
        "process_tasks",
        "_dazzle_audit_log",
        "_dazzle_atomic_audit",
        "dazzle_files",
        "refresh_tokens",
        "devices",
        "_grants",
        "_grant_events",
        "_dazzle_otp_codes",
        "_dazzle_recovery_codes",
        "_dazzle_event_inbox",
        "_dazzle_event_outbox",
    }
)


def test_in_baseline_tables_reproduces_the_in_scope_set() -> None:
    assert in_baseline_tables() == _EXPECTED_BASELINE


def test_every_artifact_is_well_formed() -> None:
    seen: set[str] = set()
    for a in DB_ARTIFACTS:
        assert isinstance(a, Artifact)
        # boot_ddl_gated implies an independent boot path to gate.
        if a.boot_ddl_gated:
            assert a.boot_entry is not None, f"{a.name}: gated but no boot_entry"
        # orchestrator-only rows declare no self-gate.
        if a.boot_entry is None and not a.is_pattern:
            assert a.boot_ddl_gated is False, f"{a.name}: no boot_entry yet gated"
        # known-ungated debt: a registered independent boot path, NOT yet gated,
        # carrying a tracking issue (#1495-sibling).
        if a.known_ungated_issue is not None:
            assert a.boot_entry is not None, f"{a.name}: ungated-debt but no boot_entry"
            assert a.boot_ddl_gated is False, f"{a.name}: marked debt yet claims gated"
            assert a.known_ungated_issue.startswith("#"), f"{a.name}: issue ref must be #NNNN"
        # exact (non-pattern) framework names are unique.
        if not a.is_pattern and a.cls is ArtifactClass.FRAMEWORK_INTERNAL:
            assert a.name not in seen, f"duplicate framework artifact {a.name}"
            seen.add(a.name)
