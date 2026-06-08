"""Administrative-capability authorization for the framework's org-admin surfaces.

Generalizes the flat ``org_admin_roles`` gate: the framework names a small fixed set of admin
CAPABILITIES (the "actions"), the app binds each to a set of personas (the "principals") in the
manifest, and a check is the set-intersection of the caller's effective in-org roles with the
capability's persona set. Default-deny, fail-closed. ``org_admin_roles`` is the default persona set
for any capability not explicitly mapped, so apps that set only ``org_admin_roles`` are unchanged.

This is the framework's OWN admin surfaces only (members, connections) — separate from the
app-domain ``permit:``/``scope:``/``grant_schema`` plane. Pure + I/O-free → unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: The framework-defined admin capabilities. The single source of truth (tests + drift gate
#: assert against this). Add a name here (and wire a surface to it) to introduce a capability.
CAPABILITIES: tuple[str, ...] = ("manage_members", "manage_connections")


@dataclass(frozen=True)
class AdminPolicy:
    """Resolved ``capability -> frozenset[persona]`` for one app. Built once at boot."""

    _by_capability: Mapping[str, frozenset[str]]

    @classmethod
    def from_config(
        cls,
        *,
        org_admin_roles: Iterable[str] | None,
        admin_capabilities: Mapping[str, Iterable[str]] | None,
    ) -> AdminPolicy:
        default = frozenset(org_admin_roles or ())
        caps = admin_capabilities or {}
        resolved: dict[str, frozenset[str]] = {}
        for cap in CAPABILITIES:
            roles = caps.get(cap)
            # An explicitly-empty / missing list falls back to org_admin_roles, so adding one
            # capability's map never silently locks out another.
            resolved[cap] = frozenset(roles) if roles else default
        return cls(resolved)

    def may(self, capability: str, effective_roles: Iterable[str]) -> bool:
        """True iff a member with ``effective_roles`` holds ``capability``. Fail-closed: an
        unknown capability or an empty resolved set denies."""
        allowed = self._by_capability.get(capability)
        if not allowed:
            return False
        return bool(set(effective_roles) & allowed)

    def roles_for(self, capability: str) -> frozenset[str]:
        """The resolved persona set for ``capability`` (empty for an unknown capability)."""
        return self._by_capability.get(capability, frozenset())


def unknown_admin_personas(
    admin_capabilities: Mapping[str, Iterable[str]], declared_personas: Iterable[str]
) -> set[str]:
    """Persona names referenced in ``admin_capabilities`` that aren't declared personas — a typo
    that would silently grant nobody. Returns the offending names (empty when all are known)."""
    declared = set(declared_personas)
    referenced: set[str] = set()
    for roles in admin_capabilities.values():
        referenced.update(roles)
    return referenced - declared
