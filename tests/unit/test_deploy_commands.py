"""Tests for dazzle deploy dockerfile|heroku|compose commands."""

import pytest

from dazzle.cli.deploy import (
    generate_compose_yaml,
    generate_heroku_files,
    generate_production_dockerfile,
)


class TestGenerateProductionDockerfile:
    """Tests for Dockerfile generation."""

    @pytest.mark.parametrize(
        "expected",
        [
            "FROM python:3.12-slim",
            "HEALTHCHECK",
            'dazzle", "serve", "--production"',
            "EXPOSE 8000",
            "COPY requirements.txt",
        ],
        ids=[
            "test_uses_python_312_slim",
            "test_includes_healthcheck",
            "test_cmd_is_dazzle_serve_production",
            "test_exposes_port_8000",
            "test_copies_requirements",
        ],
    )
    def test_dockerfile_contains(self, expected: str) -> None:
        result = generate_production_dockerfile()
        assert expected in result


class TestGenerateHerokuFiles:
    """Tests for Heroku file generation."""

    @pytest.mark.parametrize(
        "index,expected",
        [
            (0, "dazzle serve --production"),
            (1, "python-3.12"),
            (2, "dazzle-dsl==0.46.2"),
            (2, "psycopg[binary]"),
        ],
        ids=[
            "test_procfile_uses_production_flag",
            "test_runtime_is_python_312",
            "test_requirements_pins_dazzle_version",
            "test_requirements_includes_psycopg",
        ],
    )
    def test_heroku_file_contains(self, index: int, expected: str) -> None:
        files = generate_heroku_files("0.46.2")
        assert expected in files[index]


class TestGenerateComposeYaml:
    """Tests for docker-compose.yml generation."""

    @pytest.mark.parametrize(
        "expected_substring",
        [
            "app:",
            "postgres:",
            "redis:",
            "depends_on:",
            "pg_isready",
            "pgdata:",
            '"3000:8000"',
        ],
        ids=[
            "has_app_service",
            "has_postgres_service",
            "has_redis_service",
            "app_depends_on_postgres",
            "postgres_has_healthcheck",
            "has_pgdata_volume",
            "app_port_maps_3000_to_8000",
        ],
    )
    def test_compose_yaml_contains(self, expected_substring: str) -> None:
        result = generate_compose_yaml()
        assert expected_substring in result
