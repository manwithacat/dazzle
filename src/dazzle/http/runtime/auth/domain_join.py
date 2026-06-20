"""Verified-domain self-service join — pure decision logic (#1424).

Two concerns, kept separate:
  * admission control (``assert_domain_admissible``) — the uniform tenant
    restriction enforced on EVERY membership-creating path;
  * join policy (``decide_domain_join``, Task 3.x) — what a verified-domain
    match does (off / auto_join / admin_approval).

No FastAPI, no DB driver — the store is passed in, so this is exhaustively
unit-testable (mirrors apex_discovery.resolve_apex_redirect's style).
"""

from typing import Any

from dazzle.http.runtime.auth.org_settings import OrgSettings


class DomainNotAdmissibleError(RuntimeError):
    """A membership cannot be created: the tenant restricts membership to its
    verified domains and this email's domain is not among them."""

    reason = "domain_not_admissible"


def email_domain(email: str) -> str:
    """Lowercased domain part of ``email``, or ``""`` if malformed."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def tenant_verified_domains(store: Any, tenant_id: str) -> set[str]:
    """Union of verified domains across all the tenant's connections."""
    out: set[str] = set()
    for conn in store.get_connections_for_tenant(tenant_id):
        out.update(d.strip().lower() for d in (conn.verified_domains or []))
    return out


def assert_domain_admissible(store: Any, tenant_id: str, email: str) -> None:
    """Fail-closed admission gate. No-op when the tenant does not restrict;
    otherwise the email's domain MUST be in the tenant's verified set."""
    settings = OrgSettings.from_dict(store.get_org_settings(tenant_id))
    if not settings.restrict_membership_to_verified_domains:
        return
    domain = email_domain(email)
    if not domain or domain not in tenant_verified_domains(store, tenant_id):
        raise DomainNotAdmissibleError(
            f"email domain {domain!r} is not a verified domain for this organization"
        )
