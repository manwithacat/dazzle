"""
Multi-vendor mock orchestrator.

Manages lifecycle of vendor mock servers, auto-discovers which vendors
a Dazzle app needs from its AppSpec, and coordinates port allocation
and environment variable injection.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.api_kb.loader import load_pack
from dazzle.testing.vendor_mock.generator import create_mock_server

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

logger = logging.getLogger(__name__)

_DEFAULT_BASE_PORT = 9001


@dataclass
class VendorMock:
    """A running vendor mock server instance."""

    pack_name: str
    provider: str
    port: int
    app: Any = None  # FastAPI app
    server_thread: threading.Thread | None = None
    base_url: str = ""
    env_var: str = ""


@dataclass
class MockOrchestrator:
    """Manages multiple vendor mock servers.

    Args:
        seed: Optional seed for deterministic data generation across all mocks.
        base_port: Starting port for mock server allocation.
        auth_tokens: Per-vendor auth tokens, keyed by pack_name.
        project_root: Optional project root for project-local packs/scenarios.
    """

    seed: int | None = None
    base_port: int = _DEFAULT_BASE_PORT
    auth_tokens: dict[str, dict[str, str]] = field(default_factory=dict)
    project_root: Path | None = None
    _mocks: dict[str, VendorMock] = field(default_factory=dict)
    _running: bool = False

    @classmethod
    def from_appspec(
        cls,
        appspec: AppSpec,
        *,
        seed: int | None = None,
        base_port: int = _DEFAULT_BASE_PORT,
        auth_tokens: dict[str, dict[str, str]] | None = None,
        project_root: Path | None = None,
    ) -> MockOrchestrator:
        """Auto-discover needed vendors from an AppSpec.

        Scans ``appspec.apis`` for ``spec_inline`` references in the format
        ``"pack:<pack_name>"`` and creates mock servers for each discovered pack.

        Args:
            appspec: Complete application specification.
            seed: Optional seed for deterministic data.
            base_port: Starting port for allocation.
            auth_tokens: Per-vendor auth tokens.
            project_root: Optional project root for project-local packs/scenarios.

        Returns:
            Configured orchestrator (not yet started).
        """
        # Set project root for project-local pack discovery
        if project_root is not None:
            from dazzle.api_kb.loader import set_project_root

            set_project_root(project_root)

        orchestrator = cls(
            seed=seed,
            base_port=base_port,
            auth_tokens=auth_tokens or {},
            project_root=project_root,
        )

        # Discover packs from API service definitions
        pack_names: list[str] = []
        for api in appspec.apis:
            if api.spec_inline and api.spec_inline.startswith("pack:"):
                pack_name = api.spec_inline.removeprefix("pack:")
                pack_names.append(pack_name)

        # Deduplicate while preserving order
        seen: set[str] = set()
        for name in pack_names:
            if name not in seen:
                seen.add(name)
                orchestrator.add_vendor(name)

        return orchestrator

    def add_vendor(
        self,
        pack_name: str,
        *,
        port: int | None = None,
        auth_tokens: dict[str, str] | None = None,
    ) -> VendorMock:
        """Add a vendor mock server.

        Args:
            pack_name: API pack name (e.g. "sumsub_kyc").
            port: Explicit port, or auto-allocated from base_port.
            auth_tokens: Auth credentials for this vendor.

        Returns:
            The created VendorMock descriptor.
        """
        if pack_name in self._mocks:
            return self._mocks[pack_name]

        pack = load_pack(pack_name)
        if not pack:
            raise ValueError(f"API pack '{pack_name}' not found")

        assigned_port = port or (self.base_port + len(self._mocks))
        tokens = auth_tokens or self.auth_tokens.get(pack_name)

        app = create_mock_server(
            pack_name, seed=self.seed, auth_tokens=tokens, project_root=self.project_root
        )
        env_var = _pack_to_env_var(pack_name)

        mock = VendorMock(
            pack_name=pack_name,
            provider=pack.provider,
            port=assigned_port,
            app=app,
            base_url=f"http://127.0.0.1:{assigned_port}",
            env_var=env_var,
        )
        self._mocks[pack_name] = mock
        return mock

    def start(self) -> None:
        """Start all vendor mock servers in background threads."""
        if self._running:
            return

        try:
            import uvicorn
        except ImportError:
            raise RuntimeError("uvicorn is required to run mock servers")

        for mock in self._mocks.values():
            config = uvicorn.Config(
                mock.app,
                host="127.0.0.1",
                port=mock.port,
                log_level="warning",
            )
            server = uvicorn.Server(config)

            thread = threading.Thread(
                target=server.run,
                name=f"mock-{mock.pack_name}",
                daemon=True,
            )
            mock.server_thread = thread
            thread.start()

            # Inject environment variable for the integration executor
            os.environ[mock.env_var] = mock.base_url
            logger.info(
                "Started mock %s on port %d (%s=%s)",
                mock.provider,
                mock.port,
                mock.env_var,
                mock.base_url,
            )

        self._running = True

    def stop(self) -> None:
        """Stop all vendor mock servers and clean up env vars."""
        if not self._running:
            return

        for mock in self._mocks.values():
            # Remove injected env vars
            os.environ.pop(mock.env_var, None)

        # Daemon threads will die when the process exits;
        # for explicit shutdown we'd need to signal uvicorn.Server.should_exit
        self._running = False
        logger.info("Stopped %d vendor mock(s)", len(self._mocks))

    def inject_env(self) -> dict[str, str]:
        """Inject environment variables for all mocks without starting servers.

        Useful for test setups using HTTPX/TestClient instead of real sockets.

        Returns:
            Dict of injected env var name → URL.
        """
        injected: dict[str, str] = {}
        for mock in self._mocks.values():
            os.environ[mock.env_var] = mock.base_url
            injected[mock.env_var] = mock.base_url
        return injected

    def clear_env(self) -> None:
        """Remove all injected environment variables."""
        for mock in self._mocks.values():
            os.environ.pop(mock.env_var, None)

    @property
    def vendors(self) -> dict[str, VendorMock]:
        """All registered vendor mocks, keyed by pack name."""
        return dict(self._mocks)

    @property
    def is_running(self) -> bool:
        """Whether the orchestrator has been started."""
        return self._running

    def get_app(self, pack_name: str) -> Any:
        """Get the FastAPI app for a vendor (for TestClient usage).

        Args:
            pack_name: API pack name.

        Returns:
            The FastAPI app instance.

        Raises:
            KeyError: If the vendor is not registered.
        """
        return self._mocks[pack_name].app

    def get_store(self, pack_name: str) -> Any:
        """Get the state store for a vendor (for test assertions).

        Args:
            pack_name: API pack name.

        Returns:
            The MockStateStore instance.

        Raises:
            KeyError: If the vendor is not registered.
        """
        return self._mocks[pack_name].app.state.store

    def health_check(self) -> dict[str, bool]:
        """Check health of all vendor mocks using their FastAPI test clients.

        Returns:
            Dict of pack_name → healthy (True/False).
        """
        from fastapi.testclient import TestClient

        results: dict[str, bool] = {}
        for name, mock in self._mocks.items():
            try:
                client = TestClient(mock.app, raise_server_exceptions=False)
                resp = client.get("/health")
                results[name] = resp.status_code == 200
            except Exception:
                results[name] = False
        return results


def _pack_to_env_var(pack_name: str) -> str:
    """Convert a pack name to an environment variable name.

    Follows the integration executor convention:
    ``DAZZLE_API_{NAME}_URL``

    Examples:
        "sumsub_kyc" → "DAZZLE_API_SUMSUB_KYC_URL"
        "stripe_payments" → "DAZZLE_API_STRIPE_PAYMENTS_URL"
    """
    name_upper = pack_name.upper().replace("-", "_").replace(".", "_")
    return f"DAZZLE_API_{name_upper}_URL"


def discover_packs_from_appspec(appspec: AppSpec) -> list[str]:
    """Extract API pack names from an AppSpec.

    Scans ``appspec.apis`` for ``spec_inline`` references
    in ``"pack:<name>"`` format.

    Args:
        appspec: Application specification.

    Returns:
        List of pack names (deduplicated, order-preserved).
    """
    seen: set[str] = set()
    result: list[str] = []
    for api in appspec.apis:
        if api.spec_inline and api.spec_inline.startswith("pack:"):
            name = api.spec_inline.removeprefix("pack:")
            if name not in seen:
                seen.add(name)
                result.append(name)
    return result
