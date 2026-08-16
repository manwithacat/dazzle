"""Bulk all-matching leftover include_closed / as_of must not invent (cycle 2169).

The grid echoes the tbody ``hx-get`` query on all-matching POST. Treating
``include_closed`` / ``as_of`` as unconsumable invented 422. Dropping them
invented the open-only / current matched set (HTML list leftover-honours
both since 2165/2168). Empty / leftover restores False / no as_of. Valid
``true`` / YYYY-MM-DD still reach ``gated_list``. Not leftover list
include_closed clone, not related-tab as_of, not DETAIL as_of onto edit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dazzle.http.runtime.bulk_payload import (
    BulkQueryError,
    _echo_temporal,
    _echo_to_query,
    resolve_all_matching_ids,
)

_BULK_PAYLOAD = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "bulk_payload.py"
)
_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)


@pytest.mark.parametrize(
    ("echo", "as_of", "include_closed"),
    [
        ({}, None, False),
        ({"include_closed": "true"}, None, True),
        ({"include_closed": "TRUE"}, None, True),
        ({"include_closed": "1"}, None, True),
        ({"include_closed": "yes"}, None, True),
        ({"include_closed": "  yes  "}, None, True),
        ({"include_closed": "zzz"}, None, False),
        ({"include_closed": "2abc"}, None, False),
        ({"include_closed": "maybe"}, None, False),
        ({"include_closed": "false"}, None, False),
        ({"as_of": "2026-06-20"}, "2026-06-20", False),
        ({"as_of": " 2026-01-01 "}, "2026-01-01", False),
        ({"as_of": "2abc"}, None, False),
        ({"as_of": "zzz"}, None, False),
        ({"as_of": "not-a-date"}, None, False),
        ({"as_of": "2026-13-01"}, None, False),
        (
            {"as_of": "2026-06-20", "include_closed": "true"},
            "2026-06-20",
            True,
        ),
        (
            {"as_of": "zzz", "include_closed": "maybe"},
            None,
            False,
        ),
    ],
    ids=[
        "empty",
        "include-true",
        "include-upper",
        "include-one",
        "include-yes",
        "include-yes-padded",
        "include-leftover-named",
        "include-leftover-suffix",
        "include-leftover-maybe",
        "include-false",
        "as-of-valid",
        "as-of-valid-padded",
        "as-of-leftover-suffix",
        "as-of-leftover-named",
        "as-of-leftover-words",
        "as-of-leftover-month",
        "both-valid",
        "both-leftover",
    ],
)
def test_echo_temporal_leftover_does_not_invent(
    echo: dict[str, str], as_of: str | None, include_closed: bool
) -> None:
    assert _echo_temporal(echo) == (as_of, include_closed)


@pytest.mark.parametrize(
    "echo",
    [
        {"include_closed": "true"},
        {"include_closed": "zzz"},
        {"as_of": "2026-06-20"},
        {"as_of": "2abc"},
        {"as_of": "zzz", "include_closed": "maybe", "page": "2", "sort": "name"},
    ],
    ids=["include-true", "include-leftover", "as-of-valid", "as-of-leftover", "mixed"],
)
def test_echo_to_query_does_not_reject_temporal(echo: dict[str, str]) -> None:
    search, filters = _echo_to_query(echo, search_fields=None, filter_fields=None)
    assert search is None
    assert filters is None


def test_echo_to_query_still_rejects_unconsumable_bare() -> None:
    with pytest.raises(BulkQueryError, match="bogus"):
        _echo_to_query({"bogus": "x"}, search_fields=None, filter_fields=None)


@pytest.mark.asyncio
async def test_resolve_forwards_leftover_honest_temporal(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def _fake_gated_list(_service: Any, _access: Any, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"items": [{"id": "r1"}], "total": 1}

    monkeypatch.setattr("dazzle.http.runtime.bulk_payload.gated_list", _fake_gated_list)
    ids = await resolve_all_matching_ids(
        service=object(),
        access=object(),
        echo={"include_closed": "true", "as_of": "2026-06-20", "page": "2"},
        search_fields=None,
        filter_fields=None,
    )
    assert ids == ["r1"]
    assert seen["temporal_include_closed"] is True
    assert seen["temporal_as_of_raw"] == "2026-06-20"


@pytest.mark.asyncio
async def test_resolve_leftover_temporal_restores_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def _fake_gated_list(_service: Any, _access: Any, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"items": [{"id": "r1"}], "total": 1}

    monkeypatch.setattr("dazzle.http.runtime.bulk_payload.gated_list", _fake_gated_list)
    await resolve_all_matching_ids(
        service=object(),
        access=object(),
        echo={"include_closed": "zzz", "as_of": "2abc"},
        search_fields=None,
        filter_fields=None,
    )
    assert seen["temporal_include_closed"] is False
    assert seen["temporal_as_of_raw"] is None


def test_resolve_source_pins_temporal_kwargs() -> None:
    src = _BULK_PAYLOAD.read_text(encoding="utf-8")
    assert "temporal_as_of_raw=as_of_raw" in src
    assert "temporal_include_closed=include_closed" in src
    assert "as_of_raw, include_closed = _echo_temporal(echo)" in src
    assert "_TEMPORAL_ECHO_KEYS" in src
    assert "invented 422" in src or "not 422" in src


def test_edit_form_still_does_not_time_travel_or_include_closed() -> None:
    """Do not clone leftover list / related-tab / DETAIL as_of onto edit."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    edit = src.split("async def _handle_edit_form")[1].split("async def ")[0]
    assert "_detail_as_of" not in edit
    assert "_related_tab_as_of_raw" not in edit
    assert "as_of=" not in edit
    assert "include_closed" not in edit
