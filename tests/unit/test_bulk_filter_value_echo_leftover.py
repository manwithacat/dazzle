"""Bulk all-matching leftover filter VALUE must not invent empty (cycle 2206).

leftover-honest GET list filter VALUES already exist (oral #85).
All-matching bulk echo still landed leftover ``filter[status]=zzz``
in ``gated_list`` and invented an empty mutation while the leftover-
honest list view omitted (user saw unfiltered). Valid declared tokens
ride via leftover_honest_list_filters. Leftover omits (view parity).
Unknown echo keys still 422 fail-closed (do not widen). Oral #86 —
not another GET list typed VALUE kind (oral #85).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.http.runtime.bulk_payload import (
    BulkQueryError,
    _echo_to_query,
    resolve_all_matching_ids,
)

_BULK_PAYLOAD = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "bulk_payload.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "support_tickets" / "dsl" / "app.dsl"

_STATUS = ("open", "in_progress", "resolved", "closed")
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status", type=SimpleNamespace(enum_values=list(_STATUS))),
        SimpleNamespace(
            name="priority", type=SimpleNamespace(enum_values=("low", "medium", "high"))
        ),
    ]
)


@pytest.mark.parametrize(
    ("echo", "expected"),
    [
        ({"filter[status]": "zzz"}, None),
        ({"filter[status]": "ghost"}, None),
        ({"filter[status]": "open"}, {"status": "open"}),
        ({"filter[status]": "zzz", "filter[title]": "Invoice"}, {"title": "Invoice"}),
        (
            {"filter[status]": "open", "filter[title]": "Invoice"},
            {"status": "open", "title": "Invoice"},
        ),
        ({"status": "zzz"}, None),
        ({"status": "in_progress"}, {"status": "in_progress"}),
        ({}, None),
    ],
    ids=[
        "bracket-leftover-status",
        "bracket-leftover-ghost",
        "bracket-valid-status",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-status",
        "bare-valid-status",
        "empty-echo",
    ],
)
def test_echo_leftover_filter_values_do_not_invent(
    echo: dict[str, str], expected: dict[str, str] | None
) -> None:
    search, filters = _echo_to_query(
        echo,
        search_fields=["title"],
        filter_fields=["status", "priority", "title"],
        entity_spec=_SPEC,
    )
    assert search is None
    assert filters == expected


def test_echo_to_query_still_rejects_unconsumable_bare() -> None:
    with pytest.raises(BulkQueryError, match="bogus"):
        _echo_to_query(
            {"filter[status]": "zzz", "bogus": "x"},
            search_fields=None,
            filter_fields=["status"],
            entity_spec=_SPEC,
        )


@pytest.mark.asyncio
async def test_resolve_forwards_leftover_honest_filter_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def _fake_gated_list(_service: Any, _access: Any, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"items": [{"id": "r1"}], "total": 1}

    monkeypatch.setattr("dazzle.http.runtime.bulk_payload.gated_list", _fake_gated_list)
    service = SimpleNamespace(entity_spec=_SPEC)
    ids = await resolve_all_matching_ids(
        service=service,
        access=object(),
        echo={"filter[status]": "open", "page": "2"},
        search_fields=None,
        filter_fields=["status"],
    )
    assert ids == ["r1"]
    assert seen["user_filters"] == {"status": "open"}


@pytest.mark.asyncio
async def test_resolve_leftover_filter_value_restores_unfiltered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def _fake_gated_list(_service: Any, _access: Any, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"items": [{"id": "r1"}], "total": 1}

    monkeypatch.setattr("dazzle.http.runtime.bulk_payload.gated_list", _fake_gated_list)
    await resolve_all_matching_ids(
        service=SimpleNamespace(entity_spec=_SPEC),
        access=object(),
        echo={"filter[status]": "zzz"},
        search_fields=None,
        filter_fields=["status"],
    )
    assert seen["user_filters"] is None


def test_bulk_source_pins_leftover_honest_list_filters() -> None:
    src = _BULK_PAYLOAD.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert 'entity_spec=getattr(service, "entity_spec", None)' in src
    assert "filter[status]=zzz" in src


def test_live_support_tickets_ticket_status_enum() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Ticket "Support Ticket":' in src
    assert "status: enum[open,in_progress,resolved,closed]=open" in src
