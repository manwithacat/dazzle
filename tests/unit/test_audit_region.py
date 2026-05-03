"""Tests for #956 cycle 9 — `render_audit_history_region` integration.

Cycles 7 (visibility + loader) and 8 (template + DSL flag) shipped the
two halves; cycle 9 is the integration glue. These tests verify the
combined call produces valid HTML for the canonical paths:

  * Happy path — audited entity with rows + RBAC pass → rendered list
  * No audit_spec for entity → empty-state HTML
  * RBAC deny → empty-state HTML (no DB call)
  * Empty rows → empty-state HTML
  * Service exception → empty-state HTML (best-effort)
  * Template render failure → safe minimal fallback markup

The renderer never raises, never returns empty string — always
returns valid HTML the caller can drop into the surface body.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from dazzle_back.runtime.audit_region import render_audit_history_region


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


class _StubAuditService:
    def __init__(self, rows: Any) -> None:
        self._rows = rows

    async def list(self, **kwargs: Any) -> Any:
        if isinstance(self._rows, Exception):
            raise self._rows
        return self._rows


@pytest.fixture()
def viewable_spec():
    return _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["teacher"]))


@pytest.fixture()
def restricted_spec():
    return _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["admin"]))


def _render(*, audit_service, audits, viewer_personas):
    return asyncio.run(
        render_audit_history_region(
            audit_service=audit_service,
            audits=audits,
            entity_type="Manuscript",
            entity_id="abc",
            viewer_personas=viewer_personas,
        )
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_renders_history_list(self, viewable_spec):
        rows = [
            _row("2026-05-03T12:00", "status", before="draft", after="submitted"),
        ]
        html = _render(
            audit_service=_StubAuditService(rows),
            audits=[viewable_spec],
            viewer_personas=["teacher"],
        )
        assert "dz-audit-history" in html
        assert "user-1" in html
        assert "draft" in html
        assert "submitted" in html
        assert "→" in html  # update arrow

    def test_groups_multiple_field_changes(self, viewable_spec):
        same_at = "2026-05-03T12:00"
        rows = [
            _row(same_at, "status", before="draft", after="submitted"),
            _row(same_at, "title", before="Old", after="New"),
        ]
        html = _render(
            audit_service=_StubAuditService(rows),
            audits=[viewable_spec],
            viewer_personas=["teacher"],
        )
        # Both fields appear in one grouped change card.
        assert "status" in html
        assert "title" in html


# ---------------------------------------------------------------------------
# Empty / denied paths — all return valid empty-state HTML
# ---------------------------------------------------------------------------


class TestEmptyStatePaths:
    def test_no_audit_spec_returns_empty_state(self):
        # Entity not in audits → empty state, no DB call.
        html = _render(
            audit_service=_StubAuditService([]),
            audits=[],  # No audit blocks at all
            viewer_personas=["teacher"],
        )
        assert "No history yet" in html
        assert "dz-audit-history" in html

    def test_rbac_denied_returns_empty_state(self, restricted_spec):
        # Viewer doesn't have an allowed persona → empty state.
        html = _render(
            audit_service=_StubAuditService([_row("t1", "status", before="d", after="s")]),
            audits=[restricted_spec],
            viewer_personas=["teacher"],
        )
        assert "No history yet" in html
        # Importantly, the disallowed values must NOT leak into the markup.
        assert "user-1" not in html

    def test_empty_rows_returns_empty_state(self, viewable_spec):
        html = _render(
            audit_service=_StubAuditService([]),
            audits=[viewable_spec],
            viewer_personas=["teacher"],
        )
        assert "No history yet" in html

    def test_service_exception_returns_empty_state(self, viewable_spec):
        # Service blow-up swallowed at load_history; renderer returns
        # empty-state markup — never propagates the exception.
        html = _render(
            audit_service=_StubAuditService(RuntimeError("DB down")),
            audits=[viewable_spec],
            viewer_personas=["teacher"],
        )
        assert "No history yet" in html


# ---------------------------------------------------------------------------
# Template failure fallback
# ---------------------------------------------------------------------------


class TestTemplateFailureFallback:
    def test_template_failure_returns_safe_markup(self, viewable_spec):
        # Patch render_fragment to raise — the renderer must catch
        # and return the minimal-but-valid empty-state markup so the
        # surface body always has a renderable region.
        rows = [_row("t1", "status", before="d", after="s")]
        with patch(
            "dazzle_ui.runtime.template_renderer.render_fragment",
            side_effect=RuntimeError("template missing"),
        ):
            html = _render(
                audit_service=_StubAuditService(rows),
                audits=[viewable_spec],
                viewer_personas=["teacher"],
            )
        assert "<section" in html
        assert "dz-audit-history" in html
        assert "No history yet" in html
