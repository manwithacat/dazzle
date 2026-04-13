"""Dazzle e2e environment primitives.

Shared runner, mode registry, snapshot/restore, and lifecycle management for
launching example Dazzle apps as live test environments.

v1 exposes Mode A (developer one-shot) + the snapshot primitive. Modes B, C,
and D are sketched in the design spec but not wired in v1.
"""

from dazzle.e2e.errors import (
    BaselineBuildError,
    BaselineKeyError,
    BaselineRestoreError,
    E2EError,
    HealthCheckTimeoutError,
    ModeAlreadyRunningError,
    ModeLaunchError,
    PgDumpNotInstalledError,
    RunnerTeardownError,
    RuntimeFileTimeoutError,
    SnapshotError,
    UnknownModeError,
)

__all__ = [
    "BaselineBuildError",
    "BaselineKeyError",
    "BaselineRestoreError",
    "E2EError",
    "HealthCheckTimeoutError",
    "ModeAlreadyRunningError",
    "ModeLaunchError",
    "PgDumpNotInstalledError",
    "RunnerTeardownError",
    "RuntimeFileTimeoutError",
    "SnapshotError",
    "UnknownModeError",
]
