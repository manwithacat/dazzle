"""#1141: rbac verify-scope POSTs JSON to /auth/login.

Pre-fix the verifier sent form-encoded data which the framework's
own JSON-only /auth/login rejects with 422. Surfaced as a generic
"Admin login failed" on every persona row. Two correctness gates:

1. The login request body shape MUST be `json={...}`, not
   `data={...}` — that's the framework auth contract.
2. The error message MUST include the response body excerpt — bare
   "Login failed (422)" was the diagnostic gap that made this issue
   take hours to triage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.cli.rbac import _login


@pytest.mark.asyncio
async def test_login_sends_json_not_form_data() -> None:
    """The kwarg passed to async_retrying_request must be `json=`,
    matching the framework's /auth/login contract."""
    client = AsyncMock()
    resp = MagicMock(status_code=200, cookies={"session": "abc"}, text="")

    with patch(
        "dazzle.core.http_client.async_retrying_request", AsyncMock(return_value=resp)
    ) as req:
        cookies = await _login(client, "http://x", "e@x", "pw")

    assert cookies == {"session": "abc"}
    # async_retrying_request was called with json= kwarg, not data=
    call_kwargs = req.call_args.kwargs
    assert call_kwargs.get("json") == {"email": "e@x", "password": "pw"}
    assert "data" not in call_kwargs


@pytest.mark.asyncio
async def test_login_error_includes_body_excerpt() -> None:
    """A 422 from a project that requires extra fields used to
    surface as bare 'Login failed (422): <email>'. Operator now sees
    the body so the cause is actionable."""
    client = AsyncMock()
    resp = MagicMock(status_code=422)
    resp.text = '{"detail":[{"loc":["body","captcha"],"msg":"required"}]}'

    with patch("dazzle.core.http_client.async_retrying_request", AsyncMock(return_value=resp)):
        with pytest.raises(RuntimeError) as exc_info:
            await _login(client, "http://x", "e@x", "pw")

    msg = str(exc_info.value)
    assert "422" in msg
    assert "e@x" in msg
    assert "captcha" in msg, f"body excerpt missing from error: {msg!r}"


@pytest.mark.asyncio
async def test_login_truncates_long_body_excerpts() -> None:
    """Body excerpts cap at ~200 chars — a stack-trace-shaped 500
    body shouldn't bury the operator's error log."""
    client = AsyncMock()
    resp = MagicMock(status_code=500)
    resp.text = "X" * 5000

    with patch("dazzle.core.http_client.async_retrying_request", AsyncMock(return_value=resp)):
        with pytest.raises(RuntimeError) as exc_info:
            await _login(client, "http://x", "e@x", "pw")

    msg = str(exc_info.value)
    # 200 chars + repr quoting overhead — well under the original 5000.
    assert len(msg) < 400
