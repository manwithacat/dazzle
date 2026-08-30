"""Custom-domain hostname aliases (ADR-0055 PR4).

A customer hostname is an **alias of an existing tenant id** under the app's
A (apex) or B (provider_subdomain) topology — not a third topology token.
Attach: TXT then CNAME (+ ops SNI). Detach: keep serving until DNS is gone,
then cool ≥24h so the hostname is not reused while records might still
point here.

TXT lookup reuses the injectable DNS seam from
``dazzle.http.runtime.auth.domain_verification``. Do **not** reuse
``dazzle auth connection verify-domain`` or its HMAC tokens; CLI, table,
and attach lifecycle are a different plane.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast, runtime_checkable
from uuid import UUID

from dazzle.http.runtime.auth.domain_verification import DnspythonResolver, DnsTxtResolver
from dazzle.http.runtime.tenant.metrics import note_alias_verify

# Fail-closed: missing/mismatched TXT never verifies.
_TXT_PREFIX = "dazzle-verify="
_CHALLENGE_LABEL = "_dazzle-challenge"
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

LIVE_STATES = frozenset({"pending_txt", "pending_cname", "active", "pending_detach"})
SERVING_STATES = frozenset({"active", "pending_detach"})
COOLING = timedelta(hours=24)

ALIAS_STATES = (
    "pending_txt",
    "pending_cname",
    "active",
    "pending_detach",
    "cooling",
)


class AliasError(RuntimeError):
    """A hostname alias cannot move. ``reason`` is a stable machine code."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


@dataclass(frozen=True)
class AliasRow:
    id: UUID
    tenant_id: str
    hostname: str
    state: str
    txt_token: str
    cname_target: str
    verified_at: datetime | None = None
    attached_at: datetime | None = None
    detach_requested_at: datetime | None = None
    reusable_after: datetime | None = None


def ensure_tenant_host_aliases_table(cur: Any) -> None:
    """Create ``tenant_host_aliases`` (idempotent). Orchestrator + Alembic 0020."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenant_host_aliases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id TEXT NOT NULL,
            hostname TEXT NOT NULL,
            state TEXT NOT NULL,
            txt_token TEXT NOT NULL,
            cname_target TEXT NOT NULL,
            verified_at TIMESTAMPTZ,
            attached_at TIMESTAMPTZ,
            detach_requested_at TIMESTAMPTZ,
            reusable_after TIMESTAMPTZ,
            CONSTRAINT uq_tenant_host_aliases_hostname UNIQUE (hostname),
            CONSTRAINT tenant_host_aliases_state_check CHECK (
                state IN (
                    'pending_txt',
                    'pending_cname',
                    'active',
                    'pending_detach',
                    'cooling'
                )
            )
        )
    """)
    # v1: one live hostname per tenant (pending counts; cooling does not).
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_host_aliases_one_live
        ON tenant_host_aliases (tenant_id)
        WHERE state IN ('pending_txt', 'pending_cname', 'active', 'pending_detach')
    """)


def normalize_hostname(hostname: str) -> str:
    return hostname.strip().lower().rstrip(".")


def txt_name(hostname: str) -> str:
    return f"{_CHALLENGE_LABEL}.{normalize_hostname(hostname)}"


def txt_value(token: str) -> str:
    return f"{_TXT_PREFIX}{token}"


def validate_alias_hostname(
    hostname: str,
    *,
    provider_domain: str,
    canonical_hosts: tuple[str, ...] | list[str] = (),
) -> str:
    """Lowercase, no scheme/port/path; refuse bare apex and provider-domain names."""
    raw = hostname.strip()
    if "://" in raw or "/" in raw or ":" in raw or " " in raw:
        raise AliasError("invalid_hostname", "hostname must have no scheme, port, or path")
    host = normalize_hostname(raw)
    if not _HOSTNAME_RE.match(host):
        raise AliasError("invalid_hostname", f"invalid hostname {host!r}")
    labels = host.split(".")
    if len(labels) < 3:
        raise AliasError(
            "bare_apex",
            "bare customer apex is out of v1; use a hostname like app.customer.com",
        )
    canon = {h.strip().lower().rstrip(".") for h in canonical_hosts}
    if host in canon:
        raise AliasError("canonical_host", "hostname is a canonical/marketing host")
    suffix = "." + provider_domain.strip().lower().rstrip(".")
    if provider_domain and (host.endswith(suffix) or host == suffix[1:]):
        raise AliasError(
            "provider_suffix",
            "hostname is on the provider domain; aliases compose with A/B, they are not slugs",
        )
    return host


@runtime_checkable
class DnsCnameResolver(Protocol):
    def resolve_cname(self, name: str) -> list[str]: ...


def default_txt_resolver() -> DnsTxtResolver:
    """Production TXT resolver (dnspython; DNS errors → no records)."""
    return DnspythonResolver()


class DnspythonCnameResolver:
    """Production CNAME lookup. DNS errors → no records (fail-closed)."""

    def resolve_cname(self, name: str) -> list[str]:
        import dns.exception
        import dns.resolver

        try:
            answers = dns.resolver.resolve(normalize_hostname(name), "CNAME")
        except dns.exception.DNSException:
            return []
        targets: list[str] = []
        for rdata in answers:
            target = getattr(rdata, "target", None)
            if target is not None:
                targets.append(str(target).rstrip(".").lower())
            else:
                targets.append(str(rdata).rstrip(".").lower())
        return targets


def default_cname_resolver() -> DnsCnameResolver:
    return DnspythonCnameResolver()


def txt_matches(resolver: DnsTxtResolver, hostname: str, token: str) -> bool:
    expected = txt_value(token)
    return expected in resolver.resolve_txt(txt_name(hostname))


def cname_matches(resolver: DnsCnameResolver, hostname: str, target: str) -> bool:
    want = normalize_hostname(target)
    return any(normalize_hostname(a) == want for a in resolver.resolve_cname(hostname))


def dns_gone(
    hostname: str,
    *,
    txt_token: str,
    cname_target: str,
    txt_resolver: DnsTxtResolver,
    cname_resolver: DnsCnameResolver,
) -> bool:
    """True when neither the challenge TXT nor our CNAME is still published."""
    return not txt_matches(txt_resolver, hostname, txt_token) and not cname_matches(
        cname_resolver, hostname, cname_target
    )


def _row_to_alias(row: Any) -> AliasRow:
    if isinstance(row, dict):
        data = row
    elif hasattr(row, "keys"):
        data = {k: row[k] for k in row.keys()}
    else:
        raise TypeError(f"unexpected alias row type {type(row)!r}")
    raw_id = data["id"]
    alias_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    return AliasRow(
        id=alias_id,
        tenant_id=str(data["tenant_id"]),
        hostname=str(data["hostname"]),
        state=str(data["state"]),
        txt_token=str(data["txt_token"]),
        cname_target=str(data["cname_target"]),
        verified_at=data.get("verified_at"),
        attached_at=data.get("attached_at"),
        detach_requested_at=data.get("detach_requested_at"),
        reusable_after=data.get("reusable_after"),
    )


class AliasStore:
    """Postgres access for ``tenant_host_aliases``."""

    _COLS = (
        "id, tenant_id, hostname, state, txt_token, cname_target, "
        "verified_at, attached_at, detach_requested_at, reusable_after"
    )

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def get_by_hostname(self, hostname: str) -> AliasRow | None:
        cur = self._conn.execute(
            f"SELECT {self._COLS} FROM tenant_host_aliases WHERE hostname = %s",
            (normalize_hostname(hostname),),
        )
        row = cur.fetchone()
        return _row_to_alias(row) if row is not None else None

    def get_serving(self, hostname: str) -> AliasRow | None:
        cur = self._conn.execute(
            f"SELECT {self._COLS} FROM tenant_host_aliases WHERE hostname = %s AND state = ANY(%s)",
            (normalize_hostname(hostname), list(SERVING_STATES)),
        )
        row = cur.fetchone()
        return _row_to_alias(row) if row is not None else None

    def list_live_for_tenant(self, tenant_id: str) -> list[AliasRow]:
        cur = self._conn.execute(
            f"SELECT {self._COLS} FROM tenant_host_aliases "
            "WHERE tenant_id = %s AND state = ANY(%s)",
            (str(tenant_id), list(LIVE_STATES)),
        )
        return [_row_to_alias(r) for r in cur.fetchall()]

    def insert(
        self,
        *,
        tenant_id: str,
        hostname: str,
        txt_token: str,
        cname_target: str,
        state: str = "pending_txt",
    ) -> AliasRow:
        cur = self._conn.execute(
            f"""
            INSERT INTO tenant_host_aliases
                (tenant_id, hostname, state, txt_token, cname_target)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING {self._COLS}
            """,
            (str(tenant_id), hostname, state, txt_token, cname_target),
        )
        row = cur.fetchone()
        assert row is not None
        return _row_to_alias(row)

    def save(self, row: AliasRow) -> AliasRow:
        cur = self._conn.execute(
            f"""
            UPDATE tenant_host_aliases SET
                state = %s,
                verified_at = %s,
                attached_at = %s,
                detach_requested_at = %s,
                reusable_after = %s
            WHERE id = %s
            RETURNING {self._COLS}
            """,
            (
                row.state,
                row.verified_at,
                row.attached_at,
                row.detach_requested_at,
                row.reusable_after,
                str(row.id),
            ),
        )
        updated = cur.fetchone()
        assert updated is not None
        return _row_to_alias(updated)

    def delete(self, alias_id: UUID) -> None:
        self._conn.execute("DELETE FROM tenant_host_aliases WHERE id = %s", (str(alias_id),))


def claim(
    store: Any,
    *,
    tenant_id: str,
    hostname: str,
    cname_target: str,
    provider_domain: str,
    canonical_hosts: tuple[str, ...] | list[str] = (),
    now: datetime | None = None,
) -> AliasRow:
    host = validate_alias_hostname(
        hostname, provider_domain=provider_domain, canonical_hosts=canonical_hosts
    )
    target = normalize_hostname(cname_target)
    if not target:
        raise AliasError("invalid_cname_target", "cname target is required")
    moment = now or datetime.now(UTC)
    existing = store.get_by_hostname(host)
    if existing is not None:
        if existing.state == "cooling":
            until = existing.reusable_after
            if until is not None and until > moment:
                raise AliasError(
                    "cooling",
                    f"hostname is in cooling until {until.isoformat()}; refuse reuse",
                )
            store.delete(existing.id)
        else:
            raise AliasError("taken", f"hostname {host!r} is already claimed ({existing.state})")
    live = store.list_live_for_tenant(str(tenant_id))
    if live:
        raise AliasError(
            "one_active",
            "v1 allows one live alias hostname per tenant",
        )
    token = secrets.token_urlsafe(32)
    return cast(
        AliasRow,
        store.insert(
            tenant_id=str(tenant_id),
            hostname=host,
            txt_token=token,
            cname_target=target,
        ),
    )


def verify_step(
    store: Any,
    hostname: str,
    *,
    txt_resolver: DnsTxtResolver,
    cname_resolver: DnsCnameResolver,
    now: datetime | None = None,
) -> AliasRow:
    """Advance one attach step. TXT fail-closed; CNAME fail-closed."""
    row = store.get_by_hostname(hostname)
    if row is None:
        note_alias_verify("not_found")
        raise AliasError("not_found", f"no alias claimed for {hostname!r}")
    moment = now or datetime.now(UTC)
    if row.state == "pending_txt":
        if not txt_matches(txt_resolver, row.hostname, row.txt_token):
            note_alias_verify("txt_not_found")
            raise AliasError("txt_not_found", "expected TXT record is missing or mismatched")
        note_alias_verify("txt_ok")
        return cast(AliasRow, store.save(replace(row, state="pending_cname", verified_at=moment)))
    if row.state == "pending_cname":
        if not cname_matches(cname_resolver, row.hostname, row.cname_target):
            note_alias_verify("cname_not_found")
            raise AliasError("cname_not_found", "expected CNAME is missing or mismatched")
        note_alias_verify("cname_ok")
        return cast(AliasRow, store.save(replace(row, state="active", attached_at=moment)))
    note_alias_verify("wrong_state")
    raise AliasError("wrong_state", f"alias is {row.state}; nothing to verify")


def detach(
    store: Any,
    hostname: str,
    *,
    txt_resolver: DnsTxtResolver,
    cname_resolver: DnsCnameResolver,
    now: datetime | None = None,
) -> AliasRow | None:
    """Detach lifecycle.

    * pending_txt / pending_cname: abandon (delete; never went live).
    * active → pending_detach (keep serving).
    * pending_detach: refuse until DNS is gone, then cooling ≥24h.
    """
    row = store.get_by_hostname(hostname)
    if row is None:
        raise AliasError("not_found", f"no alias claimed for {hostname!r}")
    moment = now or datetime.now(UTC)
    if row.state in {"pending_txt", "pending_cname"}:
        store.delete(row.id)
        return None
    if row.state == "active":
        return cast(
            AliasRow,
            store.save(replace(row, state="pending_detach", detach_requested_at=moment)),
        )
    if row.state == "pending_detach":
        if not dns_gone(
            row.hostname,
            txt_token=row.txt_token,
            cname_target=row.cname_target,
            txt_resolver=txt_resolver,
            cname_resolver=cname_resolver,
        ):
            raise AliasError(
                "dns_still_live",
                "refuse cooling while TXT or CNAME still points here",
            )
        return cast(
            AliasRow, store.save(replace(row, state="cooling", reusable_after=moment + COOLING))
        )
    raise AliasError("wrong_state", f"alias is {row.state}; nothing to detach")
