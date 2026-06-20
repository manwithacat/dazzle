"""#1140: validator must short-circuit on the second call so the same
app booting twice through `validate_routes` doesn't double-emit every
warning, and conflict descriptions carry endpoint provenance so the
operator can trace each duplicate without monkey-patching APIRouter."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI

from dazzle.http.runtime.route_validator import validate_routes


def _app_with_one_conflict() -> FastAPI:
    app = FastAPI()

    @app.get("/dup")
    async def a() -> None: ...

    @app.get("/dup")
    async def b() -> None: ...

    return app


def test_second_validate_call_short_circuits(caplog: pytest.LogCaptureFixture) -> None:
    """`server._setup_routes` and `app_factory.assemble_post_build_routes`
    both call validate_routes on the same app — pre-fix this produced
    duplicate WARNING lines for every conflict."""
    app = _app_with_one_conflict()

    with caplog.at_level(logging.WARNING, logger="dazzle.routes"):
        first = validate_routes(app)
        second = validate_routes(app)

    assert first == second
    warning_lines = [r for r in caplog.records if "Route conflict" in r.message]
    assert len(warning_lines) == 1, (
        f"expected exactly 1 conflict warning across both calls, got {len(warning_lines)}"
    )


def test_short_circuit_returns_cached_conflicts() -> None:
    """Second call returns the same list as the first — not an empty
    placeholder. Tests that the cache is the conflict list itself."""
    app = _app_with_one_conflict()
    first = validate_routes(app)
    second = validate_routes(app)
    assert second == first
    assert len(second) == 1


def test_conflict_descriptions_carry_endpoint_provenance() -> None:
    """Each conflict line names where the duplicate handlers came from
    (`module.qualname`). Pre-fix it just listed the route names, which
    are identical for closure-factory handlers — the user had to
    monkey-patch APIRouter.add_api_route to recover the same info."""
    app = FastAPI()

    @app.get("/x")
    async def handler_a() -> None: ...

    @app.get("/x")
    async def handler_b() -> None: ...

    conflicts = validate_routes(app)
    assert len(conflicts) == 1
    msg = conflicts[0]
    # Provenance bracket + the qualnames of both handlers.
    assert "[" in msg and "]" in msg
    assert "handler_a" in msg
    assert "handler_b" in msg


def test_clean_app_caches_empty_list() -> None:
    """No-conflict run still records the validated flag, so a second
    call doesn't re-scan."""
    app = FastAPI()

    @app.get("/x")
    async def x() -> None: ...

    assert validate_routes(app) == []
    # Second call short-circuits via the cache.
    assert validate_routes(app) == []
    assert app.state.dazzle_routes_validated is True
