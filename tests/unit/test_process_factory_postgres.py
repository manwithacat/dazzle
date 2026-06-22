"""TDD tests for Task 6: PostgresProcessAdapter factory wiring.

Covers:
- _detect_backend returns "postgres" when DATABASE_URL is set (no Temporal/Redis).
- Precedence: DATABASE_URL wins over REDIS_URL (both set → "postgres").
- create_adapter with explicit backend="postgres" returns PostgresProcessAdapter.
- ProcessConfig carries PostgresProcessConfig with dsn field.
"""

import pytest

_PG = "postgresql://localhost:5432/testdb"
_REDIS = "redis://localhost:6379/0"


class TestDetectBackendPostgres:
    """_detect_backend precedence: Temporal > Postgres > EventBus > error."""

    def test_database_url_only_detects_postgres(self, monkeypatch):
        """DATABASE_URL set, no REDIS_URL, no Temporal → 'postgres'."""
        monkeypatch.setenv("DATABASE_URL", _PG)
        monkeypatch.delenv("REDIS_URL", raising=False)

        from dazzle.core.process.factory import ProcessConfig, _detect_backend

        backend = _detect_backend(ProcessConfig())
        assert backend == "postgres"

    def test_postgres_wins_over_eventbus(self, monkeypatch):
        """Both DATABASE_URL and REDIS_URL set → 'postgres' (higher precedence)."""
        monkeypatch.setenv("DATABASE_URL", _PG)
        monkeypatch.setenv("REDIS_URL", _REDIS)

        from dazzle.core.process.factory import ProcessConfig, _detect_backend

        backend = _detect_backend(ProcessConfig())
        assert backend == "postgres"

    def test_no_backend_available_raises(self, monkeypatch):
        """Neither DATABASE_URL nor REDIS_URL → ValueError."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)

        from dazzle.core.process.factory import ProcessConfig, _detect_backend

        with pytest.raises(ValueError, match="No process backend"):
            _detect_backend(ProcessConfig())

    def test_redis_only_still_detects_eventbus(self, monkeypatch):
        """Only REDIS_URL set (no DATABASE_URL) → 'eventbus' (unchanged path)."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("REDIS_URL", _REDIS)

        from dazzle.core.process.factory import ProcessConfig, _detect_backend

        backend = _detect_backend(ProcessConfig())
        assert backend == "eventbus"


class TestCreateAdapterPostgres:
    """create_adapter with backend='postgres' returns PostgresProcessAdapter."""

    def test_explicit_postgres_backend(self):
        """Explicit backend='postgres' with dsn → PostgresProcessAdapter."""
        from dazzle.core.process.factory import (
            PostgresProcessConfig,
            ProcessConfig,
            create_adapter,
        )
        from dazzle.core.process.postgres_adapter import PostgresProcessAdapter

        config = ProcessConfig(backend="postgres", postgres=PostgresProcessConfig(dsn=_PG))
        adapter = create_adapter(config)
        assert isinstance(adapter, PostgresProcessAdapter)

    def test_postgres_config_dsn_field(self):
        """PostgresProcessConfig carries dsn field defaulting to None."""
        from dazzle.core.process.factory import PostgresProcessConfig

        cfg = PostgresProcessConfig()
        assert cfg.dsn is None

        cfg2 = PostgresProcessConfig(dsn=_PG)
        assert cfg2.dsn == _PG

    def test_process_config_has_postgres_field(self):
        """ProcessConfig has a postgres: PostgresProcessConfig field."""
        from dazzle.core.process.factory import PostgresProcessConfig, ProcessConfig

        config = ProcessConfig()
        assert hasattr(config, "postgres")
        assert isinstance(config.postgres, PostgresProcessConfig)

    def test_postgres_dsn_fallback_to_env(self, monkeypatch):
        """When dsn is None, factory reads DATABASE_URL from env."""
        monkeypatch.setenv("DATABASE_URL", _PG)

        from dazzle.core.process.factory import PostgresProcessConfig, ProcessConfig, create_adapter
        from dazzle.core.process.postgres_adapter import PostgresProcessAdapter

        config = ProcessConfig(backend="postgres", postgres=PostgresProcessConfig(dsn=None))
        adapter = create_adapter(config)
        assert isinstance(adapter, PostgresProcessAdapter)

    def test_postgres_no_dsn_raises(self, monkeypatch):
        """No dsn in config and no DATABASE_URL → clear ValueError."""
        monkeypatch.delenv("DATABASE_URL", raising=False)

        from dazzle.core.process.factory import PostgresProcessConfig, ProcessConfig, create_adapter

        config = ProcessConfig(backend="postgres", postgres=PostgresProcessConfig(dsn=None))
        with pytest.raises(ValueError, match="DATABASE_URL"):
            create_adapter(config)


class TestBackendTypeLiteral:
    """BackendType includes 'postgres'."""

    def test_postgres_in_backend_type(self):
        """'postgres' is a valid BackendType value (accepted by ProcessConfig)."""
        from dazzle.core.process.factory import ProcessConfig

        # Should not raise a type error at runtime
        config = ProcessConfig(backend="postgres")  # type: ignore[arg-type]
        assert config.backend == "postgres"
