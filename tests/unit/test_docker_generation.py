"""Tests for Docker artifact generation."""

from __future__ import annotations

from pathlib import Path

from dazzle.cli.runtime_impl.docker import (
    dev_compose_path,
    dev_database_url,
    dev_redis_url,
    generate_dev_compose,
    generate_docker_compose,
    generate_dockerfile,
    generate_env_template,
    generate_local_compose,
    generate_local_run_script,
    generate_production_main,
    generate_requirements,
    write_dev_compose,
)


class TestGenerateDevCompose:
    """Tests for dev infrastructure docker-compose.yml generation."""

    def test_contains_postgres_service(self) -> None:
        result = generate_dev_compose("myapp")
        assert "postgres:" in result
        assert "postgres:16" in result

    def test_contains_redis_service(self) -> None:
        result = generate_dev_compose("myapp")
        assert "redis:" in result
        assert "redis:7-alpine" in result

    def test_postgres_uses_dazzle_credentials(self) -> None:
        result = generate_dev_compose("myapp")
        assert "POSTGRES_DB: dazzle" in result
        assert "POSTGRES_USER: dazzle" in result
        assert "POSTGRES_PASSWORD: dazzle" in result

    def test_default_ports(self) -> None:
        result = generate_dev_compose("myapp")
        assert '"5432:5432"' in result
        assert '"6379:6379"' in result

    def test_custom_ports(self) -> None:
        result = generate_dev_compose("myapp", pg_port=5433, redis_port=6380)
        assert '"5433:5432"' in result
        assert '"6380:6379"' in result

    def test_healthchecks_present(self) -> None:
        result = generate_dev_compose("myapp")
        assert "pg_isready" in result
        assert "redis-cli" in result

    def test_pgdata_volume_defined(self) -> None:
        result = generate_dev_compose("myapp")
        assert "pgdata:" in result

    def test_no_app_service(self) -> None:
        """Dev compose provides infrastructure only, no app container."""
        result = generate_dev_compose("myapp")
        assert "app:" not in result
        assert "build:" not in result

    def test_project_name_in_comment(self) -> None:
        result = generate_dev_compose("todo_app")
        assert "todo_app" in result


class TestDevComposeHelpers:
    """Tests for dev compose helper functions."""

    def test_dev_database_url_default_port(self) -> None:
        url = dev_database_url()
        assert url == "postgresql://dazzle:dazzle@localhost:5432/dazzle"

    def test_dev_database_url_custom_port(self) -> None:
        url = dev_database_url(pg_port=5433)
        assert url == "postgresql://dazzle:dazzle@localhost:5433/dazzle"

    def test_dev_redis_url_default_port(self) -> None:
        url = dev_redis_url()
        assert url == "redis://localhost:6379/0"

    def test_dev_redis_url_custom_port(self) -> None:
        url = dev_redis_url(redis_port=6380)
        assert url == "redis://localhost:6380/0"

    def test_dev_compose_path(self) -> None:
        root = Path("/tmp/myproject")
        path = dev_compose_path(root)
        assert path == root / ".dazzle" / "docker-compose.yml"

    def test_write_dev_compose(self, tmp_path: Path) -> None:
        compose_file = write_dev_compose(tmp_path, "myapp")
        assert compose_file.exists()
        assert compose_file == tmp_path / ".dazzle" / "docker-compose.yml"
        content = compose_file.read_text()
        assert "postgres:" in content
        assert "redis:" in content

    def test_write_dev_compose_creates_dazzle_dir(self, tmp_path: Path) -> None:
        dazzle_dir = tmp_path / ".dazzle"
        assert not dazzle_dir.exists()
        write_dev_compose(tmp_path, "myapp")
        assert dazzle_dir.exists()


class TestGenerateLocalCompose:
    """Tests for docker-compose.local.yml generation."""

    def test_contains_postgres_service(self) -> None:
        result = generate_local_compose("myapp")
        assert "postgres:" in result
        assert "postgres:16-alpine" in result

    def test_contains_redis_service(self) -> None:
        result = generate_local_compose("myapp")
        assert "redis:" in result
        assert "redis:7-alpine" in result

    def test_postgres_uses_app_name(self) -> None:
        result = generate_local_compose("cyfuture")
        assert "POSTGRES_DB: cyfuture" in result
        assert "POSTGRES_USER: cyfuture" in result

    def test_postgres_port_offset(self) -> None:
        result = generate_local_compose("myapp")
        assert "5433" in result  # Offset to avoid conflicts

    def test_redis_port_offset(self) -> None:
        result = generate_local_compose("myapp")
        assert "6380" in result  # Offset to avoid conflicts

    def test_healthchecks_present(self) -> None:
        result = generate_local_compose("myapp")
        assert "pg_isready" in result
        assert "redis-cli" in result

    def test_volumes_defined(self) -> None:
        result = generate_local_compose("myapp")
        assert "pgdata:" in result
        assert "redisdata:" in result


class TestGenerateLocalRunScript:
    """Tests for scripts/run_local.sh generation."""

    def test_is_bash_script(self) -> None:
        result = generate_local_run_script("myapp")
        assert result.startswith("#!/usr/bin/env bash")

    def test_sets_database_url(self) -> None:
        result = generate_local_run_script("myapp")
        assert "DATABASE_URL" in result
        assert "postgresql://" in result

    def test_sets_redis_url(self) -> None:
        result = generate_local_run_script("myapp")
        assert "REDIS_URL" in result
        assert "redis://localhost" in result

    def test_uses_app_name_in_connection_string(self) -> None:
        result = generate_local_run_script("cyfuture")
        assert "cyfuture" in result

    def test_uses_create_app_factory(self) -> None:
        result = generate_local_run_script("myapp")
        assert "create_app_factory" in result

    def test_sources_env_file(self) -> None:
        result = generate_local_run_script("myapp")
        assert ".env" in result
        assert "source" in result

    def test_sets_dazzle_project_root(self) -> None:
        result = generate_local_run_script("myapp")
        assert "DAZZLE_PROJECT_ROOT" in result


class TestGenerateDockerCompose:
    """Tests for the production docker-compose.yml generation."""

    def test_contains_app_service(self) -> None:
        result = generate_docker_compose("myapp")
        assert "app:" in result

    def test_uses_postgresql(self) -> None:
        result = generate_docker_compose("myapp")
        assert "postgresql://" in result
        assert "app.db" not in result

    def test_contains_postgres_service(self) -> None:
        result = generate_docker_compose("myapp")
        assert "postgres:" in result
        assert "postgres:16" in result

    def test_contains_redis_service(self) -> None:
        result = generate_docker_compose("myapp")
        assert "redis:" in result

    def test_app_depends_on_postgres(self) -> None:
        result = generate_docker_compose("myapp")
        assert "depends_on:" in result
        assert "postgres:" in result


class TestGenerateEnvTemplate:
    """Tests for .env.example generation."""

    def test_contains_postgres_url(self) -> None:
        result = generate_env_template("myapp")
        assert "postgresql://" in result

    def test_contains_redis_url(self) -> None:
        result = generate_env_template("myapp")
        assert "REDIS_URL" in result

    def test_contains_celery_setting(self) -> None:
        result = generate_env_template("myapp")
        assert "USE_CELERY_PROCESSES" in result

    def test_no_sqlite_reference(self) -> None:
        result = generate_env_template("myapp")
        assert "app.db" not in result
        assert "SQLite" not in result


class TestGenerateRequirements:
    """Tests for requirements.txt generation."""

    def test_includes_asyncpg(self) -> None:
        result = generate_requirements()
        assert "asyncpg" in result

    def test_includes_aiosqlite(self) -> None:
        result = generate_requirements()
        assert "aiosqlite" in result

    def test_mentions_redis(self) -> None:
        result = generate_requirements()
        assert "redis" in result


class TestGenerateDockerfile:
    """Tests for Dockerfile generation."""

    def test_contains_healthcheck(self) -> None:
        result = generate_dockerfile("myapp", include_frontend=False)
        assert "HEALTHCHECK" in result

    def test_uses_app_name(self) -> None:
        result = generate_dockerfile("myapp", include_frontend=False)
        assert "myapp" in result

    def test_no_sqlite_database_url(self) -> None:
        result = generate_dockerfile("myapp", include_frontend=False)
        assert "app.db" not in result


class TestGenerateProductionMain:
    """Tests for main.py generation."""

    def test_uses_app_name(self) -> None:
        result = generate_production_main("myapp", include_frontend=False)
        assert "myapp" in result

    def test_imports_uvicorn(self) -> None:
        result = generate_production_main("myapp", include_frontend=False)
        assert "uvicorn" in result
