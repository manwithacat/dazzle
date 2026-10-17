"""Two-factor sign-in against real PostgreSQL (DD-014, #1805, #1804).

Each test drives the public HTTP routes of a minimal app wired the way
``AuthSubsystem`` wires them (password/JSON/magic-link sign-in, the 2FA routes, the
TwoFactorConfig on ``app.state``) over a scratch database. Skipped without
TEST_DATABASE_URL / DATABASE_URL.

No ``from __future__ import annotations``: the module builds FastAPI apps (ADR-0014).
"""

import base64
import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dazzle.core.ir.security import TwoFactorConfig, TwoFactorMethod
from dazzle.http.runtime.auth import bind_rls, require_second_factor
from dazzle.http.runtime.auth.magic_link import create_magic_link
from dazzle.http.runtime.auth.magic_link_routes import create_magic_link_routes
from dazzle.http.runtime.auth.password_login_routes import create_password_login_routes
from dazzle.http.runtime.auth.routes import create_auth_routes
from dazzle.http.runtime.auth.sign_in import CHALLENGE_COOKIE
from dazzle.http.runtime.auth.store import AuthStore
from dazzle.http.runtime.auth.totp import generate_totp
from dazzle.http.runtime.auth.two_factor_routes import create_two_factor_routes

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PASSWORD = "pw-correct-horse"


@pytest.fixture
def scratch_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(os.urandom(32)).decode())
    admin_url = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_2fa_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
    try:
        yield f"{base}/{scratch}"
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


class _Mailer:
    """Captures two-factor email codes (the registered mailer seam)."""

    def __init__(self) -> None:
        self.codes: list[str] = []

    def send_magic_link(self, *, to_email: str, link_url: str) -> None:
        pass

    def send_one_time_code(self, *, to_email: str, code: str, ttl_minutes: int) -> None:
        self.codes.append(code)


def _app(store: AuthStore, cfg: TwoFactorConfig, mailer: Any = None) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.state.two_factor = cfg
    app.state.magic_link_mailer = mailer
    app.include_router(create_auth_routes(store))
    app.include_router(create_password_login_routes())
    app.include_router(create_magic_link_routes())
    app.include_router(create_two_factor_routes())

    @app.get("/filing")
    async def filing(request: Request) -> dict[str, str]:
        auth = require_second_factor(request, max_age=15 * 60)
        return {"mfa_method": str(auth.mfa_method)}

    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, follow_redirects=False)


def _store(url: str) -> AuthStore:
    store = AuthStore(database_url=url)
    store.ensure_initialized()
    return store


_TOTP_ON = TwoFactorConfig(enabled=True)


def _enrol_totp(client: TestClient, email: str) -> tuple[str, list[str]]:
    """Sign in (no factor yet), enrol an authenticator, sign out. Returns secret + codes."""
    resp = client.post("/auth/login", json={"email": email, "password": _PASSWORD})
    assert resp.status_code == 200 and "redirect_url" in resp.json()
    secret = client.post("/auth/2fa/setup/totp").json()["secret"]
    resp = client.post("/auth/2fa/verify/totp", json={"code": generate_totp(secret)})
    assert resp.status_code == 200
    codes = resp.json()["recovery_codes"]
    client.post("/auth/logout")
    client.cookies.clear()
    return secret, codes


def test_password_and_totp_sign_in_lands_in_the_org_and_sees_its_rows(scratch_url: str) -> None:
    """#1804 + DD-014 acceptance: enrol, sign out, sign in with password + TOTP; the
    session is pinned to the org (RLS shows its rows), records the factor, and the
    challenge token is never a session. A replayed code is refused."""
    store = _store(scratch_url)
    user = store.create_user(email="acct@practice.test", password=_PASSWORD)
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["accountant"])
    client = _client(_app(store, _TOTP_ON))
    secret, _codes = _enrol_totp(client, "acct@practice.test")

    resp = client.post(
        "/auth/login/password", data={"email": "acct@practice.test", "password": _PASSWORD}
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/2fa/challenge"
    assert "dazzle_session" not in resp.cookies
    token = resp.cookies[CHALLENGE_COOKIE]
    # The challenge token is not a session: presented as one, it authenticates nothing.
    assert store.validate_session(token).is_authenticated is False
    probe = _client(client.app)
    probe.cookies.set("dazzle_session", token)
    assert probe.get("/auth/me").status_code == 401

    # The enrolment code's time step was spent: the same code is refused (no replay).
    replay = client.post(
        "/auth/2fa/verify/submit?method=totp", data={"code": generate_totp(secret)}
    )
    assert replay.headers["location"].startswith("/2fa/challenge?method=totp&error=")
    resp = client.post(
        "/auth/2fa/verify/submit?method=totp",
        data={"code": generate_totp(secret, time.time() + 30)},
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/app"
    ctx = store.validate_session(resp.cookies["dazzle_session"])
    assert ctx.active_membership is not None and ctx.active_membership.tenant_id == "t-1"
    assert ctx.mfa_method == "totp" and ctx.mfa_verified_at is not None
    assert ctx.mfa_reference

    # RLS: the bound session sees its org's rows only.
    role = f"r_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        conn.execute("CREATE TABLE ledger (tenant_id text, label text)")
        conn.execute("INSERT INTO ledger VALUES ('t-1', 'mine'), ('t-2', 'theirs')")
        conn.execute("ALTER TABLE ledger ENABLE ROW LEVEL SECURITY")
        conn.execute(
            "CREATE POLICY fence ON ledger USING "
            "(tenant_id = current_setting('dazzle.tenant_id', true))"
        )
        conn.execute(f'CREATE ROLE "{role}" NOLOGIN')  # nosemgrep — uuid-derived
        conn.execute(f'GRANT SELECT ON ledger TO "{role}"')  # nosemgrep
    try:
        with psycopg.connect(scratch_url) as conn:
            conn.execute(f'SET ROLE "{role}"')  # nosemgrep
            assert bind_rls(conn, ctx) == "t-1"
            rows = conn.execute("SELECT label FROM ledger").fetchall()
            assert rows == [("mine",)]
    finally:
        with psycopg.connect(scratch_url, autocommit=True) as conn:
            conn.execute("DROP TABLE ledger")
            conn.execute(f'DROP ROLE "{role}"')  # nosemgrep


def test_recovery_code_signs_in_once_and_wrong_codes_kill_the_challenge(scratch_url: str) -> None:
    store = _store(scratch_url)
    store.create_user(email="r@practice.test", password=_PASSWORD)
    client = _client(_app(store, _TOTP_ON))
    _secret, codes = _enrol_totp(client, "r@practice.test")

    resp = client.post("/auth/login", json={"email": "r@practice.test", "password": _PASSWORD})
    assert resp.json()["status"] == "2fa_required"
    assert set(resp.json()["methods"]) == {"totp", "recovery"}
    token = resp.json()["challenge_token"]
    resp = client.post(
        "/auth/2fa/verify",
        json={"method": "recovery", "code": codes[0].lower(), "challenge_token": token},
    )
    assert resp.status_code == 200
    assert store.validate_session(resp.cookies["dazzle_session"]).mfa_method == "recovery"

    # A spent recovery code, then four more wrong codes: the challenge is dead.
    client.cookies.clear()
    token = client.post(
        "/auth/login", json={"email": "r@practice.test", "password": _PASSWORD}
    ).json()["challenge_token"]
    attempts = [{"method": "recovery", "code": codes[0]}] + [
        {"method": "totp", "code": "000000"}
    ] * 4
    for attempt in attempts:
        bad = client.post("/auth/2fa/verify", json={**attempt, "challenge_token": token})
        assert bad.status_code == 401
    resp = client.post(
        "/auth/2fa/verify",
        json={"method": "recovery", "code": codes[1], "challenge_token": token},
    )
    assert resp.status_code == 401 and resp.json()["detail"] == "No pending sign-in"


def test_magic_link_sign_in_is_challenged_for_a_user_with_two_factor(scratch_url: str) -> None:
    store = _store(scratch_url)
    user = store.create_user(email="m@practice.test", password=_PASSWORD)
    client = _client(_app(store, _TOTP_ON))
    _enrol_totp(client, "m@practice.test")

    resp = client.get(f"/auth/magic/{create_magic_link(store, user_id=str(user.id))}")
    assert resp.status_code == 303 and resp.headers["location"] == "/2fa/challenge"
    assert "dazzle_session" not in resp.cookies and CHALLENGE_COOKIE in resp.cookies


def test_enforced_role_without_a_factor_can_only_enrol(scratch_url: str) -> None:
    """enforce_for_roles: no session until a factor is enrolled; enrolling signs in."""
    cfg = TwoFactorConfig(enabled=True, enforce_for_roles=("accountant",))
    store = _store(scratch_url)
    user = store.create_user(email="e@practice.test", password=_PASSWORD)
    store.create_membership(tenant_id="t-9", identity_id=str(user.id), roles=["accountant"])
    client = _client(_app(store, cfg))

    resp = client.post(
        "/auth/login/password", data={"email": "e@practice.test", "password": _PASSWORD}
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/2fa/setup"
    assert "dazzle_session" not in resp.cookies
    assert client.get("/auth/2fa/status").status_code == 401
    assert client.get("/2fa/challenge").headers["location"] == "/login?error=2fa_expired"

    page = client.get("/2fa/setup")
    assert page.status_code == 200 and 'src="data:image/png;base64,' in page.text
    secret = store.get_totp_secret(user.id)
    assert secret is not None
    resp = client.post("/auth/2fa/setup/totp/submit", data={"code": generate_totp(secret)})
    assert resp.status_code == 200 and "dz-auth-recovery-pill" in resp.text
    ctx = store.validate_session(resp.cookies["dazzle_session"])
    assert ctx.active_membership is not None and ctx.active_membership.tenant_id == "t-9"
    assert ctx.mfa_method == "totp"


def test_step_up_records_the_factor_on_the_current_session(scratch_url: str) -> None:
    """A session that signed in before 2FA existed steps up; require_second_factor passes."""
    store = _store(scratch_url)
    store.create_user(email="s@practice.test", password=_PASSWORD)
    client = _client(_app(store, _TOTP_ON))
    secret, _codes = _enrol_totp(client, "s@practice.test")
    # Old-style session: minted without a factor (a session from before the upgrade).
    user = store.get_user_by_email("s@practice.test")
    assert user is not None
    client.cookies.set("dazzle_session", store.create_session(user).id)

    refused = client.get("/filing")
    assert refused.status_code == 403
    assert refused.json()["detail"] == {
        "error": "second_factor_required",
        "step_up_url": "/2fa/step-up?next=/filing",
    }
    resp = client.post(
        "/auth/2fa/step-up",
        json={"method": "totp", "code": generate_totp(secret, time.time() + 30)},
    )
    assert resp.status_code == 200 and resp.json()["mfa_method"] == "totp"
    assert client.get("/filing").json() == {"mfa_method": "totp"}


def test_email_code_is_delivered_by_the_mailer_and_signs_in(scratch_url: str) -> None:
    cfg = TwoFactorConfig(enabled=True, methods=(TwoFactorMethod.TOTP, TwoFactorMethod.EMAIL_OTP))
    store = _store(scratch_url)
    store.create_user(email="o@practice.test", password=_PASSWORD)
    mailer = _Mailer()
    client = _client(_app(store, cfg, mailer))
    client.post("/auth/login", json={"email": "o@practice.test", "password": _PASSWORD})
    assert client.post("/auth/2fa/setup/email-otp").status_code == 200
    resp = client.post("/auth/2fa/verify/email-otp", json={"code": mailer.codes[-1]})
    assert resp.status_code == 200 and resp.json()["recovery_codes"]
    client.post("/auth/logout")
    client.cookies.clear()

    token = client.post(
        "/auth/login", json={"email": "o@practice.test", "password": _PASSWORD}
    ).json()["challenge_token"]
    sent = client.post(
        "/auth/2fa/challenge", json={"method": "email_otp", "code": "", "challenge_token": token}
    )
    assert sent.status_code == 200 and mailer.codes[-1] not in sent.text
    resp = client.post(
        "/auth/2fa/verify",
        json={"method": "email_otp", "code": mailer.codes[-1], "challenge_token": token},
    )
    assert resp.status_code == 200
    assert store.validate_session(resp.cookies["dazzle_session"]).mfa_method == "email_otp"
