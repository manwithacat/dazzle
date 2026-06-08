"""Capability boot guard (#1344): warn when connection rows exist for a protocol whose
enterprise capability isn't active (its routes silently don't mount). Pure logic — the DB
read and logging live in the store / the lifespan hook respectively, so the mapping +
mismatch detection is unit-tested directly."""

from __future__ import annotations

from collections.abc import Callable, Mapping

# connection.type -> the capability that must be active for its routes to mount.
_TYPE_TO_CAPABILITY: dict[str, str] = {
    "oidc": "auth.enterprise.oidc",
    "saml": "auth.enterprise.saml",
    "scim": "auth.enterprise.scim",
}


def capability_boot_warnings(
    type_counts: Mapping[str, int],
    is_active: Callable[[str], bool],
) -> list[str]:
    """One actionable warning per connection type whose enterprise capability isn't active.

    A mismatch is SAFE (feature-off, no security hole) but quiet; the warning is the loud,
    actionable signal. Types not in the enterprise map (none today) are ignored.
    """
    warnings: list[str] = []
    for ctype, capability in _TYPE_TO_CAPABILITY.items():
        n = type_counts.get(ctype, 0)
        if n > 0 and not is_active(capability):
            warnings.append(
                f"{n} {ctype} connection(s) exist but {capability} is not enabled — "
                f"their routes will not mount (SSO/SCIM will 404). Add {capability} to "
                f"[capabilities] in dazzle.toml or run: dazzle capability enable {capability}"
            )
    return warnings
