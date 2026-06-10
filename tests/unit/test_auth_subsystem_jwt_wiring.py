"""Regression tests for #1105 — JWT auth routes wired through AuthSubsystem.

`create_jwt_auth_routes` was implemented + tested but never invoked by
the auth subsystem after #536 extracted it from monolithic ``auth.py``.
This file pins the wiring contract:

- A standalone JWT path (no OAuth providers) still mounts the 6 routes.
- The JWTService + TokenStore are shared between social-auth and
  standalone JWT paths via ``_ensure_jwt_service`` — refresh tokens
  issued through either path validate against the same key material.
- Missing DATABASE_URL gates the mount (TokenStore is Postgres-only).
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dazzle.back.runtime.subsystems.auth import AuthSubsystem


def _make_ctx(*, database_url: str | None, oauth_providers: list[object] | None = None) -> object:
    """Build a SubsystemContext stand-in with the minimum surface
    the subsystem reads."""
    auth_config = SimpleNamespace(
        oauth_providers=oauth_providers,
        jwt=SimpleNamespace(access_token_minutes=15, refresh_token_days=7),
    )
    appspec = SimpleNamespace(security=None)
    return SimpleNamespace(
        enable_auth=True,
        auth_store=MagicMock(name="auth_store"),
        auth_config=auth_config,
        database_url=database_url,
        config=SimpleNamespace(personas=[]),
        app=MagicMock(name="app"),
        appspec=appspec,
    )


def test_jwt_routes_build_and_mount() -> None:
    """The real factory (not a mock) builds and mounts the JWT routes.

    The other wiring tests below mock ``create_jwt_auth_routes``, so they never
    exercise FastAPI's per-route field analysis. This one builds for real.
    """
    from fastapi import FastAPI

    from dazzle.back.runtime.auth.routes_jwt import create_jwt_auth_routes

    router = create_jwt_auth_routes(
        auth_store=MagicMock(name="auth_store"),
        jwt_service=MagicMock(name="jwt_service"),
        token_store=MagicMock(name="token_store"),
    )

    app = FastAPI()
    app.include_router(router)

    paths = {getattr(route, "path", None) for route in app.routes}
    assert {"/auth/token", "/auth/token/refresh", "/auth/token/revoke"} <= paths


def test_no_handler_param_uses_optional_request_annotation() -> None:
    """#1343 regression (version-independent guard).

    FastAPI only injects a parameter when its annotation is *exactly*
    ``starlette.requests.Request``. A union like ``Request | None`` /
    ``Optional[Request]`` defeats that special-casing, so FastAPI tries to build
    a Pydantic field for ``Request`` and raises ``Invalid args for response
    field!`` at route registration — which aborted the ``auth_routes`` subsystem
    on boot (latent since v0.67.123, surfaced by the v0.81.59 lifespan-hook fix).

    Whether that raises is FastAPI-version- and ``functools.partial``-dependent,
    so this pins the underlying invariant directly: any handler param that
    mentions ``Request`` must resolve to exactly ``Request``.
    """
    import inspect
    import typing

    from starlette.requests import Request as StarletteRequest

    from dazzle.back.runtime.auth import routes_jwt as m

    handlers = [
        obj
        for name, obj in vars(m).items()
        if name.startswith("_") and inspect.iscoroutinefunction(obj)
    ]
    assert handlers, "no handler coroutines found — test wiring broke"

    offenders = []
    for func in handlers:
        for pname, ann in typing.get_type_hints(func).items():
            if pname == "return" or ann is StarletteRequest:
                continue  # absent or the exact, injectable type — fine
            # The footgun: Request wrapped in a union/Optional. Identity check on
            # union members (not substring — `TokenRequest` etc. also contain it).
            if StarletteRequest in typing.get_args(ann):
                offenders.append(f"{func.__name__}({pname}: {ann})")

    assert not offenders, (
        "FastAPI Request params must be exactly `Request`, not a union/Optional "
        f"(defeats request injection → mount crash): {', '.join(offenders)}"
    )


def test_register_jwt_routes_mounts_when_database_url_set() -> None:
    """Standalone JWT path: no OAuth, DB URL present → routes mount."""
    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test", oauth_providers=None)

    with (
        patch("dazzle.back.runtime.auth.create_jwt_auth_routes") as factory,
        patch("dazzle.back.runtime.jwt_auth.JWTService") as jwt_service_cls,
        patch("dazzle.back.runtime.token_store.TokenStore") as token_store_cls,
    ):
        factory.return_value = MagicMock(name="jwt_router")
        jwt_service_cls.return_value = MagicMock(name="jwt_service")
        token_store_cls.return_value = MagicMock(name="token_store")

        sub._register_jwt_routes(ctx)  # type: ignore[arg-type]

    factory.assert_called_once()
    ctx.app.include_router.assert_called_once()  # type: ignore[attr-defined]
    assert sub._jwt_service is not None
    assert sub._token_store is not None


def test_register_jwt_routes_skipped_without_database_url() -> None:
    """No DATABASE_URL → TokenStore is Postgres-only, so the mount skips."""
    sub = AuthSubsystem()
    ctx = _make_ctx(database_url=None, oauth_providers=None)

    with patch("dazzle.back.runtime.auth.create_jwt_auth_routes") as factory:
        sub._register_jwt_routes(ctx)  # type: ignore[arg-type]

    factory.assert_not_called()
    ctx.app.include_router.assert_not_called()  # type: ignore[attr-defined]


def test_ensure_jwt_service_is_idempotent() -> None:
    """_ensure_jwt_service must be safe to call multiple times — the
    second call reuses the JWTService/TokenStore from the first."""
    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test")

    with (
        patch("dazzle.back.runtime.jwt_auth.JWTService") as jwt_service_cls,
        patch("dazzle.back.runtime.token_store.TokenStore") as token_store_cls,
    ):
        jwt_service_cls.return_value = MagicMock(name="jwt_service")
        token_store_cls.return_value = MagicMock(name="token_store")

        assert sub._ensure_jwt_service(ctx) is True  # type: ignore[arg-type]
        first_jwt = sub._jwt_service
        first_token = sub._token_store

        assert sub._ensure_jwt_service(ctx) is True  # type: ignore[arg-type]

    # Both calls returned True; the second did NOT re-instantiate.
    assert sub._jwt_service is first_jwt
    assert sub._token_store is first_token
    assert jwt_service_cls.call_count == 1
    assert token_store_cls.call_count == 1


def test_jwt_routes_mount_after_social_auth_reuses_service() -> None:
    """When social auth runs first and builds a JWTService, the JWT-route
    registration reuses it rather than constructing a second one (#1105)."""
    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test")

    pre_built_jwt = MagicMock(name="pre_built_jwt")
    pre_built_token = MagicMock(name="pre_built_token")
    sub._jwt_service = pre_built_jwt
    sub._token_store = pre_built_token

    with (
        patch("dazzle.back.runtime.auth.create_jwt_auth_routes") as factory,
        patch("dazzle.back.runtime.jwt_auth.JWTService") as jwt_service_cls,
    ):
        factory.return_value = MagicMock(name="jwt_router")
        sub._register_jwt_routes(ctx)  # type: ignore[arg-type]

    # New JWTService never built; existing one reused.
    jwt_service_cls.assert_not_called()
    factory.assert_called_once_with(ctx.auth_store, pre_built_jwt, pre_built_token)


def test_startup_invokes_register_jwt_routes() -> None:
    """startup() must call _register_jwt_routes after the social-auth init."""
    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test", oauth_providers=None)

    with (
        patch.object(sub, "_register_auth_routes") as register_auth,
        patch.object(sub, "_init_social_auth") as init_social,
        patch.object(sub, "_register_jwt_routes") as register_jwt,
    ):
        sub.startup(ctx)  # type: ignore[arg-type]

    register_auth.assert_called_once_with(ctx)
    init_social.assert_called_once_with(ctx)
    register_jwt.assert_called_once_with(ctx)


@pytest.mark.parametrize(
    "enable_auth, auth_store_set, expect_call",
    [
        (False, True, False),  # auth disabled
        (True, False, False),  # no auth_store
        (True, True, True),  # all conditions met
    ],
)
def test_startup_gates(enable_auth: bool, auth_store_set: bool, expect_call: bool) -> None:
    """JWT routes only get registered when auth is enabled AND auth_store exists."""
    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test")
    ctx.enable_auth = enable_auth  # type: ignore[attr-defined]
    if not auth_store_set:
        ctx.auth_store = None  # type: ignore[attr-defined]

    with patch.object(sub, "_register_jwt_routes") as register_jwt:
        sub.startup(ctx)  # type: ignore[arg-type]

    if expect_call:
        register_jwt.assert_called_once()
    else:
        register_jwt.assert_not_called()


def test_ensure_jwt_service_fails_loud_without_pyjwt() -> None:
    """#1362: a missing PyJWT must mean routes don't mount at boot (with a
    loud warning), never a 500 at request time on a public endpoint."""
    import builtins

    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test")

    real_import = builtins.__import__

    def _no_jwt(name, *args, **kwargs):
        if name == "jwt":
            raise ImportError("No module named 'jwt'")
        return real_import(name, *args, **kwargs)

    with (
        patch("builtins.__import__", side_effect=_no_jwt),
        patch.dict(sys.modules) as mods,
    ):
        mods.pop("jwt", None)
        assert sub._ensure_jwt_service(ctx) is False  # type: ignore[arg-type]
    assert sub._jwt_service is None


def test_register_jwt_routes_skipped_without_pyjwt() -> None:
    """#1362 end-to-end: the route factory is never invoked without PyJWT."""
    import builtins

    sub = AuthSubsystem()
    ctx = _make_ctx(database_url="postgresql://localhost/test")

    real_import = builtins.__import__

    def _no_jwt(name, *args, **kwargs):
        if name == "jwt":
            raise ImportError("No module named 'jwt'")
        return real_import(name, *args, **kwargs)

    with (
        patch("dazzle.back.runtime.auth.create_jwt_auth_routes") as factory,
        patch("builtins.__import__", side_effect=_no_jwt),
        patch.dict(sys.modules) as mods,
    ):
        mods.pop("jwt", None)
        sub._register_jwt_routes(ctx)  # type: ignore[arg-type]

    factory.assert_not_called()
    ctx.app.include_router.assert_not_called()  # type: ignore[attr-defined]
