"""Exception hierarchy for the e2e environment package.

All e2e errors inherit from DazzleError so they surface consistently via
the existing CLI error rendering path.
"""

from dazzle.core.errors import DazzleError


class E2EError(DazzleError):
    """Base for e2e environment errors."""


# Runner-level errors ---------------------------------------------------------


class ModeAlreadyRunningError(E2EError):
    """Another Mode A instance holds the lock file for this example app."""


class UnknownModeError(E2EError):
    """get_mode(name) called with a name not in MODE_REGISTRY."""


class ModeLaunchError(E2EError):
    """subprocess.Popen raised while launching dazzle serve."""


class RuntimeFileTimeoutError(E2EError):
    """.dazzle/runtime.json did not appear within the budget."""


class HealthCheckTimeoutError(E2EError):
    """{api_url}/docs did not return 200 within the budget."""


class RunnerTeardownError(E2EError):
    """Runner __aexit__ failed to terminate subprocess or release lock.

    This is logged but never raised — teardown failures must not mask caller
    exceptions. Callers should not catch this type directly; it exists for
    telemetry and test assertions only.
    """


# Snapshot-level errors -------------------------------------------------------


class SnapshotError(E2EError):
    """Base for snapshot/restore errors."""


class PgDumpNotInstalledError(SnapshotError):
    """pg_dump or pg_restore is missing from PATH."""


class BaselineKeyError(SnapshotError):
    """Cannot compute a baseline key (missing Alembic config, etc.)."""


class BaselineBuildError(SnapshotError):
    """Lazy baseline build pipeline failed (reset, upgrade, demo, or capture)."""


class BaselineRestoreError(SnapshotError):
    """pg_restore exited non-zero."""
