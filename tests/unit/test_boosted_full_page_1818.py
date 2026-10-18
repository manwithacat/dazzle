"""#1818 — a boosted navigation gets the full document, so the app shell survives.

A workspace ``primary_actions`` button is ``<a hx-boost>``: htmx 4 sends it with
``HX-Request`` / ``HX-Boosted`` / ``HX-Target: body`` and swaps the response's
``<body>`` into the page. The page handler answered every HTMX request that did
not target the content slot with inner content only, so the swap replaced the
sidebar, topbar and breadcrumb with the bare surface. Only content-slot, drawer
and peek requests get content-only HTML; every other page GET is a full document.

Each case drives the real page router (``create_page_routes`` over the
``fixtures/custom_renderer`` AppSpec) through a ``TestClient``, with the header
values the vendored htmx 4 actually sends (``HX-Target`` is ``tag#id``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.page_routes import create_page_routes
from dazzle.http.runtime.renderers.init import register_default_renderers
from dazzle.http.runtime.services import RuntimeServices

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "custom_renderer"
_HX = {"HX-Request": "true"}


class _WordCloud:
    def render(self, surface: Any, ctx: Any) -> str:
        return "<section>cloud</section>"


@pytest.fixture(scope="module")
def client() -> TestClient:
    services = RuntimeServices()
    register_default_renderers(services)
    services.renderer_registry.register(name="word_cloud", handler=_WordCloud())
    app = FastAPI()
    app.include_router(
        create_page_routes(load_project_appspec(_FIXTURE), app_prefix="/app"), prefix="/app"
    )
    app.state.services = services
    return TestClient(app)


@pytest.mark.parametrize(
    ("headers", "full_document"),
    [
        pytest.param({}, True, id="plain-load"),
        pytest.param(
            {**_HX, "HX-Boosted": "true", "HX-Target": "body"}, True, id="boosted-body-target"
        ),
        pytest.param({**_HX, "HX-Target": "body"}, True, id="htmx-body-target"),
        pytest.param(
            {**_HX, "HX-Boosted": "true", "HX-History-Restore-Request": "true"},
            True,
            id="history-restore",
        ),
        pytest.param({**_HX, "HX-Target": "main#main-content"}, False, id="content-slot"),
        pytest.param(
            {**_HX, "HX-Target": "div#dz-detail-drawer-content"}, False, id="detail-drawer"
        ),
    ],
)
def test_only_slot_targeted_requests_get_content_only(
    client: TestClient, headers: dict[str, str], full_document: bool
) -> None:
    resp = client.get("/app/tag_cloud", headers=headers)
    assert resp.status_code == 200
    html = resp.text
    assert "<section>cloud</section>" in html
    shell = ('<nav class="dz-sidebar"', 'class="dz-topbar', "<title>", "<!DOCTYPE html>")
    if full_document:
        assert all(marker in html for marker in shell)
        # htmx 4 sets document.title from the response <head> — no trigger needed.
        assert "dz:titleUpdate" not in resp.headers.get("HX-Trigger-After-Swap", "")
    else:
        assert not any(marker in html for marker in shell)


def test_content_slot_request_retitles_the_page(client: TestClient) -> None:
    resp = client.get("/app/tag_cloud", headers={**_HX, "HX-Target": "main#main-content"})
    assert json.loads(resp.headers["HX-Trigger"]) == {"dz:titleUpdate": "Feedback word cloud"}
