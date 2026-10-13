"""#1365: the metrics router must never poison /openapi.json.

The /_dazzle/metrics endpoint was a functools.partial registered via
add_api_route. Combined with `from __future__ import annotations`, its
`-> Response` annotation stayed ForwardRef('Response') (a partial has no
__globals__) and pydantic's TypeAdapter 500'd OpenAPI generation app-wide.
The endpoint now serves the empty Prometheus document (no collector is
wired) and must keep serving it without touching the OpenAPI schema.
"""

from fastapi import FastAPI

from dazzle.http.runtime.metrics_routes import create_metrics_routes


def test_openapi_builds_with_metrics_router_mounted() -> None:
    app = FastAPI()
    app.include_router(create_metrics_routes())
    schema = app.openapi()  # raised PydanticUndefinedAnnotation pre-#1365
    # Scrape plumbing stays out of the public API surface.
    assert "/_dazzle/metrics" not in schema.get("paths", {})


def test_metrics_endpoint_still_serves() -> None:
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(create_metrics_routes())
    client = TestClient(app)
    resp = client.get("/_dazzle/metrics")
    assert resp.status_code == 200
    assert "collector not configured" in resp.text
    assert resp.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    # /docs and /openapi.json serve too — the app-wide 500 is gone.
    assert client.get("/openapi.json").status_code == 200
