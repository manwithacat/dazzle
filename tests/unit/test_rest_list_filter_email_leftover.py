"""Leftover REST ?filter[email]=zzz must not invent empty (cycle 2199).

leftover-honest int VALUES already exist (oral #79). REST
``list_handlers`` still landed leftover EMAIL VALUES on known
``email`` keys in ``gated_list`` / ``repo.list`` and invented
empty. Valid emails ride; leftover restores unfiltered (omit).
Oral #80 — not another GET list numeric VALUE (oral #79).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_email_filter_fields,
    leftover_honest_filter_email,
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

_ALLOWED = frozenset({"id", "title", "status", "email", "contact_email"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="email", type=SimpleNamespace(kind="email")),
        SimpleNamespace(name="contact_email", type=SimpleNamespace(kind="email")),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[email]": "zzz"}, {}),
        ({"filter[email]": "ghost"}, {}),
        ({"filter[email]": "not-an-email"}, {}),
        ({"filter[email]": "ada@"}, {}),
        ({"filter[email]": "ada@localhost"}, {}),
        ({"filter[email]": "ada@example.com"}, {"email": "ada@example.com"}),
        ({"filter[email]": "ada+ops@example.com"}, {"email": "ada+ops@example.com"}),
        ({"filter[contact_email]": "zzz"}, {}),
        ({"filter[contact_email]": "ops@example.com"}, {"contact_email": "ops@example.com"}),
        (
            {"filter[email]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[email]": "ada@example.com", "filter[title]": "Invoice"},
            {"email": "ada@example.com", "title": "Invoice"},
        ),
        ({"email": "zzz"}, {}),
        ({"email": "ada@example.com"}, {"email": "ada@example.com"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-email",
        "bracket-leftover-ghost",
        "bracket-leftover-phrase",
        "bracket-leftover-local-only",
        "bracket-leftover-no-dot",
        "bracket-valid-email",
        "bracket-valid-plus",
        "bracket-leftover-contact",
        "bracket-valid-contact",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-email",
        "bare-valid-email",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_email_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["email", "contact_email", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_email_filter_fields_reads_spec() -> None:
    assert entity_email_filter_fields(_SPEC) == frozenset({"email", "contact_email"})
    assert entity_email_filter_fields(None) == frozenset()
    assert entity_email_filter_fields(SimpleNamespace()) == frozenset()
    assert entity_email_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == (
        frozenset()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("not-an-email", ""),
        ("ada@", ""),
        ("ada@localhost", ""),
        ("", ""),
        (None, ""),
        ("ada@example.com", "ada@example.com"),
        ("ada+ops@example.com", "ada+ops@example.com"),
        (True, ""),
        (False, ""),
    ],
    ids=[
        "junk",
        "ghost",
        "phrase",
        "local-only",
        "no-dot",
        "empty",
        "none",
        "email",
        "plus",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_email_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_email(raw) == expected


def test_helper_source_pins_list_filter_email_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_email_filter_fields" in src
    assert "_parse_list_filter_email_values" in src
    assert "filter[email]=zzz" in src
    assert "leftover_honest_filter_email" in src


def test_list_handler_source_pins_filter_email_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[email]=zzz" in src


def test_live_acme_billing_user_email() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity User "User":' in src
    assert "email: email required" in src
