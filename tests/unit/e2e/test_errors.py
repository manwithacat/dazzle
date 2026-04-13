"""Unit tests for the e2e exception hierarchy."""

import pytest

from dazzle.core.errors import DazzleError
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


class TestE2EErrorHierarchy:
    def test_e2e_error_inherits_from_dazzle_error(self) -> None:
        assert issubclass(E2EError, DazzleError)

    def test_runner_level_errors_inherit_from_e2e_error(self) -> None:
        assert issubclass(ModeAlreadyRunningError, E2EError)
        assert issubclass(UnknownModeError, E2EError)
        assert issubclass(ModeLaunchError, E2EError)
        assert issubclass(RuntimeFileTimeoutError, E2EError)
        assert issubclass(HealthCheckTimeoutError, E2EError)
        assert issubclass(RunnerTeardownError, E2EError)

    def test_snapshot_errors_inherit_from_snapshot_error(self) -> None:
        assert issubclass(SnapshotError, E2EError)
        assert issubclass(PgDumpNotInstalledError, SnapshotError)
        assert issubclass(BaselineKeyError, SnapshotError)
        assert issubclass(BaselineBuildError, SnapshotError)
        assert issubclass(BaselineRestoreError, SnapshotError)

    def test_error_instances_carry_message(self) -> None:
        err = ModeAlreadyRunningError("lock held by pid 1234")
        assert "1234" in str(err)

    def test_errors_can_be_caught_as_e2e_error(self) -> None:
        with pytest.raises(E2EError):
            raise BaselineRestoreError("pg_restore exit 1")

    def test_errors_can_be_caught_as_dazzle_error(self) -> None:
        with pytest.raises(DazzleError):
            raise PgDumpNotInstalledError("pg_dump not on PATH")
