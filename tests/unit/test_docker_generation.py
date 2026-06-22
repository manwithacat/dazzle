"""Tests for Docker artifact generation."""

from pathlib import Path

import pytest

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

    @pytest.mark.parametrize(
        "needle",
        [
            "pg_isready",
            "redis-cli",
            "pgdata:",
        ],
        ids=[
            "test_healthchecks_present_pg",
            "test_healthchecks_present_redis",
            "test_pgdata_volume_defined",
        ],
    )
    def test_dev_compose_myapp_contains(self, needle: str) -> None:
        result = generate_dev_compose("myapp")
        assert needle in result

    @pytest.mark.parametrize(
        "app_name,kwargs,needles",
        [
            ("myapp", {}, ["postgres:", "postgres:16"]),
            ("myapp", {}, ["redis:", "redis:7-alpine"]),
            ("myapp", {}, ['"5432:5432"', '"6379:6379"']),
            ("myapp", {"pg_port": 5433, "redis_port": 6380}, ['"5433:5432"', '"6380:6379"']),
        ],
        ids=[
            "test_contains_postgres_service",
            "test_contains_redis_service",
            "test_default_ports",
            "test_custom_ports",
        ],
    )
    def test_dev_compose_content(self, app_name: str, kwargs: dict, needles: list) -> None:
        result = generate_dev_compose(app_name, **kwargs)
        for needle in needles:
            assert needle in result

    def test_postgres_uses_dazzle_credentials(self) -> None:
        result = generate_dev_compose("myapp")
        assert "POSTGRES_DB: dazzle" in result
        assert "POSTGRES_USER: dazzle" in result
        assert "POSTGRES_PASSWORD: dazzle" in result

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

    @pytest.mark.parametrize(
        "kwargs,expected_url",
        [
            ({}, "postgresql://dazzle:dazzle@localhost:5432/dazzle"),
            ({"pg_port": 5433}, "postgresql://dazzle:dazzle@localhost:5433/dazzle"),
        ],
        ids=[
            "test_dev_database_url_default_port",
            "test_dev_database_url_custom_port",
        ],
    )
    def test_dev_database_url(self, kwargs: dict, expected_url: str) -> None:
        assert dev_database_url(**kwargs) == expected_url

    @pytest.mark.parametrize(
        "kwargs,expected_url",
        [
            ({}, "redis://localhost:6379/0"),
            ({"redis_port": 6380}, "redis://localhost:6380/0"),
        ],
        ids=[
            "test_dev_redis_url_default_port",
            "test_dev_redis_url_custom_port",
        ],
    )
    def test_dev_redis_url(self, kwargs: dict, expected_url: str) -> None:
        assert dev_redis_url(**kwargs) == expected_url

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

    @pytest.mark.parametrize(
        "needle",
        [
            "5433",  # postgres port offset to avoid conflicts
            "6380",  # redis port offset to avoid conflicts
        ],
        ids=[
            "test_postgres_port_offset",
            "test_redis_port_offset",
        ],
    )
    def test_local_compose_port_offsets(self, needle: str) -> None:
        result = generate_local_compose("myapp")
        assert needle in result

    @pytest.mark.parametrize(
        "app_name,needles",
        [
            ("myapp", ["postgres:", "postgres:16-alpine"]),
            ("myapp", ["redis:", "redis:7-alpine"]),
            ("cyfuture", ["POSTGRES_DB: cyfuture", "POSTGRES_USER: cyfuture"]),
            ("myapp", ["pg_isready", "redis-cli"]),
            ("myapp", ["pgdata:", "redisdata:"]),
        ],
        ids=[
            "test_contains_postgres_service",
            "test_contains_redis_service",
            "test_postgres_uses_app_name",
            "test_healthchecks_present",
            "test_volumes_defined",
        ],
    )
    def test_local_compose_content(self, app_name: str, needles: list) -> None:
        result = generate_local_compose(app_name)
        for needle in needles:
            assert needle in result


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

    def test_no_sqlite_reference(self) -> None:
        result = generate_env_template("myapp")
        assert "app.db" not in result
        assert "SQLite" not in result


class TestGenerateRequirements:
    """Tests for requirements.txt generation."""

    def test_does_not_pin_asyncpg(self) -> None:
        # #1341: psycopg3 is the single Postgres driver; asyncpg is no longer a
        # dependency and must not be re-pinned in the generated requirements.
        result = generate_requirements()
        assert "asyncpg" not in result

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
