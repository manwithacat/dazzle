"""
Admin workspace entity definitions for DAZZLE IR.

Synthetic platform entities that are auto-generated for auth-enabled applications.
These give the admin workspace read-only views into system health, metrics, deploys,
process runs, and active sessions.

Part of Issue #686 — universal admin workspace for auth-enabled Dazzle apps.

Field tuple format: (name, type_str, modifiers_tuple, default_value_or_None)
Follows the same convention as FEEDBACK_REPORT_FIELDS in ir/feedback_widget.py
and AI_JOB_FIELDS in ir/llm.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

SYSTEM_HEALTH_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("component", "str(100)", ("required",), None),
    ("status", "enum[healthy,degraded,unhealthy]", ("required",), None),
    ("message", "text", (), None),
    ("latency_ms", "float", (), None),
    ("checked_at", "datetime", (), "now"),
)

SYSTEM_METRIC_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("name", "str(200)", ("required",), None),
    ("value", "float", ("required",), None),
    ("unit", "str(50)", (), None),
    ("tags", "text", (), None),
    ("bucket_start", "datetime", (), None),
    ("resolution", "str(10)", (), None),
)

DEPLOY_HISTORY_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("version", "str(50)", ("required",), None),
    ("previous_version", "str(50)", (), None),
    ("deployed_by", "str(200)", (), None),
    ("deployed_at", "datetime", (), "now"),
    (
        "status",
        "enum[pending,in_progress,completed,failed,rolled_back]",
        (),
        "pending",
    ),
    ("rollback_of", "str(50)", (), None),
)

PROCESS_RUN_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("process_name", "str(200)", ("required",), None),
    (
        "status",
        "enum[pending,running,waiting,suspended,compensating,completed,failed,cancelled]",
        (),
        "pending",
    ),
    ("started_at", "datetime", (), None),
    ("completed_at", "datetime", (), None),
    ("current_step", "str(200)", (), None),
    ("error", "text", (), None),
)

SESSION_INFO_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("id", "uuid", ("pk",), None),
    ("user_id", "str(200)", ("required",), None),
    ("email", "str(200)", (), None),
    ("created_at", "datetime", (), "now"),
    ("expires_at", "datetime", (), None),
    ("ip_address", "str(45)", (), None),
    ("user_agent", "str(500)", (), None),
    ("is_active", "bool", (), "true"),
)

# ---------------------------------------------------------------------------
# Virtual entity set — entities with no backing DB table (read from runtime
# state rather than persisted rows).  Used by the linker to skip migrations.
# ---------------------------------------------------------------------------

VIRTUAL_ENTITY_NAMES: frozenset[str] = frozenset(
    {
        "SystemHealth",
        "SystemMetric",
        "ProcessRun",
    }
)

# ---------------------------------------------------------------------------
# Consolidated entity definitions
#
# Each entry: (name, title, intent, fields_tuple, patterns, profile_gate)
#
#   name          — PascalCase entity name
#   title         — Human-readable title
#   intent        — Purpose statement for LLM cognition
#   fields_tuple  — One of the FIELDS constants above
#   patterns      — list[str] of pattern tags (e.g. ["system", "monitoring"])
#   profile_gate  — None (all profiles) | "standard" (standard + strict only)
# ---------------------------------------------------------------------------

ADMIN_ENTITY_DEFS: tuple[
    tuple[
        str,
        str,
        str,
        tuple[tuple[str, str, tuple[str, ...], str | None], ...],
        list[str],
        str | None,
    ],
    ...,
] = (
    (
        "SystemHealth",
        "System Health",
        "Live health-check status for each platform component",
        SYSTEM_HEALTH_FIELDS,
        ["system", "monitoring"],
        None,  # available on all profiles
    ),
    (
        "SystemMetric",
        "System Metric",
        "Time-series platform metrics collected by the runtime",
        SYSTEM_METRIC_FIELDS,
        ["system", "monitoring"],
        None,  # available on all profiles
    ),
    (
        "DeployHistory",
        "Deploy History",
        "Immutable record of every deployment with rollback lineage",
        DEPLOY_HISTORY_FIELDS,
        ["system", "audit"],
        None,  # available on all profiles
    ),
    (
        "ProcessRun",
        "Process Run",
        "Execution record for each workflow process run",
        PROCESS_RUN_FIELDS,
        ["system", "audit"],
        "standard",  # standard + strict only
    ),
    (
        "SessionInfo",
        "Session Info",
        "Active and historical user session records for security audit",
        SESSION_INFO_FIELDS,
        ["system", "audit"],
        "standard",  # standard + strict only
    ),
)
