"""#901: a pipeline stage counting a different entity runs unscoped, with a warning.

``display: pipeline_steps`` stages may count ANY entity. The region's scope
filters are resolved against the region's ``source:`` entity, so passing them to
another entity's count failed silently and showed 0. ``compute_pipeline_steps``
passes the scope only when the stage entity is the source entity; otherwise it
passes ``None`` and logs a cross-entity warning for operators to audit.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from dazzle.core.ir import AggregateRef
from dazzle.http.runtime import workspace_aggregation
from dazzle.http.runtime.workspace_region_computes import compute_pipeline_steps

_SCOPE = {"__scope_predicate": ("owner_id = %s", ["u-1"])}


@pytest.mark.parametrize(
    ("scope", "expected_scopes", "warns"),
    [
        pytest.param(_SCOPE, [_SCOPE, None], True, id="scoped-region-drops-scope-cross-entity"),
        pytest.param(None, [None, None], False, id="unscoped-region-no-warning"),
    ],
)
def test_stage_scope_follows_the_counted_entity(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    scope: dict[str, Any] | None,
    expected_scopes: list[Any],
    warns: bool,
) -> None:
    seen: list[tuple[str, Any]] = []

    async def fake_count(name: str, repo: Any, where: Any, scope_filters: Any = None, **kw: Any):
        seen.append((kw["source_entity"], scope_filters))
        return name, 7

    monkeypatch.setattr(workspace_aggregation, "_fetch_count_metric", fake_count)
    stages = [
        {"label": "Marked", "value": AggregateRef(func="count", entity="MarkingResult")},
        {"label": "Events", "value": AggregateRef(func="count", entity="AssessmentEvent")},
    ]
    repos = {"MarkingResult": object(), "AssessmentEvent": object()}
    with caplog.at_level(logging.WARNING):
        out = asyncio.run(compute_pipeline_steps(stages, repos, "MarkingResult", scope, False))

    assert seen == list(zip(["MarkingResult", "AssessmentEvent"], expected_scopes, strict=True))
    assert [s["value"] for s in out] == [7, 7]
    assert ("cross-entity count is unscoped" in caplog.text) is warns
