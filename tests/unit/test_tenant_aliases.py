"""Custom-domain aliases (ADR-0055 PR4) — lifecycle, DNS fail-closed, hostname rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from dazzle.http.runtime.tenant.aliases import (
    COOLING,
    AliasError,
    AliasRow,
    claim,
    cname_matches,
    detach,
    dns_gone,
    txt_matches,
    txt_name,
    txt_value,
    validate_alias_hostname,
    verify_step,
)

pytestmark = pytest.mark.gate


def test_validate_rejects_bare_apex() -> None:
    with pytest.raises(AliasError) as exc:
        validate_alias_hostname("customer.com", provider_domain="example.com")
    assert exc.value.reason == "bare_apex"


def test_validate_rejects_provider_suffix() -> None:
    with pytest.raises(AliasError) as exc:
        validate_alias_hostname("acme.example.com", provider_domain="example.com")
    assert exc.value.reason == "provider_suffix"


def test_validate_rejects_canonical_host() -> None:
    with pytest.raises(AliasError) as exc:
        validate_alias_hostname(
            "www.example.com",
            provider_domain="saas.io",
            canonical_hosts=("www.example.com",),
        )
    assert exc.value.reason == "canonical_host"


def test_validate_rejects_scheme_and_port() -> None:
    with pytest.raises(AliasError) as exc:
        validate_alias_hostname("https://app.customer.com", provider_domain="example.com")
    assert exc.value.reason == "invalid_hostname"
    with pytest.raises(AliasError) as exc2:
        validate_alias_hostname("app.customer.com:443", provider_domain="example.com")
    assert exc2.value.reason == "invalid_hostname"


def test_validate_accepts_app_customer_host() -> None:
    assert (
        validate_alias_hostname("App.Customer.com.", provider_domain="example.com")
        == "app.customer.com"
    )


def test_txt_fail_closed_on_empty_and_mismatch() -> None:
    class Empty:
        def resolve_txt(self, name: str) -> list[str]:
            return []

    class Other:
        def resolve_txt(self, name: str) -> list[str]:
            return ["dazzle-verify=nope"]

    assert txt_matches(Empty(), "app.customer.com", "token") is False
    assert txt_matches(Other(), "app.customer.com", "token") is False
    assert txt_name("app.customer.com") == "_dazzle-challenge.app.customer.com"


def test_txt_matches_expected_record() -> None:
    token = "abc"

    class Hit:
        def resolve_txt(self, name: str) -> list[str]:
            assert name == txt_name("app.customer.com")
            return [txt_value(token)]

    assert txt_matches(Hit(), "app.customer.com", token) is True


def test_cname_fail_closed() -> None:
    class Empty:
        def resolve_cname(self, name: str) -> list[str]:
            return []

    assert cname_matches(Empty(), "app.customer.com", "customers.example.com") is False


# ---------------------------------------------------------------------------
# In-memory store for lifecycle tests
# ---------------------------------------------------------------------------


@dataclass
class _MemStore:
    rows: dict[str, AliasRow]

    def get_by_hostname(self, hostname: str) -> AliasRow | None:
        return self.rows.get(hostname.strip().lower().rstrip("."))

    def get_serving(self, hostname: str) -> AliasRow | None:
        row = self.get_by_hostname(hostname)
        if row is not None and row.state in {"active", "pending_detach"}:
            return row
        return None

    def list_live_for_tenant(self, tenant_id: str) -> list[AliasRow]:
        live = {"pending_txt", "pending_cname", "active", "pending_detach"}
        return [r for r in self.rows.values() if r.tenant_id == tenant_id and r.state in live]

    def insert(
        self,
        *,
        tenant_id: str,
        hostname: str,
        txt_token: str,
        cname_target: str,
        state: str = "pending_txt",
    ) -> AliasRow:
        row = AliasRow(
            id=uuid4(),
            tenant_id=tenant_id,
            hostname=hostname,
            state=state,
            txt_token=txt_token,
            cname_target=cname_target,
        )
        self.rows[hostname] = row
        return row

    def save(self, row: AliasRow) -> AliasRow:
        self.rows[row.hostname] = row
        return row

    def delete(self, alias_id: UUID) -> None:
        dead = [k for k, v in self.rows.items() if v.id == alias_id]
        for k in dead:
            del self.rows[k]


class _Txt:
    def __init__(self, records: dict[str, list[str]]) -> None:
        self.records = records

    def resolve_txt(self, name: str) -> list[str]:
        return list(self.records.get(name, []))


class _Cname:
    def __init__(self, records: dict[str, list[str]]) -> None:
        self.records = records

    def resolve_cname(self, name: str) -> list[str]:
        return list(self.records.get(name, []))


def test_claim_verify_detach_cooling() -> None:
    store = _MemStore(rows={})
    now = datetime(2026, 8, 30, tzinfo=UTC)
    row = claim(
        store,
        tenant_id="t1",
        hostname="app.customer.com",
        cname_target="customers.example.com",
        provider_domain="example.com",
        now=now,
    )
    assert row.state == "pending_txt"
    txt = _Txt({txt_name(row.hostname): [txt_value(row.txt_token)]})
    cname = _Cname({})
    row = verify_step(store, row.hostname, txt_resolver=txt, cname_resolver=cname, now=now)
    assert row.state == "pending_cname"
    cname = _Cname({row.hostname: ["customers.example.com"]})
    row = verify_step(store, row.hostname, txt_resolver=txt, cname_resolver=cname, now=now)
    assert row.state == "active"

    row = detach(store, row.hostname, txt_resolver=txt, cname_resolver=cname, now=now)
    assert row is not None and row.state == "pending_detach"

    with pytest.raises(AliasError) as exc:
        detach(store, row.hostname, txt_resolver=txt, cname_resolver=cname, now=now)
    assert exc.value.reason == "dns_still_live"

    gone_txt = _Txt({})
    gone_cname = _Cname({})
    row = detach(store, row.hostname, txt_resolver=gone_txt, cname_resolver=gone_cname, now=now)
    assert row is not None and row.state == "cooling"
    assert row.reusable_after == now + COOLING


def test_txt_verify_fail_closed_stays_pending() -> None:
    store = _MemStore(rows={})
    row = claim(
        store,
        tenant_id="t1",
        hostname="app.customer.com",
        cname_target="customers.example.com",
        provider_domain="example.com",
    )
    with pytest.raises(AliasError) as exc:
        verify_step(
            store,
            row.hostname,
            txt_resolver=_Txt({}),
            cname_resolver=_Cname({}),
        )
    assert exc.value.reason == "txt_not_found"
    assert store.get_by_hostname(row.hostname).state == "pending_txt"  # type: ignore[union-attr]


def test_v1_one_live_alias_per_tenant() -> None:
    store = _MemStore(rows={})
    claim(
        store,
        tenant_id="t1",
        hostname="app.customer.com",
        cname_target="customers.example.com",
        provider_domain="example.com",
    )
    with pytest.raises(AliasError) as exc:
        claim(
            store,
            tenant_id="t1",
            hostname="app.other.com",
            cname_target="customers.example.com",
            provider_domain="example.com",
        )
    assert exc.value.reason == "one_active"


def test_cooling_refuses_reuse_until_reusable_after() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    cooled = AliasRow(
        id=uuid4(),
        tenant_id="t1",
        hostname="app.customer.com",
        state="cooling",
        txt_token="x",
        cname_target="customers.example.com",
        reusable_after=now + timedelta(hours=12),
    )
    store = _MemStore(rows={cooled.hostname: cooled})
    with pytest.raises(AliasError) as exc:
        claim(
            store,
            tenant_id="t2",
            hostname="app.customer.com",
            cname_target="customers.example.com",
            provider_domain="example.com",
            now=now,
        )
    assert exc.value.reason == "cooling"

    later = now + timedelta(hours=25)
    row = claim(
        store,
        tenant_id="t2",
        hostname="app.customer.com",
        cname_target="customers.example.com",
        provider_domain="example.com",
        now=later,
    )
    assert row.state == "pending_txt"
    assert row.tenant_id == "t2"


def test_dns_gone_requires_both_txt_and_cname_absent() -> None:
    token = "tok"
    hostname = "app.customer.com"
    target = "customers.example.com"
    assert (
        dns_gone(
            hostname,
            txt_token=token,
            cname_target=target,
            txt_resolver=_Txt({}),
            cname_resolver=_Cname({}),
        )
        is True
    )
    assert (
        dns_gone(
            hostname,
            txt_token=token,
            cname_target=target,
            txt_resolver=_Txt({txt_name(hostname): [txt_value(token)]}),
            cname_resolver=_Cname({}),
        )
        is False
    )
