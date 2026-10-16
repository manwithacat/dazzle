"""Enterprise auth boot guard (#1344, DD-013): ``[auth.enterprise] protocols`` gates the
OIDC and SCIM route groups.

Two checks, both pure logic so they are unit-tested without a DB or an app; the DB read
and the logging live in the store and the lifespan hook respectively:

* :func:`require_protocol_extras` — a declared protocol whose Python extra does not import
  is a boot **error** at subsystem setup. Declaring ``oidc`` without ``authlib`` is a
  deployment mistake that must stop the boot, never a silent skip.
* :func:`undeclared_connection_errors` — connection rows whose type is not a declared
  protocol mount no routes (SSO/SCIM will 404). That mismatch is SAFE (feature off, no
  security hole) but quiet, so it is logged at ERROR at startup rather than aborting a
  deploy that is otherwise healthy.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterable, Mapping

# protocol -> the importable modules its runtime needs. ``cryptography`` encrypts every
# connection secret at rest (OIDC client_secret, SCIM bearer); ``authlib`` drives OIDC.
# Both ship in the ``sso`` extra.
_PROTOCOL_MODULES: dict[str, tuple[str, ...]] = {
    "oidc": ("authlib", "cryptography"),
    "scim": ("cryptography",),
}

# Routing-only connections (verified-domain join) carry no protocol and need no routes.
_ROUTING_ONLY_TYPES = frozenset({"domain"})


class EnterpriseAuthBootError(RuntimeError):
    """A declared enterprise protocol cannot run in this install."""


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def missing_protocol_extras(protocols: Iterable[str]) -> list[str]:
    """One message per declared protocol whose required modules do not import."""
    problems: list[str] = []
    for protocol in protocols:
        missing = [m for m in _PROTOCOL_MODULES.get(protocol, ()) if not _module_available(m)]
        if missing:
            problems.append(
                f"[auth.enterprise] declares {protocol!r} but {', '.join(missing)} "
                "is not installed. Install the extra: pip install 'dazzle-dsl[sso]'"
            )
    return problems


def require_protocol_extras(protocols: Iterable[str]) -> None:
    """Raise :class:`EnterpriseAuthBootError` when any declared protocol cannot run."""
    problems = missing_protocol_extras(protocols)
    if problems:
        raise EnterpriseAuthBootError("; ".join(problems))


def undeclared_connection_errors(
    type_counts: Mapping[str, int],
    protocols: Iterable[str],
) -> list[str]:
    """One actionable message per connection type with rows but no declared protocol."""
    declared = set(protocols)
    errors: list[str] = []
    for ctype, n in sorted(type_counts.items()):
        if n <= 0 or ctype in _ROUTING_ONLY_TYPES or ctype in declared:
            continue
        errors.append(
            f"{n} {ctype} connection(s) exist but {ctype!r} is not in [auth.enterprise] "
            "protocols — their routes will not mount (SSO/SCIM will 404). Add it to "
            "[auth.enterprise] protocols in dazzle.toml (DD-013)."
        )
    return errors
