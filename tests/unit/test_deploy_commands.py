"""Tests for dazzle deploy dockerfile|heroku|compose commands."""

from __future__ import annotations

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

    def test_has_app_service(self) -> None:
        result = generate_compose_yaml()
        assert "app:" in result

    def test_has_postgres_service(self) -> None:
        result = generate_compose_yaml()
        assert "postgres:" in result

    def test_has_redis_service(self) -> None:
        result = generate_compose_yaml()
        assert "redis:" in result

    def test_app_depends_on_postgres(self) -> None:
        result = generate_compose_yaml()
        assert "depends_on:" in result
        assert "postgres:" in result

    def test_postgres_has_healthcheck(self) -> None:
        result = generate_compose_yaml()
        assert "pg_isready" in result

    def test_has_pgdata_volume(self) -> None:
        result = generate_compose_yaml()
        assert "pgdata:" in result

    def test_app_port_maps_3000_to_8000(self) -> None:
        result = generate_compose_yaml()
        assert '"3000:8000"' in result
