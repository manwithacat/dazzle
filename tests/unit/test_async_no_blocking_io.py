"""Handlers declared `async def` must not perform blocking I/O on the event loop.

Why this exists
---------------
Two call sites declared `async def` but did synchronous network I/O inline:

- ``http/channels/ses_webhooks.py::_confirm_subscription`` —
  ``urllib.request.urlopen(req, timeout=10)`` directly on the loop.
- ``http/runtime/social_auth.py::verify_google_token`` —
  ``verify_oauth2_token`` performs a synchronous round-trip to Google's
  tokeninfo endpoint.

A blocked event loop stalls every concurrent request in the worker, including
health checks — which can trip the orchestrator's liveness probe and cascade into
a restart (#1714). ``channels/providers/email.py:179`` already had this right via
``run_in_executor``; these two did not.

What this catches
-----------------
A regression to inline blocking calls. The assertion is behavioural rather than
structural: the worker thread is parked inside a fake ``urlopen``, and the test
checks the event loop can still run other work. A structural check for
``run_in_executor`` would pass even if the call were moved back inline.

How to satisfy it
-----------------
Dispatch the blocking call to an executor, e.g.
``await asyncio.get_running_loop().run_in_executor(None, _blocking_call)``.

What this does NOT catch
------------------------
Blocking *file* I/O in ``http/runtime/file_storage.py:250,265``. That one is
local-disk and tolerable; it is tracked separately rather than asserted here.
"""

from __future__ import annotations

import asyncio
import threading
import urllib.request
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


# The parked thread waits far longer than the probe is allowed, so a blocked
# event loop shows up as a `wait_for` TimeoutError rather than a slow pass.
_PARK_SECONDS = 30
_DEADLINE = 2.0


class _FakeResponse:
    status = 200

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _parked_urlopen(entered: threading.Event, released: threading.Event):
    """A `urlopen` stand-in that parks the calling thread until released."""

    def _urlopen(req: Any, timeout: Any = None) -> _FakeResponse:
        entered.set()
        released.wait(timeout=_PARK_SECONDS)
        return _FakeResponse()

    return _urlopen


async def test_sns_confirm_subscription_does_not_block_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop must stay responsive while SNS confirmation is in flight.

    The discriminator is the deadline, not the assertions. The fake ``urlopen``
    parks its thread for :data:`_PARK_SECONDS`, far longer than the
    :data:`_DEADLINE` the probe is given:

    - with ``run_in_executor`` the loop is free, the probe runs within the
      deadline and releases the parked thread, so the test finishes in ms;
    - without it the loop is parked inside ``urlopen`` for the full
      ``_PARK_SECONDS``, so the probe's deadline has already expired when the
      loop unblocks and ``wait_for`` raises ``TimeoutError``.

    An earlier draft of this test polled for ``entered`` *before* probing, which
    let a blocked loop "pass" — the poll itself absorbed the stall.
    """
    from dazzle.http.channels.ses_webhooks import _confirm_subscription

    entered = threading.Event()
    released = threading.Event()
    monkeypatch.setattr(urllib.request, "urlopen", _parked_urlopen(entered, released))

    try:
        task = asyncio.create_task(
            _confirm_subscription(
                {"SubscribeURL": "https://sns.example/confirm", "TopicArn": "arn:topic"}
            )
        )

        async def _probe() -> bool:
            # Yield until the worker thread is parked in the blocking call.
            # Only possible while the loop is free.
            for _ in range(int(_DEADLINE * 100)):
                if entered.is_set():
                    released.set()
                    return True
                await asyncio.sleep(0.01)
            return False

        assert await asyncio.wait_for(_probe(), timeout=_DEADLINE), (
            "event loop was blocked by the SNS confirmation round-trip"
        )
        assert await asyncio.wait_for(task, timeout=_PARK_SECONDS) is True
    finally:
        released.set()


async def test_verify_google_token_does_not_block_the_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same shape for the Google tokeninfo round-trip."""
    pytest.importorskip("google.oauth2", reason="requires the optional social auth extra")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    from dazzle.http.runtime.social_auth import verify_google_token

    entered = threading.Event()
    released = threading.Event()

    def _parked_verify(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        entered.set()
        released.wait(timeout=_PARK_SECONDS)
        return {
            "sub": "google-sub-1",
            "email": "person@example.com",
            "email_verified": True,
            "name": "Person",
        }

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _parked_verify)
    monkeypatch.setattr(google_requests, "Request", lambda *a, **k: object())

    try:
        task = asyncio.create_task(verify_google_token("id-token", "client-id"))

        async def _probe() -> bool:
            for _ in range(int(_DEADLINE * 100)):
                if entered.is_set():
                    released.set()
                    return True
                await asyncio.sleep(0.01)
            return False

        assert await asyncio.wait_for(_probe(), timeout=_DEADLINE), (
            "event loop was blocked by the Google tokeninfo round-trip"
        )
        profile = await asyncio.wait_for(task, timeout=_PARK_SECONDS)
        assert profile.provider_user_id == "google-sub-1"
    finally:
        released.set()


async def test_google_verification_errors_still_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dispatching to an executor must not swallow SocialAuthError."""
    pytest.importorskip("google.oauth2", reason="requires the optional social auth extra")
    from google.oauth2 import id_token as google_id_token

    from dazzle.http.runtime.social_auth import SocialAuthError, verify_google_token

    def _raise(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ValueError("bad token")

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _raise)

    with pytest.raises(SocialAuthError) as excinfo:
        await verify_google_token("id-token", "client-id")
    assert excinfo.value.code == "invalid_token"
