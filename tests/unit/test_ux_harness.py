"""Tests for UX verification Postgres harness."""

from dazzle.testing.ux.harness import PostgresHarness, check_postgres_available


class TestPostgresDetection:
    def test_check_returns_bool(self) -> None:
        result = check_postgres_available()
        assert isinstance(result, bool)


class TestHarnessConfig:
    def test_default_db_url(self) -> None:
        harness = PostgresHarness(project_name="test_default")
        assert "localhost" in harness.db_url or "127.0.0.1" in harness.db_url

    def test_custom_db_url(self) -> None:
        harness = PostgresHarness(
            db_url="postgresql://custom:5432/db",
            project_name="test_custom",
        )
        assert "custom" in harness.db_url

    def test_test_db_name_sanitized(self) -> None:
        harness = PostgresHarness(project_name="my-project.v2")
        assert harness._test_db_name() == "dazzle_ux_test_my_project_v2"
