"""#1141: rbac verify-scope POSTs JSON to /auth/login.

Pre-fix the verifier sent form-encoded data which the framework's
own JSON-only /auth/login rejects with 422. Surfaced as a generic
"Admin login failed" on every persona row. Two correctness gates:

1. The login request on the wire is ``application/json`` with the
   credentials as a JSON object — the framework auth contract.
2. The error message MUST include the response body excerpt — bare
   "Login failed (422)" was the diagnostic gap that made this issue
   take hours to triage — capped so a stack-trace body stays readable.

Driven through a real ``httpx.AsyncClient`` on a ``MockTransport``, so the
assertions are on the request the server would actually receive.
"""

import json

import httpx
import pytest

from dazzle.cli.rbac import _login


def _client(status: int, body: str = "", cookies: str = "") -> tuple[httpx.AsyncClient, list]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        headers = {"set-cookie": cookies} if cookies else {}
        return httpx.Response(status, text=body, headers=headers)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


@pytest.mark.asyncio
async def test_login_posts_json_credentials_and_returns_session_cookies() -> None:
    client, seen = _client(200, cookies="session=abc; Path=/")

    cookies = await _login(client, "http://app.test", "e@x", "pw")

    assert cookies == {"session": "abc"}
    [request] = seen
    assert (request.method, str(request.url)) == ("POST", "http://app.test/auth/login")
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {"email": "e@x", "password": "pw"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_excerpt"),
    [
        pytest.param(
            '{"detail":[{"loc":["body","captcha"],"msg":"required"}]}',
            "captcha",
            id="excerpt-names-the-missing-field",
        ),
        pytest.param("X" * 5000, "X" * 200, id="excerpt-capped-at-200-chars"),
    ],
)
async def test_login_failure_message_carries_status_email_and_body_excerpt(
    body: str, expected_excerpt: str
) -> None:
    client, _ = _client(422, body=body)

    with pytest.raises(RuntimeError) as exc_info:
        await _login(client, "http://app.test", "e@x", "pw")

    message = str(exc_info.value)
    assert message.startswith("Login failed (422): e@x")
    assert expected_excerpt in message
    assert len(message) < 400
