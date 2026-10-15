"""Tests for DazzleBackendApp sitespec handling.

Regression test for issue where sitespec_data parameter was being
overwritten by config defaults in DazzleBackendApp.__init__.
"""

import pytest

# Skip if FastAPI not installed
pytest.importorskip("fastapi")

from dazzle.core.ir.appspec import AppSpec  # noqa: E402
from dazzle.core.ir.domain import DomainSpec, EntitySpec  # noqa: E402
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind  # noqa: E402
from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig  # noqa: E402


def _create_minimal_appspec() -> AppSpec:
    """Create a minimal AppSpec for testing."""
    entity = EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=["pk", "required"],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=["required"],
            ),
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test application",
        domain=DomainSpec(entities=[entity]),
    )


class TestDazzleBackendAppSitespec:
    """Tests for sitespec_data parameter handling."""

    def test_sitespec_data_param_takes_precedence_over_config(self) -> None:
        """Test that explicit sitespec_data param is not overwritten by config.

        Regression test: Previously, the constructor had duplicate assignments
        that would overwrite the explicit parameter with config.sitespec_data (None).
        """
        spec = _create_minimal_appspec()

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
        spec = _create_minimal_appspec()

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
        spec = _create_minimal_appspec()
        app_builder = DazzleBackendApp(
            spec,
        )

        assert app_builder._sitespec_data is None
