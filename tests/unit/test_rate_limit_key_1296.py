"""#1296 — rate-limit key derivation: exempt the internal loopback self-fetch
and honor X-Forwarded-For behind trusted proxies.

The SSR page handler fetches entity data over an internal loopback HTTP call
(Heroku: `http://127.0.0.1:{PORT}`). The old key_func (`get_remote_address`)
bucketed every such self-fetch under `127.0.0.1` and ignored XFF — saturating
one bucket → loopback 429 → entity detail 404 / list empty.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.rate_limit import (
    _is_loopback,
    _resolve_trusted_proxies,
    make_rate_limit_key,
)


def _req(host: str | None, xff: str | None = None) -> SimpleNamespace:
    headers = {"X-Forwarded-For": xff} if xff is not None else {}
    client = SimpleNamespace(host=host) if host is not None else None
    return SimpleNamespace(client=client, headers=SimpleNamespace(get=headers.get))


# ── _is_loopback ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.5.6.7", True),  # whole 127.0.0.0/8
        ("::1", True),
        ("10.0.0.4", False),
        ("203.0.113.9", False),
        ("", False),
        ("not-an-ip", False),
    ],
)
def test_is_loopback(host: str, expected: bool) -> None:
    assert _is_loopback(host) is expected


# ── internal loopback self-fetch → unique (effectively exempt) key ───────────


def test_loopback_no_xff_gets_unique_key() -> None:
    key_func = make_rate_limit_key(trusted_proxies=0)
    k1 = key_func(_req("127.0.0.1"))
    k2 = key_func(_req("127.0.0.1"))
    assert k1.startswith("internal-loopback:")
    assert k2.startswith("internal-loopback:")
    assert k1 != k2  # unique per request → never accumulates toward a limit


def test_loopback_with_xff_is_NOT_exempt() -> None:
    # A real external request behind a same-host proxy arrives from loopback
    # but WITH an XFF — it must be keyed by client, not exempted.
    key_func = make_rate_limit_key(trusted_proxies=1)
    key = key_func(_req("127.0.0.1", xff="203.0.113.9"))
    assert key == "203.0.113.9"
    assert not key.startswith("internal-loopback:")


# ── trusted-proxy XFF derivation (fix 3) ─────────────────────────────────────


def test_default_zero_trusted_proxies_uses_client_host_ignoring_xff() -> None:
    key_func = make_rate_limit_key(trusted_proxies=0)
    # Spoofing-safe default: XFF ignored when no trusted proxies configured.
    assert key_func(_req("203.0.113.1", xff="1.2.3.4")) == "203.0.113.1"


def test_one_trusted_proxy_takes_rightmost_xff() -> None:
    key_func = make_rate_limit_key(trusted_proxies=1)
    # Heroku/Cloudflare single proxy: real client is the entry the trusted
    # proxy added (rightmost). Leftmost is client-spoofable and ignored.
    assert key_func(_req("10.0.0.1", xff="spoofed, 198.51.100.7")) == "198.51.100.7"


def test_two_trusted_proxies_takes_second_from_right() -> None:
    key_func = make_rate_limit_key(trusted_proxies=2)
    assert key_func(_req("10.0.0.1", xff="client, 198.51.100.7, 10.0.0.2")) == "198.51.100.7"


def test_single_entry_xff_with_one_trusted_proxy() -> None:
    key_func = make_rate_limit_key(trusted_proxies=1)
    assert key_func(_req("10.0.0.1", xff="198.51.100.7")) == "198.51.100.7"


def test_insufficient_xff_entries_falls_back_to_client_host() -> None:
    key_func = make_rate_limit_key(trusted_proxies=3)
    # Only 2 entries but 3 trusted hops claimed → don't trust; use client.host.
    assert key_func(_req("10.0.0.1", xff="a, b")) == "10.0.0.1"


def test_non_loopback_no_xff_uses_client_host() -> None:
    key_func = make_rate_limit_key(trusted_proxies=1)
    assert key_func(_req("198.51.100.7")) == "198.51.100.7"


def test_no_client_returns_anonymous() -> None:
    key_func = make_rate_limit_key(trusted_proxies=0)
    assert key_func(_req(None)) == "anonymous"


# ── _resolve_trusted_proxies (env) ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("env_val", "expected"),
    [
        (None, 0),
        ("", 0),
        ("0", 0),
        ("1", 1),
        ("3", 3),
        ("garbage", 0),
        ("-2", 0),
    ],
)
def test_resolve_trusted_proxies(monkeypatch, env_val: str | None, expected: int) -> None:
    if env_val is None:
        monkeypatch.delenv("DAZZLE_RATE_LIMIT_TRUSTED_PROXIES", raising=False)
    else:
        monkeypatch.setenv("DAZZLE_RATE_LIMIT_TRUSTED_PROXIES", env_val)
    assert _resolve_trusted_proxies() == expected
