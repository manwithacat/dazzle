"""Guard resolve_provider against type=domain connections (#1424 phase 2)."""

from datetime import UTC, datetime

import pytest

from dazzle.http.runtime.auth.connections import (
    ConnectionError,
    ConnectionRecord,
    resolve_provider,
)


@pytest.fixture
def domain_connection() -> ConnectionRecord:
    """A type=domain connection (routing-only, no IdP provider)."""
    return ConnectionRecord(
        id="conn-domain-1",
        tenant_id="org-1",
        type="domain",
        provider="native",
        domains=["example.com"],
        verified_domains=["example.com"],
        config={},
        secrets={},
        group_mapping={},
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_resolve_provider_rejects_domain_type(domain_connection: ConnectionRecord) -> None:
    """resolve_provider must reject type=domain with a clear error."""
    with pytest.raises(ConnectionError, match="domain.*routing-only"):
        resolve_provider(domain_connection)
