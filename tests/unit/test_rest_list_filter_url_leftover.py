"""Leftover REST ?filter[preview_url]=zzz must not invent empty (cycle 2200).

leftover-honest email VALUES already exist (oral #80). REST
``list_handlers`` still landed leftover URL VALUES on known
``preview_url`` keys in ``gated_list`` / ``repo.list`` and invented
empty. Valid http(s) URLs ride; leftover restores unfiltered (omit).
Oral #81 — not another GET list email VALUE (oral #80).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_url_filter_fields,
    leftover_honest_filter_url,
    leftover_honest_list_filters,
)

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_LIST = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "handlers"
    / "list_handlers.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "acme_billing" / "dsl" / "entities.dsl"

_ALLOWED = frozenset({"id", "title", "status", "preview_url", "logo_url"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="preview_url", type=SimpleNamespace(kind="url")),
        SimpleNamespace(name="logo_url", type=SimpleNamespace(kind="url")),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[preview_url]": "zzz"}, {}),
        ({"filter[preview_url]": "ghost"}, {}),
        ({"filter[preview_url]": "not-a-url"}, {}),
        ({"filter[preview_url]": "example.com/preview"}, {}),
        ({"filter[preview_url]": "ftp://files.example.com/a.pdf"}, {}),
        (
            {"filter[preview_url]": "https://placehold.co/400"},
            {"preview_url": "https://placehold.co/400"},
        ),
        (
            {"filter[preview_url]": "http://example.com/a.png"},
            {"preview_url": "http://example.com/a.png"},
        ),
        ({"filter[logo_url]": "zzz"}, {}),
        (
            {"filter[logo_url]": "https://cdn.example.com/logo.svg"},
            {"logo_url": "https://cdn.example.com/logo.svg"},
        ),
        (
            {"filter[preview_url]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[preview_url]": "https://placehold.co/400", "filter[title]": "Invoice"},
            {"preview_url": "https://placehold.co/400", "title": "Invoice"},
        ),
        ({"preview_url": "zzz"}, {}),
        ({"preview_url": "https://placehold.co/400"}, {"preview_url": "https://placehold.co/400"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-url",
        "bracket-leftover-ghost",
        "bracket-leftover-phrase",
        "bracket-leftover-no-scheme",
        "bracket-leftover-ftp",
        "bracket-valid-https",
        "bracket-valid-http",
        "bracket-leftover-logo",
        "bracket-valid-logo",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-url",
        "bare-valid-url",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_url_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["preview_url", "logo_url", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_url_filter_fields_reads_spec() -> None:
    assert entity_url_filter_fields(_SPEC) == frozenset({"preview_url", "logo_url"})
    assert entity_url_filter_fields(None) == frozenset()
    assert entity_url_filter_fields(SimpleNamespace()) == frozenset()
    assert entity_url_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == (
        frozenset()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("not-a-url", ""),
        ("example.com/preview", ""),
        ("ftp://files.example.com/a.pdf", ""),
        ("https://", ""),
        ("", ""),
        (None, ""),
        ("https://placehold.co/400", "https://placehold.co/400"),
        ("http://example.com/a.png", "http://example.com/a.png"),
        (True, ""),
        (False, ""),
    ],
    ids=[
        "junk",
        "ghost",
        "phrase",
        "no-scheme",
        "ftp",
        "scheme-only",
        "empty",
        "none",
        "https",
        "http",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_url_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_url(raw) == expected


def test_helper_source_pins_list_filter_url_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_url_filter_fields" in src
    assert "_parse_list_filter_url_values" in src
    assert "filter[preview_url]=zzz" in src
    assert "leftover_honest_filter_url" in src


def test_list_handler_source_pins_filter_url_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[preview_url]=zzz" in src


def test_live_acme_billing_invoice_preview_url() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Invoice "Invoice":' in src
    assert "preview_url: url" in src
