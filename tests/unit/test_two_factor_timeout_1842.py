"""#1842 (WCAG 2.2.1 Timing Adjustable): the two-factor sign-in challenge warns before it
times out, "More time" extends it up to a hard cap, and a timed-out challenge returns to
sign-in with the email filled in.

The routes run over an in-memory store whose extension rule is the real
``TwoFactorChallenge.extended_expiry``; the SQL is exercised against Postgres in
tests/integration/test_two_factor_pg.py. The client script's behaviour is driven in
Chromium in tests/unit/test_a11y_client_status_1842.py.

No ``from __future__ import annotations``: the module builds FastAPI apps (ADR-0014).
"""

import re
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.ir.security import TwoFactorConfig, TwoFactorMethod
from dazzle.http.runtime.auth.auth_views import build_login_password_view
from dazzle.http.runtime.auth.models import AuthContext, UserRecord
from dazzle.http.runtime.auth.sign_in import CHALLENGE_COOKIE
from dazzle.http.runtime.auth.store_two_factor import (
    CHALLENGE_MAX_LIFETIME,
    CHALLENGE_TTL,
    PURPOSE_VERIFY,
    TwoFactorChallenge,
)
from dazzle.http.runtime.auth.two_factor_routes import EXTEND_PATH, create_two_factor_routes
from dazzle.http.runtime.csrf import CSRFConfig, CSRFMiddleware
from dazzle.render.fragment.renderer import FragmentRenderer

_EMAIL = "a+b@practice.test"


@dataclass
class _Row:
    challenge: TwoFactorChallenge
    consumed: bool = False


class _Store:
    """The challenge half of ``AuthStore`` the timeout routes touch, in memory."""

    def __init__(self, user: UserRecord) -> None:
        self.user = user
        self.rows: dict[str, _Row] = {}

    def open(self, *, age: timedelta, remaining: timedelta) -> str:
        now = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        self.rows[token] = _Row(
            TwoFactorChallenge(
                token=token,
                user_id=str(self.user.id),
                purpose=PURPOSE_VERIFY,
                primary_method="password",
                membership_id=None,
                redirect_to="/app",
                attempts=0,
                created_at=now - age,
                expires_at=now + remaining,
            )
        )
        return token

    def get_2fa_challenge(self, token: str) -> TwoFactorChallenge | None:
        row = self.rows.get(token)
        live = row and not row.consumed and row.challenge.expires_at > datetime.now(UTC)
        return row.challenge if live and row else None

    def extend_2fa_challenge(self, token: str) -> datetime | None:
        ch = self.get_2fa_challenge(token)
        new = ch.extended_expiry(datetime.now(UTC)) if ch else None
        if ch is None or new is None:
            return None
        self.rows[token].challenge = replace(ch, expires_at=new)
        return new

    def expired_2fa_challenge_user_id(self, token: str) -> str | None:
        row = self.rows.get(token)
        timed_out = row and not row.consumed and row.challenge.expires_at <= datetime.now(UTC)
        return row.challenge.user_id if timed_out and row else None

    def get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        return self.user if user_id == self.user.id else None

    def validate_session(self, session_id: str) -> AuthContext:
        return AuthContext()

    def fail_2fa_challenge(self, token: str) -> None:
        pass

    def get_totp_secret(self, user_id: UUID) -> str | None:
        return None


def _client(*, email_otp: bool = False, csrf: bool = False) -> tuple[TestClient, _Store]:
    user = UserRecord(
        id=uuid4(), email=_EMAIL, password_hash="x", totp_enabled=True, email_otp_enabled=email_otp
    )
    store = _Store(user)
    app = FastAPI()
    app.state.auth_store = store
    app.state.two_factor = TwoFactorConfig(
        enabled=True, methods=(TwoFactorMethod.TOTP, TwoFactorMethod.EMAIL_OTP)
    )
    app.include_router(create_two_factor_routes())
    asgi = CSRFMiddleware(app, CSRFConfig(enabled=True)) if csrf else app
    return TestClient(asgi, follow_redirects=False), store


_JSON = {"accept": "application/json"}


@pytest.mark.parametrize(
    ("age", "remaining", "headers", "status", "expires_in", "extendable", "location"),
    [
        pytest.param(9, 1, _JSON, 200, CHALLENGE_TTL, True, None, id="adds-a-full-ttl"),
        pytest.param(25, 1, _JSON, 200, timedelta(minutes=5), False, None, id="clipped-to-cap"),
        pytest.param(29, 1, _JSON, 409, None, None, None, id="cap-reached"),
        pytest.param(
            9, 1, {}, 303, CHALLENGE_TTL, None, "/2fa/challenge?method=totp&extended=1", id="form"
        ),
        pytest.param(29, 1, {}, 303, None, None, "/2fa/challenge?method=totp", id="form-at-cap"),
    ],
)
def test_more_time_extends_the_challenge_up_to_the_cap(
    age: int,
    remaining: int,
    headers: dict[str, str],
    status: int,
    expires_in: timedelta | None,
    extendable: bool | None,
    location: str | None,
) -> None:
    client, store = _client()
    token = store.open(age=timedelta(minutes=age), remaining=timedelta(minutes=remaining))
    before = store.rows[token].challenge.expires_at
    client.cookies.set(CHALLENGE_COOKIE, token)

    resp = client.post(f"{EXTEND_PATH}?method=totp", headers=headers)

    assert resp.status_code == status
    after = store.rows[token].challenge
    assert after.expires_at <= after.created_at + CHALLENGE_MAX_LIFETIME
    if expires_in is None:
        assert after.expires_at == before
    else:
        gained = after.expires_at - datetime.now(UTC)
        assert abs(gained - expires_in) < timedelta(seconds=5)
    if status == 200:
        body = resp.json()
        assert abs(body["expires_in"] - expires_in.total_seconds()) < 5  # type: ignore[union-attr]
        assert body["extendable"] is extendable
    if location is not None:
        assert resp.headers["location"] == location


@pytest.mark.parametrize(
    ("method", "path", "cookie", "location"),
    [
        pytest.param("GET", "/2fa/challenge", "expired", "email", id="page"),
        pytest.param("POST", "/auth/2fa/verify/submit?method=totp", "expired", "email", id="code"),
        pytest.param("POST", "/auth/2fa/email-otp-send/submit", "expired", "email", id="send"),
        pytest.param("POST", f"{EXTEND_PATH}?method=totp", "expired", "email", id="more-time"),
        pytest.param("GET", "/2fa/challenge", "unknown", "plain", id="unknown-token"),
        pytest.param("GET", "/2fa/challenge", "", "plain", id="no-cookie"),
    ],
)
def test_a_timed_out_challenge_returns_to_sign_in_with_the_email(
    method: str, path: str, cookie: str, location: str
) -> None:
    client, store = _client()
    if cookie == "expired":
        client.cookies.set(
            CHALLENGE_COOKIE, store.open(age=timedelta(minutes=11), remaining=-timedelta(minutes=1))
        )
    elif cookie == "unknown":
        client.cookies.set(CHALLENGE_COOKIE, secrets.token_urlsafe(32))

    resp = client.request(method, path, data={"code": "123456"} if method == "POST" else None)

    assert resp.status_code == 303
    expected = "/login?error=2fa_expired"
    if location == "email":
        expected += "&email=a%2Bb@practice.test"
    assert resp.headers["location"] == expected


@pytest.mark.parametrize(
    ("headers", "admitted"),
    [
        pytest.param({}, False, id="no-origin-no-token"),
        pytest.param({"origin": "https://evil.example"}, False, id="cross-site"),
        pytest.param({"origin": "http://testserver"}, True, id="same-origin"),
        pytest.param({"x-csrf-token": "tok"}, True, id="double-submit-token"),
    ],
)
def test_more_time_is_csrf_protected(headers: dict[str, str], admitted: bool) -> None:
    client, store = _client(csrf=True)
    client.cookies.set(
        CHALLENGE_COOKIE, store.open(age=timedelta(minutes=9), remaining=timedelta(minutes=1))
    )
    client.cookies.set("dazzle_csrf", "tok")

    resp = client.post(f"{EXTEND_PATH}?method=totp", headers={**_JSON, **headers})

    assert (resp.status_code != 403) is admitted
    assert (resp.status_code == 200) is admitted


@pytest.mark.parametrize(
    ("age", "mode", "present", "absent"),
    [
        pytest.param(
            0,
            "totp",
            (
                f'action="{EXTEND_PATH}?method=totp" data-dz-2fa-extend',
                ">More time</button>",
                "Choose More time",
            ),
            ("Email me a new code",),
            id="totp",
        ),
        pytest.param(
            29,
            "totp",
            ("can&#x27;t be extended again",),
            ("data-dz-2fa-extend", ">More time</button>"),
            id="at-cap",
        ),
        pytest.param(
            0,
            "email_otp",
            ("data-dz-2fa-extend", ">Email me a new code</button>", "Email codes last 5 minutes"),
            (),
            id="email-code",
        ),
    ],
)
def test_the_code_page_carries_the_timeout_warning(
    age: int, mode: str, present: tuple[str, ...], absent: tuple[str, ...]
) -> None:
    client, store = _client(email_otp=True)
    client.cookies.set(
        CHALLENGE_COOKIE, store.open(age=timedelta(minutes=age), remaining=timedelta(minutes=1))
    )

    html = client.get(f"/2fa/challenge?method={mode}&sent=1").text

    expires_in = re.search(r'data-dz-2fa-timeout data-expires-in="(\d+)"', html)
    assert expires_in is not None and 55 <= int(expires_in.group(1)) <= 60
    assert 'data-warn-seconds="60"' in html
    # An empty alert region from load (announced when filled); actions start hidden.
    assert re.search(r'<p [^>]*role="alert"[^>]*data-dz-2fa-timeout-message[^>]*></p>', html)
    assert "data-dz-2fa-timeout-actions hidden" in html
    assert '<script defer src="/static/js/dz-2fa-timeout.js"></script>' in html
    for frag in present:
        assert frag in html
    for frag in absent:
        assert frag not in html


def test_the_sign_in_page_prefills_the_email() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme", email=_EMAIL)
    assert f'value="{_EMAIL}"' in FragmentRenderer().render(page)
