"""Phase 2: Sec-Fetch-Site + Origin admission gate (spec §4.2)."""

import asyncio
from typing import Any

import pytest

from dazzle.http.runtime.csrf import CSRFConfig, CSRFMiddleware, origin_disposition


def _h(**kw: str) -> list[tuple[bytes, bytes]]:
    """Build raw ASGI headers from kwargs (underscores -> dashes)."""
    return [(k.replace("_", "-").encode("latin-1"), v.encode("latin-1")) for k, v in kw.items()]


CFG = CSRFConfig(enabled=True)
CFG_TRUSTED = CSRFConfig(enabled=True, trusted_origins=["https://embed.partner.com"])
APP = "app.example.com"


@pytest.mark.parametrize(
    ("headers", "host", "config", "expected"),
    [
        # ── Sec-Fetch-Site alone ──
        pytest.param(
            {"sec_fetch_site": "same-origin"}, APP, CFG, True, id="sfs-same-origin-admits"
        ),
        pytest.param({"sec_fetch_site": "none"}, APP, CFG, True, id="sfs-none-admits"),
        pytest.param(
            {"sec_fetch_site": "cross-site"}, APP, CFG, False, id="sfs-cross-site-rejects"
        ),
        pytest.param(
            {"sec_fetch_site": "same-site"}, APP, CFG, False, id="sfs-same-site-rejects-by-default"
        ),
        # A garbage/unknown Sec-Fetch-Site value must fail CLOSED (reject), not open.
        pytest.param({"sec_fetch_site": "bogus"}, APP, CFG, False, id="sfs-unknown-fails-closed"),
        # ── Origin vs Host ──
        pytest.param(
            {"origin": "https://app.example.com", "host": APP},
            APP,
            CFG,
            True,
            id="origin-matches-host-admits",
        ),
        pytest.param(
            {"origin": "http://localhost:8000", "host": "localhost:8000"},
            "localhost:8000",
            CFG,
            True,
            id="origin-matches-host-with-port-admits",
        ),
        pytest.param(
            {"origin": "https://evil.com", "host": APP},
            APP,
            CFG,
            False,
            id="origin-differs-from-host-rejects",
        ),
        pytest.param(
            {"origin": "https://tenant-b.example.com", "host": "tenant-a.example.com"},
            "tenant-a.example.com",
            CFG,
            False,
            id="cross-tenant-subdomain-rejects",
        ),
        pytest.param({"origin": "null", "host": APP}, APP, CFG, False, id="origin-null-rejects"),
        # Browsers omit default ports; an explicit :443 is a distinct authority
        # and rejected — documents the no-normalization behaviour.
        pytest.param(
            {"origin": "https://app.example.com:443", "host": APP},
            APP,
            CFG,
            False,
            id="explicit-default-port-does-not-match-bare-host",
        ),
        # ── trusted origins ──
        pytest.param(
            {"origin": "https://embed.partner.com", "host": APP},
            APP,
            CFG_TRUSTED,
            True,
            id="trusted-origin-admits-despite-host-mismatch",
        ),
        pytest.param(
            {"origin": "https://other.partner.com", "host": APP},
            APP,
            CFG_TRUSTED,
            False,
            id="untrusted-origin-still-rejects",
        ),
        pytest.param(
            {"sec_fetch_site": "same-site", "origin": "https://embed.partner.com"},
            APP,
            CFG_TRUSTED,
            True,
            id="same-site-in-trusted-admits",
        ),
        # ── precedence: the unforgeable Sec-Fetch-Site wins over Origin ──
        pytest.param(
            {"sec_fetch_site": "same-origin", "origin": "https://evil.com", "host": APP},
            APP,
            CFG,
            True,
            id="sfs-same-origin-wins-over-mismatched-origin",
        ),
        pytest.param(
            {"sec_fetch_site": "cross-site", "origin": "https://app.example.com", "host": APP},
            APP,
            CFG,
            False,
            id="sfs-cross-site-wins-over-matching-origin",
        ),
        # ── no signal: defer to the token check ──
        pytest.param({"host": APP}, APP, CFG, None, id="no-origin-no-fetch-metadata-is-none"),
    ],
)
def test_origin_disposition(
    headers: dict[str, str], host: str, config: CSRFConfig, expected: bool | None
) -> None:
    assert origin_disposition(_h(**headers), host, config) is expected


async def _drive(config: CSRFConfig, *, method: str, path: str, headers_extra: Any) -> int:
    headers = list(headers_extra)
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    status = {"code": 0}

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    await CSRFMiddleware(inner, config)(scope, receive, send)
    return status["code"]


@pytest.mark.parametrize(
    ("path", "headers", "expected_status"),
    [
        pytest.param(
            "/academicyears",
            {"sec_fetch_site": "same-origin", "host": APP},
            200,
            id="same-origin-post-admits-without-token",
        ),
        pytest.param(
            "/academicyears",
            {
                "sec_fetch_site": "cross-site",
                "cookie": "dazzle_csrf=abc",
                "x_csrf_token": "abc",
                "host": APP,
            },
            403,
            id="cross-site-post-rejected-even-with-valid-token",
        ),
        pytest.param(
            "/academicyears",
            {"cookie": "dazzle_csrf=abc", "x_csrf_token": "abc", "host": APP},
            200,
            id="no-origin-signal-falls-back-to-token-pass",
        ),
        pytest.param(
            "/academicyears",
            {"host": APP},
            403,
            id="no-origin-signal-falls-back-to-token-reject",
        ),
        pytest.param(
            "/webhooks/stripe",
            {"sec_fetch_site": "cross-site", "host": APP},
            200,
            id="exempt-path-still-exempt-regardless-of-origin",
        ),
        pytest.param(
            "/api/x",
            {"authorization": "Bearer tok", "sec_fetch_site": "cross-site", "host": APP},
            200,
            id="bearer-still-exempt-regardless-of-origin",
        ),
    ],
)
def test_middleware_origin_gate(path: str, headers: dict[str, str], expected_status: int) -> None:
    status = asyncio.run(
        _drive(CSRFConfig(enabled=True), method="POST", path=path, headers_extra=_h(**headers))
    )
    assert status == expected_status
