"""HTML list leftover include_closed must not invent open-only (cycle 2168).

Valid ``?include_closed=true`` / ``1`` / ``yes`` used to be dropped in
``_handle_table`` (never forwarded to ``_list_entity_in_process``), so
the HTML list invented the REST-default open-only collection. REST
already honours the param. Leftover junk (``zzz``, ``2abc``, ``maybe``)
must not invent closed rows. Empty / invalid restores *False*
(active-only). Not leftover as_of (2165), not leftover sort/page,
not related-tab as_of clone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.page_routes import _parse_list_include_closed

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("YES", True),
        ("  true  ", True),
        ("zzz", False),
        ("2abc", False),
        ("maybe", False),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        (None, False),
        ("  ", False),
    ],
    ids=[
        "true",
        "true-upper",
        "true-title",
        "one",
        "yes",
        "yes-upper",
        "true-padded",
        "leftover-named",
        "leftover-suffix",
        "leftover-maybe",
        "false",
        "zero",
        "no",
        "empty",
        "none",
        "whitespace",
    ],
)
def test_parse_list_include_closed_leftover_does_not_invent(raw: object, expected: bool) -> None:
    assert _parse_list_include_closed(raw) == expected


def test_handle_table_forwards_leftover_honest_include_closed() -> None:
    """``_handle_table`` must pass leftover-honest include_closed into the fetch."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "include_closed=_list_include_closed" in src
    assert "_list_include_closed = _parse_list_include_closed(" in src
    assert "def _parse_list_include_closed(" in src
    assert "invented the open-only" in src or "must not invent the open-only" in src


def test_list_entity_reparse_include_closed_instead_of_raw_bool() -> None:
    """In-process list must leftover-parse include_closed before gated_list."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "include_closed = _parse_list_include_closed(include_closed)" in src
    assert '"temporal_include_closed": include_closed' in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone related-tab as_of / DETAIL as_of / include_closed onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
    assert "include_closed" not in edit
