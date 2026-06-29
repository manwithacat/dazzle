"""Characterization fixtures for the legacy detail chrome (ADR-0049 Phase 2).

Freezes `render_detail_view` output across a chrome matrix as the visual-parity
reference the substrate `_build_view` must reproduce before the Phase 2
default-flip + the deletion of the legacy renderer. Per ADR-0049 D1 these are a
visual reference, NOT a post-flip byte gate. Deleted alongside
`render_detail_view` in Task 6.

Regenerate with `UPDATE_LEGACY_DETAIL_CHAR=1 uv run pytest
tests/unit/test_legacy_detail_chrome_char_phase2.py`.
"""

import os
import pathlib

import pytest

from dazzle.page.runtime.detail_renderer import render_detail_view
from dazzle.render.context import (
    DetailContext,
    ExternalLinkAction,
    FieldContext,
    IntegrationActionContext,
    TransitionContext,
)

_FIXTURE_DIR = pathlib.Path(__file__).parent / "__snapshots__" / "legacy_detail_chrome"
_UPDATE = os.environ.get("UPDATE_LEGACY_DETAIL_CHAR") == "1"

_FIELDS = [
    FieldContext(name="title", label="Title", type="text"),
    FieldContext(name="status", label="Status", type="text"),
]
_ITEM = {"id": "abc-123", "title": "Ship it", "status": "open"}


def _dc(**over: object) -> DetailContext:
    base: dict = {
        "entity_name": "Task",
        "title": "Ship it",
        "fields": _FIELDS,
        "item": dict(_ITEM),
        "back_url": "/task",
        "status_field": "status",
    }
    base.update(over)
    return DetailContext(**base)


# (label, DetailContext) — the chrome matrix.
DETAIL_MATRIX: list[tuple[str, DetailContext]] = [
    ("minimal", _dc()),
    ("edit_delete", _dc(edit_url="/task/abc-123/edit", delete_url="/api/task/abc-123")),
    (
        "transitions",
        _dc(
            transitions=[
                TransitionContext(to_state="done", label="Mark Done", api_url="/api/task/abc-123"),
            ]
        ),
    ),
    (
        "external",
        _dc(
            external_link_actions=[
                ExternalLinkAction(name="docs", label="Open Docs", url="https://x", new_tab=True),
            ]
        ),
    ),
    (
        "integration",
        _dc(
            integration_actions=[
                IntegrationActionContext(
                    label="Verify",
                    integration_name="ch",
                    mapping_name="verify",
                    api_url="/api/task/abc-123/integrations/ch/verify",
                ),
            ]
        ),
    ),
    ("history", _dc(show_history=True)),
    (
        "full",
        _dc(
            edit_url="/task/abc-123/edit",
            delete_url="/api/task/abc-123",
            transitions=[
                TransitionContext(to_state="done", label="Mark Done", api_url="/api/task/abc-123"),
            ],
            external_link_actions=[
                ExternalLinkAction(name="docs", label="Open Docs", url="https://x", new_tab=True),
            ],
            integration_actions=[
                IntegrationActionContext(
                    label="Verify",
                    integration_name="ch",
                    mapping_name="verify",
                    api_url="/api/task/abc-123/integrations/ch/verify",
                ),
            ],
            show_history=True,
        ),
    ),
]

_IDS = [c[0] for c in DETAIL_MATRIX]


def _fixture_path(label: str) -> pathlib.Path:
    return _FIXTURE_DIR / f"{label}.html"


@pytest.mark.parametrize(("label", "detail"), DETAIL_MATRIX, ids=_IDS)
def test_legacy_detail_chrome_matches_fixture(label: str, detail: DetailContext) -> None:
    rendered = render_detail_view(detail)
    path = _fixture_path(label)
    if _UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.exists(), f"missing fixture {path} — regenerate with UPDATE_LEGACY_DETAIL_CHAR=1"
    assert rendered == path.read_text(encoding="utf-8")
