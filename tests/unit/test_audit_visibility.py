"""Tests for #956 cycle 7 — audit visibility gate + load_history loader.

Cycle 5 made `AuditEntry.by_user_id` correct. Cycle 6 built the read
primitives. Cycle 7 wires them together with the cycle-1 `show_to:`
RBAC gate.

These tests verify:

  * `find_audit_spec` returns the matching spec or None
  * `can_view_audit_history` honours the persona allow-list
    (deny-by-default, intersection check)
  * `load_history` short-circuits cleanly on:
      - missing audit_spec
      - failed RBAC check
      - empty service result
      - service exception (best-effort, never raises)
  * Service results are decoded + grouped via the cycle-6 helpers
  * Both list-of-dicts and paged-response shapes work
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import pytest

from dazzle.http.runtime.audit_visibility import (
    can_view_audit_history,
    find_audit_spec,
    load_history,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class _ShowTo:
    kind: str = "persona"
    personas: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.personas is None:
            self.personas = []


@dataclass
class _AuditSpec:
    entity: str
    track: list[str] = None  # type: ignore[assignment]
    show_to: _ShowTo = None  # type: ignore[assignment]
    retention_days: int = 0

    def __post_init__(self):
        if self.track is None:
            self.track = []
        if self.show_to is None:
            self.show_to = _ShowTo()


def _row(at, field_name, *, before, after, by="user-1", op="update"):
    return {
        "at": at,
        "entity_type": "Manuscript",
        "entity_id": "abc",
        "field_name": field_name,
        "operation": op,
        "before_value": json.dumps(before) if before is not None else None,
        "after_value": json.dumps(after) if after is not None else None,
        "by_user_id": by,
    }


# ---------------------------------------------------------------------------
# find_audit_spec
# ---------------------------------------------------------------------------


class TestFindAuditSpec:
    def test_returns_matching_spec(self):
        a = _AuditSpec(entity="Manuscript")
        b = _AuditSpec(entity="Order")
        assert find_audit_spec([a, b], "Manuscript") is a
        assert find_audit_spec([a, b], "Order") is b

    def test_returns_none_when_not_found(self):
        assert find_audit_spec([_AuditSpec(entity="X")], "Y") is None

    def test_empty_list_returns_none(self):
        assert find_audit_spec([], "X") is None


# ---------------------------------------------------------------------------
# can_view_audit_history
# ---------------------------------------------------------------------------


class TestCanViewAuditHistory:
    @pytest.mark.parametrize(
        ("spec", "viewer_personas", "expected"),
        [
            (None, ["teacher"], False),  # no spec → deny
            # Empty allow-list is an explicit deny (framework requires explicit grant)
            (_AuditSpec(entity="X", show_to=_ShowTo(personas=[])), ["teacher"], False),
            # Direct match
            (
                _AuditSpec(entity="X", show_to=_ShowTo(personas=["teacher", "admin"])),
                ["teacher"],
                True,
            ),
            # Intersection — one of viewer's roles matches
            (
                _AuditSpec(entity="X", show_to=_ShowTo(personas=["teacher", "admin"])),
                ["student", "admin"],
                True,
            ),
            # No intersection
            (
                _AuditSpec(entity="X", show_to=_ShowTo(personas=["admin"])),
                ["teacher", "student"],
                False,
            ),
            # Unknown kind fails closed (future kinds default-deny)
            (
                _AuditSpec(
                    entity="X",
                    show_to=_ShowTo(kind="future_kind", personas=["teacher"]),
                ),
                ["teacher"],
                False,
            ),
            # Empty viewer personas
            (_AuditSpec(entity="X", show_to=_ShowTo(personas=["admin"])), [], False),
        ],
        ids=[
            "none_spec_denies",
            "empty_show_to_denies",
            "persona_match_allows",
            "intersection_partial",
            "no_intersection_denies",
            "unknown_kind_fail_closed",
            "empty_viewer_denies",
        ],
    )
    def test_visibility(self, spec, viewer_personas, expected) -> None:
        assert can_view_audit_history(spec, viewer_personas) is expected


# ---------------------------------------------------------------------------
# load_history
# ---------------------------------------------------------------------------


class _StubAuditService:
    def __init__(self, rows: Any) -> None:
        self._rows = rows
        self.calls: list[dict[str, Any]] = []

    async def list(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._rows, Exception):
            raise self._rows
        return self._rows


class TestLoadHistory:
    def _viewable_spec(self) -> _AuditSpec:
        return _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["teacher"]))

    @pytest.mark.parametrize(
        ("svc_data", "use_spec", "expected_len"),
        [
            ([], False, 0),
            ([], True, 0),
            (
                {"items": [_row("t1", "status", before="d", after="s")], "total": 1, "page": 1},
                True,
                1,
            ),
            (RuntimeError("DB down"), True, 0),
        ],
        ids=[
            "test_none_spec_returns_empty",
            "test_empty_rows_returns_empty",
            "test_paged_response_shape_supported",
            "test_service_exception_returns_empty",
        ],
    )
    def test_load_history_cases(self, svc_data, use_spec: bool, expected_len: int):
        spec = self._viewable_spec() if use_spec else None
        result = asyncio.run(
            load_history(
                audit_service=_StubAuditService(svc_data),
                audit_spec=spec,
                entity_type="Manuscript",
                entity_id="abc",
                viewer_personas=["teacher"],
            )
        )
        assert len(result) == expected_len

    def test_rbac_denied_returns_empty(self):
        # Viewer doesn't have an allowed persona → return [] without
        # touching the audit service (no DB hit).
        spec = _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["admin"]))
        svc = _StubAuditService([_row("t1", "status", before="d", after="s")])
        result = asyncio.run(
            load_history(
                audit_service=svc,
                audit_spec=spec,
                entity_type="Manuscript",
                entity_id="abc",
                viewer_personas=["teacher"],
            )
        )
        assert result == []
        assert svc.calls == []  # No DB call when RBAC denies.

    def test_decoded_and_grouped(self):
        rows = [
            _row("t1", "status", before="draft", after="submitted"),
            _row("t1", "title", before="Old", after="New"),
            _row("t2", "status", before="submitted", after="published"),
        ]
        result = asyncio.run(
            load_history(
                audit_service=_StubAuditService(rows),
                audit_spec=self._viewable_spec(),
                entity_type="Manuscript",
                entity_id="abc",
                viewer_personas=["teacher"],
            )
        )
        # 3 rows → 2 groups (t1: status+title, t2: status alone).
        assert len(result) == 2
        assert len(result[0].fields) == 2
        assert len(result[1].fields) == 1
        # Decoded values reach the HistoryEntry.
        assert result[0].fields[0].decoded_after == "submitted"

    def test_filter_passed_to_service(self):
        svc = _StubAuditService([])
        asyncio.run(
            load_history(
                audit_service=svc,
                audit_spec=self._viewable_spec(),
                entity_type="Manuscript",
                entity_id="abc",
                viewer_personas=["teacher"],
                limit=50,
            )
        )
        # Filter discriminates by both entity_type and entity_id.
        assert len(svc.calls) == 1
        call = svc.calls[0]
        assert call["filters"] == {"entity_type": "Manuscript", "entity_id": "abc"}
        assert call["page_size"] == 50

    def test_pydantic_model_rows_supported(self):
        # The service may return Pydantic models; loader uses
        # `model_dump()` to coerce.
        from pydantic import BaseModel

        class _Row(BaseModel):
            at: str
            entity_type: str
            entity_id: str
            field_name: str
            operation: str
            before_value: str | None = None
            after_value: str | None = None
            by_user_id: str | None = None

        models = [
            _Row(
                at="t1",
                entity_type="Manuscript",
                entity_id="abc",
                field_name="status",
                operation="update",
                before_value=json.dumps("draft"),
                after_value=json.dumps("submitted"),
                by_user_id="user-1",
            ),
        ]
        result = asyncio.run(
            load_history(
                audit_service=_StubAuditService(models),
                audit_spec=self._viewable_spec(),
                entity_type="Manuscript",
                entity_id="abc",
                viewer_personas=["teacher"],
            )
        )
        assert len(result) == 1
        assert result[0].fields[0].decoded_after == "submitted"
