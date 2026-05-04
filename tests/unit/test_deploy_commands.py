"""Tests for dazzle deploy dockerfile|heroku|compose commands."""

import pytest

from dazzle.cli.deploy import (
    generate_compose_yaml,
    generate_heroku_files,
    generate_production_dockerfile,
)


class TestGenerateProductionDockerfile:
    """Tests for Dockerfile generation."""

    def test_uses_python_312_slim(self) -> None:
        result = generate_production_dockerfile()
        assert "FROM python:3.12-slim" in result

    def test_includes_healthcheck(self) -> None:
        result = generate_production_dockerfile()
        assert "HEALTHCHECK" in result

    def test_cmd_is_dazzle_serve_production(self) -> None:
        result = generate_production_dockerfile()
        assert 'dazzle", "serve", "--production"' in result

    def test_exposes_port_8000(self) -> None:
        result = generate_production_dockerfile()
        assert "EXPOSE 8000" in result

    def test_copies_requirements(self) -> None:
        result = generate_production_dockerfile()
        assert "COPY requirements.txt" in result


class TestGenerateHerokuFiles:
    """Tests for Heroku file generation."""

    def test_procfile_uses_production_flag(self) -> None:
        procfile, runtime, requirements = generate_heroku_files("0.46.2")
        assert "dazzle serve --production" in procfile

    def test_runtime_is_python_312(self) -> None:
        _, runtime, _ = generate_heroku_files("0.46.2")
        assert "python-3.12" in runtime

    def test_requirements_pins_dazzle_version(self) -> None:
        _, _, requirements = generate_heroku_files("0.46.2")
        assert "dazzle-dsl==0.46.2" in requirements

    def test_requirements_includes_psycopg(self) -> None:
        _, _, requirements = generate_heroku_files("0.46.2")
        assert "psycopg[binary]" in requirements


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
