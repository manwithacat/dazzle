"""Runtime service container — replaces module-level singletons.

Attached to app.state.services at startup.  Each app instance gets its own
services, enabling multi-tenant isolation and clean test fixtures.
"""

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from dazzle.core import ir
from dazzle.http.runtime.event_bus import EntityEventBus
from dazzle.http.runtime.presence_tracker import PresenceTracker
from dazzle.render.fragment.registry import PrimitiveRegistry, RendererRegistry


@dataclass
class RuntimeServices:
    """Container for runtime service instances. Attached at app boot to
    ``app.state.services`` and threaded as a ``services`` parameter
    into renderer / primitive / extension callbacks.

    Each app instance gets its own ``RuntimeServices``, enabling
    multi-tenant isolation and clean test fixtures.

    **Reading this from extension code.** Every attribute below is
    part of the framework's public contract for extension authors —
    renderers (``services.renderer_registry.resolve(...)`` from
    `fixtures/custom_renderer/`), primitives, route overrides, and
    any code that receives ``services`` as a parameter can read
    these. The ``Any``-typed optional services are typed loosely to
    dodge an import cycle at this level — see ``services: Any`` in
    ``dazzle.render.dispatch.dispatch_render`` for the same trick.

    **Required services (always present):**

    - ``event_bus`` (``EntityEventBus``) — in-process pub/sub for
      entity create/update/delete events. Extension code subscribes
      via ``services.event_bus.subscribe(entity, kind, handler)``.
      Constructed by default at app boot.
    - ``presence_tracker`` (``PresenceTracker``) — tracks live
      web-sockets per user for presence indicators. Read-only for
      most extension code; the framework's collab surfaces consume
      it. Renderer authors don't typically reach for this.
    - ``renderer_registry`` (``RendererRegistry``) — registry where
      custom renderers register and the dispatcher resolves them.
      Public API: ``register(name, handler)``,
      ``resolve(name) -> Handler | None``,
      ``registered_names() -> set[str]``. See
      ``fixtures/custom_renderer/`` for the registration shape and
      #1116 / #1117 for the manifest + dispatch contract.
    - ``primitive_registry`` (``PrimitiveRegistry``) — registers DSL
      primitives (computed-field operators, predicate evaluators,
      widgets). Public API mirrors ``renderer_registry``.

    **Optional services (may be None depending on deployment):**

    - ``event_framework`` — either an ``EventFramework`` (HLESS /
      ``dazzle.events.framework``) or a ``NullEventFramework`` when
      HLESS is not configured. Renderer code that fires domain
      events reaches for this; rendering-only renderers don't.
    - ``metrics_collector`` — the active metrics collector instance
      (Prometheus-compatible) when telemetry is enabled. Extension
      code emitting counters / histograms reads this. ``None`` when
      telemetry is off; extension code must branch on ``None`` to
      stay portable across deployments.
    - ``system_collector`` — system-level metrics (CPU / memory /
      event-bus depth). Mostly framework-internal; extension code
      rarely needs this.
    - ``metrics_emitter`` — push-side surface for metrics emission
      (the framework's metric-name → Counter adapter). Use when you
      need to emit a named metric without reaching for the collector
      directly.
    - ``process_manager`` — the active process / schedule runtime
      (Temporal / event-bus adapter). Extension code that
      starts domain processes reaches for this.
    - ``app_spec`` — the parsed Dazzle ``AppSpec`` for this app instance.
      Populated at boot. Used by the renderer dispatch ctx builder to do
      polymorphic-surface lookups for ``subtype_panel:`` blocks (#1217 Phase 3e).

    Anything not listed here is framework-internal and may change
    between minor versions. If you need to reach for it, file an
    issue — the goal is to surface what renderer authors legitimately
    need without locking the framework into a wider public API than
    it needs to commit to.

    See also: ``fixtures/custom_renderer/`` (worked example),
    ``docs/reference/access-control.md`` (renderer protocol), and
    #1121 (the design conversation that produced this docstring —
    a ``RendererServices`` Protocol shape was considered but
    deferred until extension authors signal that IDE help on the
    type surface matters more than this narrative).
    """

    event_bus: EntityEventBus = field(default_factory=EntityEventBus)
    presence_tracker: PresenceTracker = field(default_factory=PresenceTracker)
    renderer_registry: RendererRegistry = field(default_factory=RendererRegistry)
    primitive_registry: PrimitiveRegistry = field(default_factory=PrimitiveRegistry)
    # Typed `Any` to avoid an import cycle at this level — call sites
    # that need the concrete type cast or use TYPE_CHECKING blocks.
    event_framework: Any = None  # EventFramework | NullEventFramework | None
    metrics_collector: Any = None  # MetricsCollector | None
    system_collector: Any = None  # SystemCollector | None
    metrics_emitter: Any = None  # MetricsEmitter | None
    process_manager: Any = None  # ProcessManager | None
    app_spec: ir.AppSpec | None = (
        None  # ir.AppSpec | None — populated at boot, used by renderer dispatch ctx builder
    )


def get_services(request: Request) -> RuntimeServices:
    """FastAPI dependency — typed access to runtime services."""
    services: RuntimeServices = request.app.state.services
    return services
