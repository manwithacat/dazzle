"""#1547 — the fragment search/select round-trip keys off field_name.

The result rows must target the WIDGET's ids (keyed by field name, not
source), the select endpoint must propagate field_name, and the
post-selection OOB input must satisfy the live widget contract
(dz-search-select-input + combobox aria + typeahead hx-get) so the
dz-search-select controller keeps working after a selection.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.fragment_routes import create_fragment_router


class _Cache:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], Any] = {}

    async def get(self, scope: str, key: str) -> Any:
        return self.data.get((scope, key))

    async def put(self, scope: str, key: str, value: Any, ttl: int = 0) -> None:
        self.data[(scope, key)] = value


def _client() -> TestClient:
    sources = {
        "companieshouse": {
            "url": "http://upstream.test/search",
            "detail_url": "http://upstream.test/detail",
            "display_key": "title",
            "value_key": "company_number",
            "autofill": {"registered_address": "address"},
        }
    }
    cache = _Cache()
    # Pre-seed the cache so no real HTTP happens.
    cache.data[("fragment:companieshouse", "http://upstream.test/search?q=acme")] = [
        {"title": "Acme Ltd", "company_number": "123"}
    ]
    cache.data[("fragment:companieshouse:detail", "http://upstream.test/detail/123")] = {
        "title": "Acme Ltd",
        "company_number": "123",
        "registered_address": "1 Acme Way",
    }
    app = FastAPI()
    app.include_router(create_fragment_router(sources, cache=cache))
    return TestClient(app)


def test_search_rows_target_the_field_ids() -> None:
    client = _client()
    r = client.get(
        "/_dazzle/fragments/search",
        params={"source": "companieshouse", "q": "acme", "field_name": "manufacturer"},
    )
    assert r.status_code == 200
    assert 'hx-target="#search-results-manufacturer"' in r.text
    # the select link propagates the field
    assert "field_name=manufacturer" in r.text


def test_select_oob_input_satisfies_the_widget_contract() -> None:
    client = _client()
    r = client.get(
        "/_dazzle/fragments/select",
        params={"source": "companieshouse", "id": "123", "field_name": "manufacturer"},
    )
    assert r.status_code == 200
    # hidden carrier keyed by FIELD name
    assert 'id="field-manufacturer"' in r.text
    # the OOB-swapped visible input keeps the live widget contract —
    # class, combobox aria, and the typeahead hx-get so re-searching works
    assert 'id="search-input-manufacturer"' in r.text
    assert 'class="dz-search-select-input"' in r.text
    assert 'role="combobox"' in r.text
    assert "/_dazzle/fragments/search?source=companieshouse" in r.text
    assert "field_name=manufacturer" in r.text
    # autofill OOB pair still present
    assert 'id="field-address"' in r.text


def test_search_without_field_name_still_works() -> None:
    """Legacy fallback: field_name defaults to source (pre-#1547 markup)."""
    client = _client()
    r = client.get(
        "/_dazzle/fragments/search",
        params={"source": "companieshouse", "q": "acme"},
    )
    assert r.status_code == 200
    assert 'hx-target="#search-results-companieshouse"' in r.text


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
