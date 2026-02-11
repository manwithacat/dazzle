"""Tests for Docker artifact generation."""

from __future__ import annotations

from dazzle.cli.runtime_impl.docker import (
    generate_docker_compose,
    generate_dockerfile,
    generate_env_template,
    generate_local_compose,
    generate_local_run_script,
    generate_production_main,
    generate_requirements,
)


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
    """Tests for the existing docker-compose.yml generation."""

    def test_contains_app_service(self) -> None:
        result = generate_docker_compose("myapp")
        assert "app:" in result

    def test_uses_sqlite(self) -> None:
        result = generate_docker_compose("myapp")
        assert "app.db" in result


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

    def test_uses_app_name_in_postgres_url(self) -> None:
        result = generate_env_template("cyfuture")
        assert "cyfuture" in result


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


class TestGenerateProductionMain:
    """Tests for main.py generation."""

    def test_uses_app_name(self) -> None:
        result = generate_production_main("myapp", include_frontend=False)
        assert "myapp" in result

    def test_imports_uvicorn(self) -> None:
        result = generate_production_main("myapp", include_frontend=False)
        assert "uvicorn" in result
