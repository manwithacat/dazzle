"""
Vendor mock system — auto-generated API simulators from API pack definitions.

Generate mock servers for third-party vendor APIs (SumSub, HMRC, Xero, etc.)
directly from TOML-defined API packs. Provides stateful CRUD, auth validation,
and realistic response data for integration testing without vendor credentials.
"""

from __future__ import annotations

from dazzle.testing.vendor_mock.assertions import RequestRecorder, get_recorder
from dazzle.testing.vendor_mock.data_generators import DataGenerator
from dazzle.testing.vendor_mock.fixtures import mock_vendor
from dazzle.testing.vendor_mock.generator import create_mock_server
from dazzle.testing.vendor_mock.orchestrator import MockOrchestrator, discover_packs_from_appspec
from dazzle.testing.vendor_mock.state import MockStateStore

__all__ = [
    "DataGenerator",
    "MockOrchestrator",
    "MockStateStore",
    "RequestRecorder",
    "create_mock_server",
    "discover_packs_from_appspec",
    "get_recorder",
    "mock_vendor",
]
