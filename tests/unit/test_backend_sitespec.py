"""Tests for DazzleBackendApp sitespec handling.

Regression test for issue where sitespec_data parameter was being
overwritten by config defaults in DazzleBackendApp.__init__.
"""

from unittest.mock import MagicMock, patch

import pytest

# Skip if FastAPI not installed
pytest.importorskip("fastapi")

from dazzle_back.runtime.server import DazzleBackendApp, ServerConfig  # noqa: E402
from dazzle_back.specs import BackendSpec, EntitySpec, FieldSpec  # noqa: E402
from dazzle_back.specs.entity import FieldType, ScalarType  # noqa: E402


def _create_minimal_backend_spec() -> BackendSpec:
    """Create a minimal BackendSpec for testing."""
    return BackendSpec(
        name="test_app",
        description="Test application",
        entities=[
            EntitySpec(
                name="Task",
                label="Task",
                description="A task",
                fields=[
                    FieldSpec(
                        name="id",
                        type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                        required=True,
                        unique=True,
                        indexed=True,
                    ),
                    FieldSpec(
                        name="title",
                        type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                        required=True,
                    ),
                ],
            )
        ],
        endpoints=[],
        channels=[],
    )


class TestDazzleBackendAppSitespec:
    """Tests for sitespec_data parameter handling."""

    def test_sitespec_data_param_takes_precedence_over_config(self) -> None:
        """Test that explicit sitespec_data param is not overwritten by config.

        Regression test: Previously, the constructor had duplicate assignments
        that would overwrite the explicit parameter with config.sitespec_data (None).
        """
        spec = _create_minimal_backend_spec()

        # Create sitespec data
        sitespec_data = {
            "version": 1,
            "brand": {"product_name": "Test App"},
            "pages": [{"route": "/", "type": "landing"}],
        }

        # Create app with explicit sitespec_data
        app_builder = DazzleBackendApp(
            spec,
            sitespec_data=sitespec_data,
        )

        # Verify sitespec_data was preserved
        assert app_builder._sitespec_data is not None, (
            "sitespec_data should not be None when explicitly passed"
        )
        assert app_builder._sitespec_data == sitespec_data
        assert app_builder._sitespec_data["brand"]["product_name"] == "Test App"

    def test_sitespec_data_falls_back_to_config_when_not_provided(self) -> None:
        """Test that config.sitespec_data is used when param not provided."""
        spec = _create_minimal_backend_spec()

        config_sitespec = {
            "version": 1,
            "brand": {"product_name": "Config App"},
            "pages": [],
        }

        config = ServerConfig(sitespec_data=config_sitespec)
        app_builder = DazzleBackendApp(
            spec,
            config=config,
        )

        assert app_builder._sitespec_data == config_sitespec

    def test_sitespec_data_none_when_not_provided(self) -> None:
        """Test that sitespec_data is None when not provided anywhere."""
        spec = _create_minimal_backend_spec()
        app_builder = DazzleBackendApp(
            spec,
        )

        assert app_builder._sitespec_data is None

    @patch("dazzle_back.runtime.pg_backend.PostgresBackend")
    @patch("dazzle_back.runtime.migrations.auto_migrate")
    def test_site_routes_registered_when_sitespec_provided(
        self, mock_migrate: MagicMock, mock_pg: MagicMock
    ) -> None:
        """Test that /_site/* routes are registered when sitespec_data provided."""
        spec = _create_minimal_backend_spec()

        sitespec_data = {
            "version": 1,
            "brand": {"product_name": "Test"},
            "pages": [{"route": "/", "type": "landing"}],
            "legal": {},
        }

        app_builder = DazzleBackendApp(
            spec,
            sitespec_data=sitespec_data,
            database_url="postgresql://mock/test",
        )
        app = app_builder.build()

        # Check that site routes were registered
        route_paths = [route.path for route in app.routes]

        assert "/_site/pages" in route_paths, "/_site/pages route should be registered"
        assert "/_site/page/{route:path}" in route_paths, "/_site/page route should be registered"

    @patch("dazzle_back.runtime.pg_backend.PostgresBackend")
    @patch("dazzle_back.runtime.migrations.auto_migrate")
    def test_site_routes_not_registered_when_no_sitespec(
        self, mock_migrate: MagicMock, mock_pg: MagicMock
    ) -> None:
        """Test that /_site/* routes are NOT registered when no sitespec_data."""
        spec = _create_minimal_backend_spec()

        app_builder = DazzleBackendApp(
            spec,
            database_url="postgresql://mock/test",
        )
        app = app_builder.build()

        # Check that site routes were NOT registered
        route_paths = [route.path for route in app.routes]

        assert "/_site/pages" not in route_paths, (
            "/_site/pages should not be registered without sitespec"
        )
