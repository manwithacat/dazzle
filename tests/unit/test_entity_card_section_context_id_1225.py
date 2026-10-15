"""#1225: per-section `filter: X = current_context` predicates must
resolve to the scoped record id.

Pre-fix, `_fetch_entity_card_section_rows` hardcoded the `context_id`
argument of the condition-filter conversion to None, so `filter:
student_profile = current_context` predicates silently dropped and
sections fan-fetched the first-scope row regardless of which pupil the
entity_card was scoped to.

These tests run the fetcher against a recording repository and assert on
the filters the section query actually carries. Real DB integration is
exercised by AegisMark's pupil_dashboard.
"""

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core.access import AccessComparisonKind, AccessConditionSpec
from dazzle.http.runtime.workspace_card_fetchers import _fetch_entity_card_section_rows


class _RecordingRepo:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, Any]] = []

    async def list(self, **kwargs: Any) -> dict[str, Any]:
        self.list_calls.append(kwargs)
        return {"items": [{"id": "mark-1"}]}


@dataclass
class _Ctx:
    """The fetcher ``dataclasses.replace``-s this per section."""

    source: str
    repositories: dict[str, Any] = field(default_factory=dict)
    entity_access_specs: dict[str, Any] = field(default_factory=dict)
    cedar_access_spec: Any | None = None


@pytest.mark.parametrize(
    ("context_kwargs", "expected_filters"),
    [
        pytest.param(
            {"context_id": "pupil-abc"},
            {"student_profile": "pupil-abc"},
            id="selected-context-filters-the-section-#1225",
        ),
        pytest.param({}, {}, id="no-selection-leaves-the-section-unfiltered"),
    ],
)
def test_section_query_filters_by_current_context(
    context_kwargs: dict[str, str], expected_filters: dict[str, str]
) -> None:
    repo = _RecordingRepo()
    section = SimpleNamespace(
        name="recent_marks",
        mode="mini_bars",
        source="MarkingResult",
        limit=5,
        filter=AccessConditionSpec(
            kind="comparison",
            field="student_profile",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_context",
        ),
    )

    rows = asyncio.run(
        _fetch_entity_card_section_rows(
            config=SimpleNamespace(sections=[section]),
            ctx=_Ctx(source="Pupil", repositories={"MarkingResult": repo}),
            request=None,
            auth_context=None,
            user_id="user-123",
            **context_kwargs,
        )
    )

    assert [call["filters"] for call in repo.list_calls] == [expected_filters]
    assert repo.list_calls[0]["page_size"] == 5
    assert rows == {0: [{"id": "mark-1"}]}
