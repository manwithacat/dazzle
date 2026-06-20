"""Transport-agnostic data-access core (#1422 option b).

The enforcement+data logic relocated out of the REST route-handler closures so
both the REST API and the HTML page layer call ONE core, in-process, instead of
the page layer self-fetching its own REST endpoint over loopback HTTP.

Scope (tenant isolation) is already compiled into Repository SQL via the
``__scope_predicate`` filter key; permit (Cedar) is relocated here from the route
closures. See docs/superpowers/specs/2026-06-20-page-rest-inprocess-core-design.md.
"""

from dataclasses import dataclass
from typing import Any


class AccessForbidden(Exception):
    """Permit (Cedar) denied the operation."""


class RecordNotFound(Exception):
    """Row is missing or hidden by a scope predicate."""


@dataclass(frozen=True)
class AccessContext:
    """Everything enforcement needs, bundled once per request."""

    auth_context: Any
    entity_name: str
    cedar_access_spec: Any | None
    fk_graph: Any | None
    admin_personas: list[str] | None


def access_context_from(
    *,
    auth_context: Any,
    entity_name: str,
    cedar_access_spec: Any | None,
    fk_graph: Any | None,
    admin_personas: list[str] | None,
) -> AccessContext:
    """Bundle the per-request enforcement inputs into an AccessContext."""
    return AccessContext(
        auth_context=auth_context,
        entity_name=entity_name,
        cedar_access_spec=cedar_access_spec,
        fk_graph=fk_graph,
        admin_personas=admin_personas,
    )
