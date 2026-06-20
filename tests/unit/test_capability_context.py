"""SubsystemContext carries the resolved capability set (#1342)."""

from unittest.mock import MagicMock

from dazzle.core.capabilities.models import ResolvedCapabilities
from dazzle.http.runtime.subsystems import SubsystemContext


def _ctx(**kw):
    return SubsystemContext(
        app=MagicMock(),
        appspec=MagicMock(),
        config=MagicMock(),
        services={},
        repositories={},
        entities=[],
        channels=[],
        **kw,
    )


def test_capabilities_defaults_to_none():
    assert _ctx().capabilities is None


def test_capabilities_field_is_queryable():
    caps = ResolvedCapabilities(
        active=frozenset({"auth.enterprise.oidc"}),
        declared=("auth.enterprise.oidc",),
    )
    ctx = _ctx(capabilities=caps)
    assert ctx.capabilities.is_active("auth.enterprise.oidc")
    assert not ctx.capabilities.is_active("auth.enterprise.scim")
