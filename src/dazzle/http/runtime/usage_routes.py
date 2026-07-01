"""Framework beacon route for first-party usage-signal field capture.

ADR-0050 Phase 5 / 1a. The client hook (``dz-usage.js``) POSTs a fire-and-forget
``navigator.sendBeacon`` here on a form field's first engagement; the handler
records ``(surface, 'field', field)`` into the usage collector so the render-time
form-widget inferer (1a) can adapt to which fields users actually use.

Best-effort telemetry: the write is fire-and-forget (dropped under backpressure)
and the endpoint always returns ``204`` regardless. Same-origin beacons are
admitted by the CSRF origin gate (ADR-0033) — recording a usage count carries no
ambient-authority risk, so no exemption widens the CSRF surface. Mounted only
when a usage collector exists (i.e. a database is configured).
"""

from typing import Annotated

from fastapi import APIRouter, Form, Request, Response

from dazzle.http.runtime.usage_signal import USAGE_KIND_FIELD


def create_usage_routes() -> APIRouter:
    """Router exposing ``POST /_dz/usage/field`` for the field-engagement beacon."""
    router = APIRouter(prefix="/_dz/usage", tags=["internal"])

    @router.post("/field", status_code=204)
    async def record_field(
        request: Request,
        surface: Annotated[str, Form()] = "",
        field: Annotated[str, Form()] = "",
    ) -> Response:
        collector = getattr(request.app.state, "usage_collector", None)
        if collector is not None and surface and field:
            resolved = getattr(getattr(request, "state", None), "tenant", None)
            resolved_id = getattr(resolved, "id", None) if resolved is not None else None
            tenant_id = str(resolved_id) if resolved_id is not None else ""
            collector.record(
                tenant_id=tenant_id, surface=surface, kind=USAGE_KIND_FIELD, target=field
            )
        return Response(status_code=204)

    return router
