"""Capability model for the opt-in feature-gating system (#1342).

A capability is a framework feature an app must explicitly opt into via
``[capabilities]`` in dazzle.toml. Each one self-describes the pip extra it needs
(for the runbook) and the importable module used to probe availability.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    """A declarable, gateable framework capability.

    Attributes:
        id: Dotted identifier, e.g. ``auth.enterprise.oidc``.
        label: Human-readable name for CLI/diagnostics.
        probe_module: Importable module whose presence means the capability is
            *available* in this runtime (e.g. ``authlib``). Probed with
            ``importlib.util.find_spec``.
        required_extras: pip extras that install ``probe_module`` (for the
            remediation runbook), e.g. ``("sso",)``.
        remediation: Exact, actionable fix shown when declared-but-unavailable.
    """

    id: str
    label: str
    probe_module: str
    required_extras: tuple[str, ...]
    remediation: str


class CapabilityUnavailableError(RuntimeError):
    """Raised at boot when a declared capability's extra is not installed."""


@dataclass(frozen=True, slots=True)
class ResolvedCapabilities:
    """Boot-time resolution of declared capabilities.

    ``active`` = declared ∧ available. ``unavailable`` = declared ∧ not-installed
    (each a boot error). ``declared`` is the raw manifest list (for diagnostics).
    """

    active: frozenset[str]
    unavailable: frozenset[str]
    declared: tuple[str, ...]

    def is_active(self, capability_id: str) -> bool:
        return capability_id in self.active
