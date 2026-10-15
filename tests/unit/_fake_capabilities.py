"""Stand-in capabilities for the capability-registry tests.

The framework registers no capability since the enterprise auth ones were parked
in DD-013 (flense ship AD), so these tests register their own, shaped like the
three that existed: one with a probe module behind an extra, one whose extra is
never installed, and one with no import-time dependency.
"""

import pytest

import dazzle.core.capabilities.registry as reg
from dazzle.core.capabilities.models import Capability

ALPHA = "demo.alpha"  # probe ``authlib`` behind the ``sso`` extra
BETA = "demo.beta"  # probe ``dazzle_demo_absent`` behind a ``beta`` extra
GAMMA = "demo.gamma"  # no probe: always available once declared

FAKE_CAPABILITIES = (
    Capability(
        id=ALPHA,
        label="Demo alpha",
        probe_module="authlib",
        required_extras=("sso",),
        remediation="pip install 'dazzle-dsl[sso]'",
    ),
    Capability(
        id=BETA,
        label="Demo beta",
        probe_module="dazzle_demo_absent",
        required_extras=("beta",),
        remediation="pip install 'dazzle-dsl[beta]'",
    ),
    Capability(
        id=GAMMA,
        label="Demo gamma",
        probe_module=None,
        required_extras=(),
        remediation="",
    ),
)


@pytest.fixture
def fake_capabilities(monkeypatch: pytest.MonkeyPatch) -> tuple[Capability, ...]:
    """Register the stand-ins for one test; the registry is restored afterwards."""
    for cap in FAKE_CAPABILITIES:
        monkeypatch.setitem(reg._REGISTRY, cap.id, cap)
    return FAKE_CAPABILITIES
