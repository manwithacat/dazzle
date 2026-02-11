"""Tests for the api_packs MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def _import_api_packs():
    """Import api_packs handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])

    # Create mock API pack objects using SimpleNamespace for JSON serializability
    mock_auth = SimpleNamespace(
        auth_type="api_key",
        env_var="STRIPE_API_KEY",
        token_url=None,
        scopes=None,
    )

    mock_env_var = SimpleNamespace(
        name="STRIPE_API_KEY",
        required=True,
        description="API key",
        example="sk_test_xxx",
    )

    mock_operation = SimpleNamespace(
        name="create_customer",
        method="POST",
        path="/v1/customers",
        description="Create customer",
    )

    mock_pack = SimpleNamespace(
        name="stripe",
        provider="stripe",
        category="payments",
        description="Stripe API integration",
        version="1.0.0",
        base_url="https://api.stripe.com",
        docs_url="https://stripe.com/docs",
        auth=mock_auth,
        env_vars=[mock_env_var],
        operations=[mock_operation],
        foreign_models=[],
        infrastructure=None,
        generate_service_dsl=lambda: (
            'service stripe "Stripe":\n    base_url: "https://api.stripe.com"'
        ),
        generate_foreign_model_dsl=lambda m: "",
    )

    # Mock the api_kb module
    mock_api_kb = MagicMock()
    mock_api_kb.list_packs = MagicMock(return_value=[mock_pack])
    mock_api_kb.search_packs = MagicMock(return_value=[mock_pack])
    mock_api_kb.load_pack = MagicMock(return_value=mock_pack)
    sys.modules["dazzle.api_kb"] = mock_api_kb

    # Mock the loader module
    mock_loader = MagicMock()
    mock_loader.generate_env_example = MagicMock(return_value="STRIPE_API_KEY=sk_test_xxx")
    sys.modules["dazzle.api_kb.loader"] = mock_loader

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "api_packs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.api_packs",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.api_packs"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_ap = _import_api_packs()

# Get references to the functions we need
list_api_packs_handler = _ap.list_api_packs_handler
search_api_packs_handler = _ap.search_api_packs_handler
get_api_pack_handler = _ap.get_api_pack_handler
generate_service_dsl_handler = _ap.generate_service_dsl_handler
get_env_vars_for_packs_handler = _ap.get_env_vars_for_packs_handler


# =============================================================================
# Handler Tests
# =============================================================================


class TestListApiPacksHandler:
    """Tests for list_api_packs_handler."""

    def test_lists_packs(self) -> None:
        """Test listing all API packs."""
        result = list_api_packs_handler({})
        data = json.loads(result)

        assert "count" in data
        assert "packs" in data
        assert data["count"] >= 0

    def test_pack_info_structure(self) -> None:
        """Test that pack info has expected structure."""
        result = list_api_packs_handler({})
        data = json.loads(result)

        if data["count"] > 0:
            pack = data["packs"][0]
            assert "name" in pack
            assert "provider" in pack
            assert "category" in pack
            assert "description" in pack


class TestSearchApiPacksHandler:
    """Tests for search_api_packs_handler."""

    def test_returns_query_info(self) -> None:
        """Test that query info is included in response."""
        result = search_api_packs_handler({"category": "payments"})
        data = json.loads(result)

        assert "query" in data
        assert data["query"]["category"] == "payments"

    def test_search_by_category(self) -> None:
        """Test searching by category."""
        result = search_api_packs_handler({"category": "payments"})
        data = json.loads(result)

        assert "packs" in data
        assert "count" in data

    def test_search_by_provider(self) -> None:
        """Test searching by provider."""
        result = search_api_packs_handler({"provider": "stripe"})
        data = json.loads(result)

        assert "packs" in data
        assert data["query"]["provider"] == "stripe"

    def test_search_by_query(self) -> None:
        """Test searching by text query."""
        result = search_api_packs_handler({"query": "payment"})
        data = json.loads(result)

        assert "packs" in data
        assert data["query"]["text"] == "payment"


class TestGetApiPackHandler:
    """Tests for get_api_pack_handler."""

    def test_requires_pack_name(self) -> None:
        """Test that pack_name is required."""
        result = get_api_pack_handler({})
        data = json.loads(result)

        assert "error" in data
        assert "pack_name" in data["error"].lower()

    def test_returns_pack_details(self) -> None:
        """Test getting pack details."""
        result = get_api_pack_handler({"pack_name": "stripe"})
        data = json.loads(result)

        assert "name" in data
        assert "provider" in data
        assert "auth" in data
        assert "operations" in data

    def test_includes_env_vars(self) -> None:
        """Test that env vars are included."""
        result = get_api_pack_handler({"pack_name": "stripe"})
        data = json.loads(result)

        assert "env_vars" in data


class TestGenerateServiceDslHandler:
    """Tests for generate_service_dsl_handler."""

    def test_requires_pack_name(self) -> None:
        """Test that pack_name is required."""
        result = generate_service_dsl_handler({})
        data = json.loads(result)

        assert "error" in data
        assert "pack_name" in data["error"].lower()

    def test_generates_dsl(self) -> None:
        """Test generating DSL from pack."""
        result = generate_service_dsl_handler({"pack_name": "stripe"})
        data = json.loads(result)

        assert "dsl" in data
        assert "pack" in data
        assert "hint" in data

    def test_includes_required_env_vars(self) -> None:
        """Test that required env vars are listed."""
        result = generate_service_dsl_handler({"pack_name": "stripe"})
        data = json.loads(result)

        assert "env_vars_required" in data


class TestGetEnvVarsForPacksHandler:
    """Tests for get_env_vars_for_packs_handler."""

    def test_returns_env_example(self) -> None:
        """Test getting env example content."""
        result = get_env_vars_for_packs_handler({})
        data = json.loads(result)

        assert "env_example" in data
        assert "hint" in data

    def test_with_specific_packs(self) -> None:
        """Test getting env vars for specific packs."""
        result = get_env_vars_for_packs_handler({"pack_names": ["stripe"]})
        data = json.loads(result)

        assert data["packs"] == ["stripe"]
        assert "env_example" in data
