"""DNS-TXT domain-ownership verification for enterprise connections (auth Plan 4b.iv).

Verifying a domain is what moves it from *claimed* (``connection.domains``) to *trusted*
(``connection.verified_domains``) — and only verified domains route email→org or let an
IdP assert identities (the anti-hijack gate the routing + JIT join depend on).

The verification token is **HMAC-SHA256(connection-secret-key, "domain-verify:<conn_id>:
<domain>")** — deterministic (no storage / migration), and unforgeable without the
deployment's ``DAZZLE_CONNECTION_SECRET`` (the key connections already require). The org
admin publishes ``dazzle-verify=<token>`` as a DNS TXT record on the domain; ``verify_domain``
looks it up through an injectable resolver (dnspython in production, a fake in tests),
enforces one-owner-per-domain, and on a match appends the domain to ``verified_domains``.

``dnspython`` is an enterprise-connections (``[sso]`` extra) dependency, imported lazily.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Protocol, runtime_checkable

from dazzle.http.runtime.auth.connection_crypto import _load_key

_TXT_PREFIX = "dazzle-verify="

# Postgres advisory-lock key serializing verified-domain claims (one verified owner
# per domain). All verification writes take this single lock so concurrent verifies
# can't both claim a domain or lost-update a connection's domain list. Distinct from
# MEMBERSHIP_EVENTS_LOCK_KEY (0x6D656D65). "dzdv" = domain verify.
CONNECTION_DOMAIN_LOCK_KEY = 0x647A6476


class DomainVerificationError(RuntimeError):
    """A domain cannot be verified. ``reason`` is a stable machine code
    (``already_verified_elsewhere`` / ``txt_not_found``); the message is human detail."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def _normalize(domain: str) -> str:
    return domain.strip().lower().rstrip(".")


def verification_token(connection_id: str, domain: str) -> str:
    """The unforgeable per-(connection, domain) token.

    HMAC under ``DAZZLE_CONNECTION_SECRET`` (via :func:`_load_key`, which raises
    fail-closed when the key is absent). Including ``connection_id`` AND ``domain``
    means a token published for one pair never verifies another.
    """
    key = _load_key()
    msg = f"domain-verify:{connection_id}:{_normalize(domain)}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def txt_record(connection_id: str, domain: str) -> str:
    """The full DNS TXT record value the admin must publish on ``domain``."""
    return f"{_TXT_PREFIX}{verification_token(connection_id, domain)}"


@runtime_checkable
class DnsTxtResolver(Protocol):
    """Resolves a domain's TXT records to a list of strings (the seam for tests)."""

    def resolve_txt(self, domain: str) -> list[str]: ...


class DnspythonResolver:
    """Production resolver — dnspython TXT lookup. A lookup failure (NXDOMAIN, no
    answer, timeout) yields ``[]`` so verification simply doesn't match (never a
    silent pass, never a crash)."""

    def resolve_txt(self, domain: str) -> list[str]:
        import dns.exception  # lazy — [sso] extra
        import dns.resolver

        try:
            answers = dns.resolver.resolve(_normalize(domain), "TXT")
        except dns.exception.DNSException:
            # NXDOMAIN / NoAnswer / Timeout / NoNameservers ⇒ "no records" (a real
            # programming bug still propagates — we only swallow DNS-level outcomes).
            return []
        records: list[str] = []
        for rdata in answers:
            # A TXT rdata is one-or-more quoted strings; join the byte chunks.
            parts = getattr(rdata, "strings", None)
            if parts is not None:
                records.append(b"".join(parts).decode("utf-8", "replace"))
            else:
                records.append(str(rdata).strip('"'))
        return records


def verify_domain(
    store: Any,
    connection: Any,
    domain: str,
    *,
    resolver: DnsTxtResolver,
) -> bool:
    """Verify ``domain`` for ``connection`` via DNS TXT; on success add it to
    ``verified_domains`` and return ``True``. Return ``False`` when the expected TXT
    record isn't present yet.

    Raises ``DomainVerificationError("already_verified_elsewhere")`` if a *different*
    connection already owns the domain (one verified owner per domain — the routing
    layer can't disambiguate two). Re-verifying for the same connection is idempotent.

    The DNS lookup runs first (outside any lock); the ownership check + write are then
    delegated to ``store.claim_verified_domain``, which is advisory-lock-serialized so
    two concurrent verifications can't both win the same domain.
    """
    norm = _normalize(domain)

    # Fast fail (non-authoritative) — skip the DNS round-trip when another connection
    # plainly already owns it. The atomic claim below is the real enforcer.
    existing = store.get_connection_by_verified_domain(norm)
    if existing is not None and existing.id != connection.id:
        raise DomainVerificationError(
            "already_verified_elsewhere",
            "this domain is already verified by another connection",
        )

    expected = txt_record(connection.id, norm)
    if expected not in resolver.resolve_txt(norm):
        return False

    # Atomic, race-safe claim (enforces one-owner-per-domain under concurrency).
    if not store.claim_verified_domain(connection.id, norm):
        raise DomainVerificationError(
            "already_verified_elsewhere",
            "this domain is already verified by another connection",
        )
    return True
