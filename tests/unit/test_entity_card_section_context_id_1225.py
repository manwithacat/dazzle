"""#1225: per-section `filter: X = current_context` predicates must
resolve to the scoped record id.

Pre-fix, `_fetch_entity_card_section_rows` called
`_extract_condition_filters(..., None, None)` — the last positional arg
(`context_id`) was hardcoded None. So `filter: student_profile =
current_context` predicates silently dropped, sections fan-fetched
the first-scope row regardless of which pupil the entity_card was
scoped to. The fix threads `context_id` from `env.user_ctx.filter_context`
down into the call.

These tests intercept `_extract_condition_filters` to confirm the
context_id is now propagated. Real DB integration is exercised by
AegisMark's pupil_dashboard once it picks up this version.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch


@dataclass
class _MockSection:
    name: str
    mode: str
    source: str | None = None
    filter: Any | None = None
    limit: int | None = None
    fields: list[str] = field(default_factory=list)


@dataclass
class _MockConfig:
    sections: list[_MockSection] = field(default_factory=list)


@dataclass
class _MockCtx:
    """Real dataclass — the fetcher uses dataclasses.replace on this."""

    source: str
    repositories: dict[str, Any] = field(default_factory=dict)
    entity_access_specs: dict[str, Any] = field(default_factory=dict)
    cedar_access_spec: Any | None = None


def _make_ctx_with_repo(entity_name: str) -> _MockCtx:
    return _MockCtx(
        source="Pupil",
        repositories={entity_name: MagicMock()},
    )


def test_context_id_threaded_into_extract_condition_filters() -> None:
    """The fix: context_id flows from caller → fetcher →
    _extract_condition_filters."""
    from dazzle.http.runtime.workspace_card_fetchers import (
        _fetch_entity_card_section_rows,
    )

    section = _MockSection(
        name="recent_marks",
        mode="mini_bars",
        source="MarkingResult",
        filter=MagicMock(),  # presence triggers the call; shape doesn't matter
        limit=5,
    )
    config = _MockConfig(sections=[section])
    ctx = _make_ctx_with_repo("MarkingResult")

    captured_calls: list[tuple] = []

    def _capture(*args, **_kwargs):
        captured_calls.append(args)
        return None

    with (
        patch(
            "dazzle.http.runtime.scope_filters._extract_condition_filters",
            side_effect=_capture,
        ),
        patch(
            "dazzle.http.runtime.workspace_card_fetchers._apply_workspace_scope_filters",
            return_value=({}, False),
        ),
        patch(
            "dazzle.http.runtime.workspace_card_fetchers._safe_fetch",
            return_value=[],
        ),
    ):
        asyncio.run(
            _fetch_entity_card_section_rows(
                config=config,
                ctx=ctx,
                request=MagicMock(),
                auth_context=MagicMock(),
                user_id="user-123",
                context_id="pupil-abc",
            )
        )

    assert len(captured_calls) == 1
    # _extract_condition_filters(condition, user_id, filters, logger,
    #   auth_context, ref_targets, context_id)
    # context_id is the 7th positional arg.
    assert captured_calls[0][6] == "pupil-abc"


def test_context_id_defaults_to_none_for_backward_compat() -> None:
    """When the caller doesn't pass context_id (older invocation),
    the fetcher still works — passes None through (matches pre-fix
    behaviour for the no-context-id branch)."""
    from dazzle.http.runtime.workspace_card_fetchers import (
        _fetch_entity_card_section_rows,
    )

    section = _MockSection(
        name="recent_marks",
        mode="mini_bars",
        source="MarkingResult",
        filter=MagicMock(),
        limit=5,
    )
    config = _MockConfig(sections=[section])
    ctx = _make_ctx_with_repo("MarkingResult")

    captured_calls: list[tuple] = []

    def _capture(*args, **_kwargs):
        captured_calls.append(args)
        return None

    with (
        patch(
            "dazzle.http.runtime.scope_filters._extract_condition_filters",
            side_effect=_capture,
        ),
        patch(
            "dazzle.http.runtime.workspace_card_fetchers._apply_workspace_scope_filters",
            return_value=({}, False),
        ),
        patch(
            "dazzle.http.runtime.workspace_card_fetchers._safe_fetch",
            return_value=[],
        ),
    ):
        asyncio.run(
            _fetch_entity_card_section_rows(
                config=config,
                ctx=ctx,
                request=MagicMock(),
                auth_context=MagicMock(),
                user_id="user-123",
                # context_id omitted
            )
        )

    assert len(captured_calls) == 1
    assert captured_calls[0][6] is None
