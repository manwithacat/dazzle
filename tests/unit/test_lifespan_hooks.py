"""Lifespan hook registry tests (the on_event → lifespan migration).

These close the coverage gap that let the latent bug ship: nothing asserted that
subsystem startup hooks actually FIRE when the app boots under the server's custom
lifespan. `@app.on_event` is silently ignored when a custom lifespan is set, so those
hooks were dead — and no test exercised the lifespan startup path to notice.
"""

import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.back.runtime.lifespan_hooks import (
    init_lifespan_registry,
    register_lifespan_hook,
    run_shutdown_hooks,
    run_startup_hooks,
)


def _app_with_lifespan() -> tuple[FastAPI, list[str]]:
    """A FastAPI app whose custom lifespan drives the hook registry (mirrors the server)."""
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_startup_hooks(app)
        try:
            yield
        finally:
            await run_shutdown_hooks(app)

    app = FastAPI(lifespan=lifespan)
    init_lifespan_registry(app)
    return app, events


def test_registered_hooks_fire_under_custom_lifespan() -> None:
    app, events = _app_with_lifespan()

    async def _startup() -> None:
        events.append("startup")

    async def _shutdown() -> None:
        events.append("shutdown")

    register_lifespan_hook(app, startup=_startup, shutdown=_shutdown)

    with TestClient(app):
        pass  # enters lifespan (startup), exits (shutdown)

    assert events == ["startup", "shutdown"]


def test_on_event_is_dead_under_custom_lifespan() -> None:
    """Documents WHY the bug existed: @app.on_event does NOT run when a custom lifespan
    is set — the exact trap the registry exists to avoid."""
    app, events = _app_with_lifespan()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the deprecation we're migrating off

        @app.on_event("startup")
        async def _legacy() -> None:  # pragma: no cover — must never run
            events.append("on_event")

    with TestClient(app):
        pass

    assert "on_event" not in events  # silently ignored


def test_sync_and_async_hooks_both_run() -> None:
    app, events = _app_with_lifespan()
    register_lifespan_hook(app, startup=lambda: events.append("sync"))

    async def _async() -> None:
        events.append("async")

    register_lifespan_hook(app, startup=_async)
    with TestClient(app):
        pass
    assert "sync" in events and "async" in events


def test_shutdown_runs_in_reverse_order() -> None:
    app, events = _app_with_lifespan()
    register_lifespan_hook(app, shutdown=lambda: events.append("A"))
    register_lifespan_hook(app, shutdown=lambda: events.append("B"))
    with TestClient(app):
        pass
    assert events == ["B", "A"]  # reverse registration order (nested teardown)


def test_a_failing_hook_does_not_abort_the_others_or_boot() -> None:
    app, events = _app_with_lifespan()

    async def _boom() -> None:
        raise RuntimeError("hook blew up")

    register_lifespan_hook(app, startup=_boom)
    register_lifespan_hook(app, startup=lambda: events.append("survived"))

    # Boot must still succeed (resilience: a dead-until-now hook can't crash a deploy).
    with TestClient(app):
        pass
    assert events == ["survived"]


def test_no_on_event_calls_remain_in_runtime_source() -> None:
    """Drift guard: subsystems + runtime must register via the lifespan registry, never
    `@app.on_event(...)` (which the custom lifespan ignores). Catches a regression."""
    import re
    from pathlib import Path

    import dazzle.back.runtime as runtime_pkg

    root = Path(runtime_pkg.__file__).parent
    pattern = re.compile(r"\.on_event\s*\(")  # a FastAPI on_event CALL (not the DSL field)
    offenders = []
    for py in root.rglob("*.py"):
        if py.name == "lifespan_hooks.py":
            continue  # its docstrings reference on_event by name
        for i, line in enumerate(py.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{py.relative_to(root)}:{i}")
    assert not offenders, f"use register_lifespan_hook, not @app.on_event: {offenders}"
