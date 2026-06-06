"""Process-wide capability registry + boot-time resolution (#1342)."""

from importlib.util import find_spec

from dazzle.core.capabilities.models import (
    Capability,
    CapabilityUnavailableError,
    ResolvedCapabilities,
)

_REGISTRY: dict[str, Capability] = {}


def register(capability: Capability) -> None:
    """Register a capability. Idempotent across imports (last wins)."""
    _REGISTRY[capability.id] = capability


def get(capability_id: str) -> Capability | None:
    return _REGISTRY.get(capability_id)


def all_capabilities() -> list[Capability]:
    return sorted(_REGISTRY.values(), key=lambda c: c.id)


def known_capability_ids() -> set[str]:
    return set(_REGISTRY)


def unknown_capability_ids(declared: list[str]) -> list[str]:
    """Declared ids with no registered capability (for validate diagnostics)."""
    known = known_capability_ids()
    return [cid for cid in declared if cid not in known]


def active_capability_ids(declared: list[str]) -> set[str]:
    """The subset of declared ids that are registered AND available.

    Non-raising (unlike :func:`resolve_capabilities`): for advisory/cognition
    surfaces (bootstrap, lint relevance, spec-analyze) that must never crash on an
    unavailable or unknown declared capability — those are simply omitted from the
    active set rather than raising a boot error.
    """
    return {cid for cid in declared if (cap := get(cid)) is not None and is_available(cap)}


def suggest_capability(unknown_id: str) -> str | None:
    """Closest known capability id to a typo'd one, or None (shared by the CLI
    and `dazzle validate` so the did-you-mean hint stays consistent)."""
    import difflib

    matches = difflib.get_close_matches(unknown_id, sorted(known_capability_ids()), n=1)
    return matches[0] if matches else None


def is_available(capability: Capability) -> bool:
    """True iff the capability is usable in this runtime.

    A capability with ``probe_module is None`` has no import-time dependency and
    is always available. Otherwise its probe module must be importable.
    ``find_spec`` is guarded: a dotted module whose parent package is missing
    raises ``ModuleNotFoundError`` rather than returning None.
    """
    if capability.probe_module is None:
        return True
    try:
        return find_spec(capability.probe_module) is not None
    except ModuleNotFoundError:
        return False


def resolve_capabilities(declared: list[str]) -> ResolvedCapabilities:
    """Compute active/unavailable from the declared list.

    Unknown ids are ignored here (``validate`` reports them); this function
    concerns *availability*. Raises ``CapabilityUnavailableError`` listing every
    declared-but-unavailable capability with its remediation runbook.
    """
    active: set[str] = set()
    unavailable: set[str] = set()
    for cid in declared:
        cap = _REGISTRY.get(cid)
        if cap is None:
            continue  # unknown — handled by validate, not a boot error here
        if is_available(cap):
            active.add(cid)
        else:
            unavailable.add(cid)

    if unavailable:
        lines = [f"  - {cid}: {_REGISTRY[cid].remediation}" for cid in sorted(unavailable)]
        raise CapabilityUnavailableError(
            "These capabilities are declared in [capabilities] but their packages "
            "are not installed:\n" + "\n".join(lines)
        )

    return ResolvedCapabilities(active=frozenset(active), declared=tuple(declared))


# --- Enterprise auth capabilities (consumer #1) -----------------------------
register(
    Capability(
        id="auth.enterprise.oidc",
        label="Enterprise OIDC SSO",
        probe_module="authlib",
        required_extras=("sso",),
        remediation="pip install 'dazzle-dsl[sso]'",
    )
)
register(
    Capability(
        id="auth.enterprise.saml",
        label="Enterprise SAML SSO",
        probe_module="onelogin",
        required_extras=("saml",),
        remediation="pip install 'dazzle-dsl[saml]'  # needs native libxmlsec1",
    )
)
register(
    Capability(
        id="auth.enterprise.scim",
        label="Enterprise SCIM provisioning",
        # SCIM is stateless bearer auth over JSON with no import-time dependency
        # (it mounted unconditionally pre-#1342). Always available once declared —
        # no extra to install, so no probe and no remediation runbook.
        probe_module=None,
        required_extras=(),
        remediation="",
    )
)
