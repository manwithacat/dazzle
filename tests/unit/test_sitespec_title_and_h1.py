"""Sitespec page title and heading, rendered through the real site router.

* #1107: the ``<title>`` carries the spec's ``product_name``, not "Dazzle".
* #1108: a page without a hero gets one page-title ``<h1>`` before its sections.
* #1108 / #1261: a page with a hero (typed or not) keeps the hero's ``<h1>`` as
  the only one.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.site_routes import create_site_page_routes

_SPEC = {
    "version": 1,
    "brand": {
        "product_name": "Acme Ledger",
        "tagline": "Books that balance",
        "company_legal_name": "Acme Ltd",
        "support_email": "support@example.com",
    },
    "pages": [
        {
            "route": "/",
            "type": "landing",
            "title": "Home",
            "sections": [{"type": "hero", "headline": "Close the month", "subhead": "Fast"}],
        },
        {
            "route": "/about",
            "type": "landing",
            "title": "About us",
            "sections": [{"type": "features", "items": [{"title": "Audit", "body": "Trail"}]}],
        },
    ],
    "layout": {"nav": {"public": []}, "footer": {"columns": [], "disclaimer": ""}},
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.state.fragment_chrome = True
    app.include_router(create_site_page_routes(_SPEC, project_root=None))
    return TestClient(app)


@pytest.mark.parametrize("route", ["/", "/about"])
def test_title_names_the_product(client: TestClient, route: str) -> None:
    body = client.get(route).text
    title = re.search(r"<title>(.*?)</title>", body, re.S)
    assert title and "Acme Ledger" in title.group(1) and "Dazzle" not in title.group(1)


def test_page_without_hero_gets_one_page_title_h1_before_sections(client: TestClient) -> None:
    body = client.get("/about").text
    assert re.findall(r"<h1\b", body) == ["<h1"]
    h1 = body.index('<h1 class="dz-page-title">About us</h1>')
    assert h1 < body.index("dz-section-features")


def test_hero_page_keeps_the_hero_h1_only(client: TestClient) -> None:
    body = client.get("/").text
    assert "dz-page-title" not in body
    assert len(re.findall(r"<h1\b", body)) == 1
    assert "Close the month" in body
