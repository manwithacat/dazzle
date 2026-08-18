"""Fragment leftover ?source= must not invent 200 empty-result theater (cycle 2248).

leftover-honest catalog stay-put already exists (oral #69 /
leftover_honest_auth_error). GET ``/_dazzle/fragments/search``
and ``/select`` still treated leftover ``zzz`` / ``ghost`` as a
miss and invented a 200 ``dz-search-result-empty`` theater
(``Unknown source``). Valid declared source names ride;
leftover stays put (400, no theater). Source is required —
blank stays put. Live fieldtest_hub
``source=companies_house_lookup.search_companies``. Oral #118
— not leftover catalog picker (oral #69), not leftover search
entity (oral #117).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.fragment_routes import (
    create_fragment_router,
    leftover_honest_fragment_source,
)

_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "fragment_routes.py"
)
_LIVE_DSL = Path(__file__).resolve().parents[2] / "examples" / "fieldtest_hub" / "dsl" / "app.dsl"
_LIVE_CTX = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "render" / "context.py"


class _Cache:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], Any] = {}

    async def get(self, scope: str, key: str) -> Any:
        return self.data.get((scope, key))

    async def put(self, scope: str, key: str, value: Any, ttl: int = 0) -> None:
        self.data[(scope, key)] = value


def _mount() -> TestClient:
    sources = {
        "companieshouse": {
            "url": "http://upstream.test/search",
            "detail_url": "http://upstream.test/detail",
            "display_key": "title",
            "value_key": "company_number",
        }
    }
    cache = _Cache()
    cache.data[("fragment:companieshouse", "http://upstream.test/search?q=acme")] = [
        {"title": "Acme Ltd", "company_number": "123"}
    ]
    cache.data[("fragment:companieshouse:detail", "http://upstream.test/detail/123")] = {
        "title": "Acme Ltd",
        "company_number": "123",
    }
    app = FastAPI()
    app.include_router(create_fragment_router(sources, cache=cache))
    return TestClient(app)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("companieshouse", "companieshouse"),
        ("  companieshouse  ", "companieshouse"),
        ("", None),
        (None, None),
        ("   ", None),
        ("zzz", None),
        ("ghost", None),
        ("MysterySource", None),
        ("CompaniesHouse", None),
        (["companieshouse"], None),
        ({"source": "companieshouse"}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "declared-rides",
        "strip",
        "empty-required",
        "none-required",
        "blank-required",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-mystery",
        "leftover-case",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_fragment_source_does_not_invent(raw: object, expected: str | None) -> None:
    declared = {"companieshouse": {}}
    assert leftover_honest_fragment_source(raw, declared) == expected


def test_leftover_source_zzz_search_does_not_invent_empty_theater() -> None:
    client = _mount()
    resp = client.get("/_dazzle/fragments/search", params={"source": "zzz", "q": "acme"})
    assert resp.status_code == 400
    assert resp.text == "Unknown source"
    assert "dz-search-result-empty" not in resp.text


def test_leftover_source_ghost_search_does_not_invent_empty_theater() -> None:
    client = _mount()
    resp = client.get("/_dazzle/fragments/search", params={"source": "ghost", "q": "acme"})
    assert resp.status_code == 400
    assert "dz-search-result-empty" not in resp.text


def test_leftover_source_zzz_select_does_not_invent_empty_theater() -> None:
    client = _mount()
    resp = client.get("/_dazzle/fragments/select", params={"source": "zzz", "id": "123"})
    assert resp.status_code == 400
    assert resp.text == "Unknown source"
    assert "dz-search-result-empty" not in resp.text


def test_valid_source_still_searches() -> None:
    client = _mount()
    resp = client.get(
        "/_dazzle/fragments/search",
        params={"source": "companieshouse", "q": "acme"},
    )
    assert resp.status_code == 200
    assert "Acme Ltd" in resp.text


def test_valid_source_still_selects() -> None:
    client = _mount()
    resp = client.get(
        "/_dazzle/fragments/select",
        params={"source": "companieshouse", "id": "123"},
    )
    assert resp.status_code == 200
    assert "Acme Ltd" in resp.text


def test_helper_source_pins_fragment_source_leftover() -> None:
    routes = _ROUTES.read_text()
    assert "def leftover_honest_fragment_source" in routes
    assert "leftover_honest_auth_error" in routes
    assert 'return HTMLResponse("Unknown source", status_code=400)' in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes


def test_live_fragment_search_and_fieldtest_source() -> None:
    assert 'endpoint=f"/_dazzle/fragments/search?source={source_name}"' in _LIVE_CTX.read_text()
    assert "source=companies_house_lookup.search_companies" in _LIVE_DSL.read_text()
