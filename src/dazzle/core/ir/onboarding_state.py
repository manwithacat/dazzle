"""``OnboardingState`` framework-injected entity (v0.71.1).

Per-user progression state for the guided-onboarding feature shipped in
v0.71.0. The entity is auto-generated whenever the project declares at
least one ``guide`` block — apps that don't use guides don't pay the
table cost.

One row per ``(user_id, guide_name, guide_version)`` triple. Versioning
lets a guide rewrite (``guide_version`` bump) start a fresh progression
row rather than mutating the existing one, so historical state survives
spec revisions.

Field convention mirrors ``FEEDBACK_REPORT_FIELDS`` (the closest existing
prior art) — strings for user references rather than FK refs, since the
project's User entity name varies. The repository layer translates
between auth-store IDs and the string column.
"""

ONBOARDING_STATE_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    # Primary key — opaque UUID; uniqueness on (user_id, guide_name,
    # guide_version) is enforced at the repository layer (UPSERT logic).
    ("id", "uuid", ("pk",), None),
    # User reference — stored as a string ID to stay decoupled from the
    # project's User entity name (mirrors FeedbackReport.reported_by).
    ("user_id", "str(200)", ("required",), None),
    # Guide identity — name + version. Bumping the version means the
    # guide author rewrote the flow; this row tracks the OLD version's
    # progression, and a new row is created for the new version.
    ("guide_name", "str(200)", ("required",), None),
    ("guide_version", "int", ("required",), "1"),
    # Progression state — current step (None = not started or
    # completed), plus arrays of completed + dismissed step IDs.
    # Arrays stored as JSON text (text + json.dumps round-trip);
    # avoids a join table for what's a small bounded list per row.
    ("current_step", "str(200)", (), None),
    ("completed_steps", "text", (), "[]"),
    ("dismissed_steps", "text", (), "[]"),
    # Lifecycle timestamps.
    ("started_at", "datetime", (), "now"),
    ("completed_at", "datetime", (), None),
    # Optional metadata — free-form JSON for downstream apps to stash
    # whatever context they want (e.g. last-step-fired event payload).
    ("metadata", "text", (), None),
)
