"""DETAIL related-tab leftover as_of must not invent current children (cycle 2167).

Parent DETAIL time-travels via leftover-honest ``?as_of=`` (2166) but
related-tab ``_list_entity_in_process`` used to drop the date, so
children invented *now*. Empty / leftover restores *no as_of*
(current children). Valid YYYY-MM-DD still time-travels. Edit form
stays current (oral #50). Not leftover DETAIL as_of clone onto the
edit form, not leftover list as_of (2165), not leftover sort/page.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from dazzle.http.runtime.page_routes import (
    _parse_list_as_of,
    _related_tab_as_of_raw,
)

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (None, None),
        (date(2026, 6, 20), "2026-06-20"),
        (date(2025, 1, 1), "2025-01-01"),
        ("zzz", None),
        ("2abc", None),
        ("not-a-date", None),
        ("2026-06-20", "2026-06-20"),
        ("  ", None),
        ("", None),
    ],
    ids=[
        "none-current",
        "valid-date",
        "valid-date-old",
        "leftover-named",
        "leftover-suffix",
        "leftover-words",
        "iso-string",
        "whitespace",
        "empty",
    ],
)
def test_related_tab_as_of_raw_leftover_does_not_invent(
    as_of: object, expected: str | None
) -> None:
    assert _related_tab_as_of_raw(as_of) == expected


def test_related_tab_as_of_reuses_parent_leftover_honest_parse() -> None:
    """Related leftover shares DETAIL parse; does not invent a second theater."""
    assert _parse_list_as_of("zzz") is None
    assert _related_tab_as_of_raw(None) is None
    assert _related_tab_as_of_raw(date(2026, 6, 20)) == "2026-06-20"


def test_related_tab_fetch_forwards_parent_as_of() -> None:
    """Related ``_list_entity_in_process`` must receive leftover-honest as_of."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "as_of_raw=_related_tab_as_of_raw(_as_of)" in src
    assert "def _related_tab_as_of_raw(" in src
    assert "invented *current* related" in src or "invent *current* children" in src
    assert "_as_of = _detail_as_of(" in src


def test_edit_form_still_does_not_time_travel() -> None:
    """Do not clone DETAIL / related as_of onto the edit form (oral #50)."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "as_of_raw=" not in edit
