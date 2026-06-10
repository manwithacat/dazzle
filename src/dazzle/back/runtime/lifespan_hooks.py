"""App lifespan hook registry — the supported replacement for ``@app.on_event``.

DazzleServer constructs the app with a custom ``lifespan`` (DB pool + audit logger).
**FastAPI/Starlette ignore ``@app.on_event`` handlers entirely when a custom lifespan
is set** (verified on FastAPI 0.122) — so the subsystem startup/shutdown hooks that used
``@ctx.app.on_event(...)`` silently never ran. Subsystems now register through this
registry instead, and the server's ``_lifespan`` drives the hooks.

Resilience: a hook that raises is logged and skipped, never aborting boot/shutdown. These
hooks were dead until now, so restoring them must not be able to turn a working deploy into
a crash loop — a misconfigured hook degrades to "feature off + a warning", as it was before.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_STARTUP_ATTR = "_dazzle_lifespan_startup"
_SHUTDOWN_ATTR = "_dazzle_lifespan_shutdown"

# A hook is a no-arg callable; it may be sync or return an awaitable.
LifespanHook = Callable[[], Any]


def init_lifespan_registry(app: Any) -> None:
    """Initialise the per-app hook lists. Call once at app construction, before
    subsystems register (idempotent — re-init clears, which only matters in tests)."""
    setattr(app.state, _STARTUP_ATTR, [])
    setattr(app.state, _SHUTDOWN_ATTR, [])


def register_lifespan_hook(
    app: Any, *, startup: LifespanHook | None = None, shutdown: LifespanHook | None = None
) -> None:
    """Register startup and/or shutdown callables to run in the app's lifespan.

    Replaces ``@app.on_event("startup")`` / ``@app.on_event("shutdown")``. Safe to call
    from a subsystem's ``startup(ctx)`` (build phase); the hooks fire later, in
    ``_lifespan`` startup order and reverse order on shutdown.
    """
    if startup is not None:
        _hooks(app, _STARTUP_ATTR).append(startup)
    if shutdown is not None:
        _hooks(app, _SHUTDOWN_ATTR).append(shutdown)


def _hooks(app: Any, attr: str) -> list[LifespanHook]:
    hooks = getattr(app.state, attr, None)
    if hooks is None:  # defensive — a code path that registered before init
        hooks = []
        setattr(app.state, attr, hooks)
    return hooks


async def _run_one(hook: LifespanHook) -> None:
    try:
        result = hook()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 — one hook must not abort the others / boot
        logger.warning("lifespan hook %r failed", getattr(hook, "__name__", hook), exc_info=True)


async def run_startup_hooks(app: Any) -> None:
    """Run all registered startup hooks in registration order (resilient)."""
    for hook in list(getattr(app.state, _STARTUP_ATTR, [])):
        await _run_one(hook)


async def run_shutdown_hooks(app: Any) -> None:
    """Run all registered shutdown hooks in REVERSE registration order (mirrors nested
    resource teardown), resilient to individual failures."""
    for hook in reversed(list(getattr(app.state, _SHUTDOWN_ATTR, []))):
        await _run_one(hook)


async def run_legacy_router_events(app: Any, phase: str) -> None:
    """Run HOST-APP ``@app.on_event`` handlers inside the dazzle lifespan (#1366).

    A custom ``lifespan=`` makes Starlette skip its default lifespan, which is
    the only thing that drains ``app.router.on_startup`` / ``on_shutdown`` —
    so downstream hooks registered on the app ``build()`` returns were
    appended to those lists and **silently never ran** (a host app lost its
    auth/pool init with no warning). v0.81.59's registry protected the
    framework's own subsystems; this drains the host's handlers with the
    original FastAPI semantics.

    Deliberate contrasts with the framework registry above:

    - **Exceptions propagate.** A failed host startup hook aborts boot —
      original ``on_event`` semantics, and exactly the loud failure the
      silent-loss incident needed. (Framework hooks stay resilient: they were
      dead for releases, so restoring them must not crash working deploys.)
    - **One WARNING per handler**, pointing at ``register_lifespan_hook`` —
      ``on_event`` is deprecated upstream and Starlette's own router-level
      support is already gone, so the bridge is a compatibility courtesy,
      not the recommended path.

    ``getattr`` defensively: a future FastAPI may drop the lists entirely.
    """
    attr = "on_startup" if phase == "startup" else "on_shutdown"
    handlers = list(getattr(getattr(app, "router", None), attr, []) or [])
    for handler in handlers:
        logger.warning(
            "Running legacy @app.on_event(%r) handler %r inside the dazzle lifespan "
            "(#1366). on_event is deprecated — migrate to "
            "dazzle.back.runtime.lifespan_hooks.register_lifespan_hook.",
            phase,
            getattr(handler, "__name__", handler),
        )
        result = handler()
        if inspect.isawaitable(result):
            await result
