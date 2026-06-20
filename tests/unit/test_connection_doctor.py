"""Connection-doctor diagnosis kernel tests (auth Plan 4b.v).

Pure: build a connection + the three env flags, assert the structured checks,
``ready``, and the runbook. No env/DB/network.
"""

from datetime import datetime

from dazzle.http.runtime.auth.connection_doctor import Check, diagnose_connection
from dazzle.http.runtime.auth.connections import ConnectionRecord


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "oidc",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {"issuer": "https://idp.example", "client_id": "cid"},
        "secrets": {"client_secret": "shh"},
        "group_mapping": {"eng": "engineer"},
        "status": "active",
        "created_at": datetime(2026, 6, 6),
        "updated_at": datetime(2026, 6, 6),
    }
    base.update(over)
    return ConnectionRecord(**base)


def _diag(conn, *, secret=True, sso=True, dns=True):
    return diagnose_connection(conn, secret_key_ok=secret, sso_extra_ok=sso, dns_extra_ok=dns)


def _by_name(diag, name) -> Check:
    return next(c for c in diag.checks if c.name == name)


# ---- the happy path ----


def test_fully_configured_is_ready() -> None:
    diag = _diag(_conn())
    assert diag.ready is True
    assert all(c.status == "ok" for c in diag.checks if c.level == "required")
    # No required remedies; runbook still carries the two un-introspectable reminders.
    assert any("redirect URI" in step for step in diag.runbook)
    assert any("/auth/enterprise/login?connection=conn-1" in step for step in diag.runbook)


def test_secret_value_never_appears_in_report() -> None:
    diag = _diag(_conn(secrets={"client_secret": "SUPER-SECRET"}))
    blob = repr(diag)
    assert "SUPER-SECRET" not in blob
    assert _by_name(diag, "client_secret").status == "ok"


# ---- required failures gate readiness ----


def test_missing_secret_key_fails() -> None:
    diag = _diag(_conn(), secret=False)
    assert diag.ready is False
    c = _by_name(diag, "secret_key")
    assert c.status == "fail" and "DAZZLE_CONNECTION_SECRET" in c.remedy


def test_missing_sso_extra_fails() -> None:
    diag = _diag(_conn(), sso=False)
    assert diag.ready is False
    assert _by_name(diag, "sso_extra").status == "fail"
    assert any("dazzle-dsl[sso]" in step for step in diag.runbook)


def test_missing_issuer_and_discovery_fails() -> None:
    diag = _diag(_conn(config={"client_id": "cid"}))
    assert diag.ready is False
    assert _by_name(diag, "issuer_or_discovery").status == "fail"


def test_discovery_url_satisfies_issuer_check() -> None:
    diag = _diag(_conn(config={"discovery_url": "https://idp/.well-known/x", "client_id": "c"}))
    assert _by_name(diag, "issuer_or_discovery").status == "ok"


def test_missing_client_id_fails() -> None:
    diag = _diag(_conn(config={"issuer": "https://idp.example"}))
    assert _by_name(diag, "client_id").status == "fail" and diag.ready is False


def test_missing_client_secret_fails() -> None:
    diag = _diag(_conn(secrets={}))
    assert _by_name(diag, "client_secret").status == "fail" and diag.ready is False


def test_no_verified_domain_fails() -> None:
    diag = _diag(_conn(verified_domains=[]))
    assert _by_name(diag, "verified_domain").status == "fail" and diag.ready is False
    assert any("verify-domain" in step for step in diag.runbook)


# ---- recommended warnings don't gate readiness ----


def test_empty_group_mapping_warns_but_still_ready() -> None:
    diag = _diag(_conn(group_mapping={}))
    assert _by_name(diag, "group_mapping").status == "warn"
    assert diag.ready is True  # recommended, not required


def test_missing_dns_extra_warns_but_still_ready() -> None:
    diag = _diag(_conn(), dns=False)
    assert _by_name(diag, "dns_extra").status == "warn"
    assert diag.ready is True


def test_claimed_unverified_domain_warns() -> None:
    diag = _diag(_conn(domains=["acme.test", "extra.test"], verified_domains=["acme.test"]))
    c = _by_name(diag, "claimed_unverified")
    assert c.status == "warn" and "extra.test" in c.detail


def test_no_unverified_warning_when_all_claimed_are_verified() -> None:
    diag = _diag(_conn(domains=["acme.test"], verified_domains=["acme.test"]))
    assert not any(c.name == "claimed_unverified" for c in diag.checks)


# ---- runbook ordering ----


def test_runbook_lists_required_remedies_before_recommended() -> None:
    # Missing client_id (required) + empty group_mapping (recommended).
    diag = _diag(_conn(config={"issuer": "https://idp.example"}, group_mapping={}))
    remedies = diag.runbook
    client_id_idx = next(
        i for i, s in enumerate(remedies) if "client_id" in s.lower() or "client id" in s.lower()
    )
    group_idx = next(i for i, s in enumerate(remedies) if "group-map" in s)
    assert client_id_idx < group_idx


# ---- non-oidc types ----


def test_non_oidc_type_returns_minimal_note() -> None:
    diag = _diag(_conn(type="scim"))
    assert diag.connection_type == "scim"
    assert _by_name(diag, "type").status == "warn"
    # Doesn't run the OIDC-specific checks.
    assert not any(c.name == "client_id" for c in diag.checks)
