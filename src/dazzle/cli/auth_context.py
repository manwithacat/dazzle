"""Per-invocation state the ``dazzle auth`` callback hands to its sub-commands.

A leaf below ``cli/auth.py`` and ``cli/auth_connection.py`` so the connection sub-app,
which ``auth.py`` mounts, can read the parent's ``--database-url`` without importing
``auth.py`` (a cycle) and without walking a click context (the core wheel has no click:
typer vendors its own, and the v0.120.0 PyPI smoke test failed on that import).
"""

_database_url_override: str | None = None


def set_database_url_override(database_url: str | None) -> None:
    """Record the ``--database-url`` the ``dazzle auth`` callback received."""
    global _database_url_override  # noqa: PLW0603  # CLI callback storage, per-invocation
    _database_url_override = database_url or None


def database_url_override() -> str | None:
    """The recorded ``--database-url``, or ``None`` when the callback had none."""
    return _database_url_override
