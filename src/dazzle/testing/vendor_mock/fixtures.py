"""
Pytest fixtures for vendor mock servers.

Provides auto-discovery fixtures that start mock servers for all vendors
referenced in a Dazzle AppSpec, with deterministic data generation and
request recording for test assertions.

Register as a pytest plugin via pyproject.toml entry point::

    [project.entry-points."pytest11"]
    dazzle_vendor_mocks = "dazzle.testing.vendor_mock.fixtures"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from dazzle.testing.vendor_mock.orchestrator import MockOrchestrator

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture()
def vendor_mocks() -> Generator[MockOrchestrator, None, None]:
    """Create a vendor mock orchestrator with deterministic seed.

    Use ``vendor_mocks.add_vendor("sumsub_kyc")`` to add specific vendors,
    or combine with an AppSpec fixture for auto-discovery.

    Yields:
        MockOrchestrator instance with env vars injected.
    """
    orch = MockOrchestrator(seed=42, base_port=19001)
    yield orch
    orch.clear_env()


@pytest.fixture()
def vendor_mocks_from_appspec(
    request: pytest.FixtureRequest,
) -> Generator[MockOrchestrator, None, None]:
    """Auto-discover and start vendor mocks from an AppSpec.

    Requires an ``appspec`` fixture to be defined in the test module
    or conftest. Falls back to an empty orchestrator if not available.

    Yields:
        MockOrchestrator with all discovered vendors registered and env injected.
    """
    appspec = request.getfixturevalue("appspec") if "appspec" in request.fixturenames else None
    if appspec:
        orch = MockOrchestrator.from_appspec(appspec, seed=42, base_port=19001)
    else:
        orch = MockOrchestrator(seed=42, base_port=19001)
    orch.inject_env()
    yield orch
    orch.clear_env()


def mock_vendor(
    pack_name: str,
    *,
    seed: int = 42,
    port: int = 19001,
    auth_tokens: dict[str, str] | None = None,
) -> Any:
    """Create a standalone mock vendor with a TestClient for direct testing.

    This is a helper for tests that need a single vendor mock without
    the full orchestrator.

    Args:
        pack_name: API pack name (e.g. "sumsub_kyc").
        seed: Seed for deterministic data generation.
        port: Port for the mock server.
        auth_tokens: Optional auth credentials.

    Returns:
        TestClient wrapping the vendor's FastAPI app.

    Example::

        def test_sumsub_applicant():
            client = mock_vendor("sumsub_kyc")
            resp = client.post("/resources/applicants",
                json={"type": "individual"},
                headers={"X-App-Token": "t", "X-App-Access-Ts": "0", "X-App-Access-Sig": "s"})
            assert resp.status_code == 201
    """
    from fastapi.testclient import TestClient

    from dazzle.testing.vendor_mock.generator import create_mock_server

    app = create_mock_server(pack_name, seed=seed, auth_tokens=auth_tokens)
    return TestClient(app, raise_server_exceptions=False)
