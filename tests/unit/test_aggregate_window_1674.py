"""#1674: last-reading windows parse on a metrics region and batch in SQL."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.ir import AggregateRef, DerivedMetric
from dazzle.core.parser import parse_modules
from dazzle.http.runtime.aggregate import AggregateBucket, MeasureWindow, build_aggregate_sql
from dazzle.http.runtime.workspace_aggregation import (
    _compute_aggregate_metrics,
    _window_group_key,
)
from tests.unit._aggregate_test_helpers import agg

WORKSPACE_TEMPLATE = """module t

app t "T"

entity Reading "Reading":
  id: uuid pk
  taken_at: datetime
  value_delta: decimal(12,3)
  elapsed_hours: decimal(8,3)

workspace daily_board "Daily board":
  purpose: "x"
  stage: "command_center"

  week_energy:
    source: Reading
    display: metrics
    aggregate:
{metrics}
"""


def _parse_region(tmp_path: Path, metric_lines: list[str]):
    metrics = "\n".join(f"      {line}" for line in metric_lines)
    f = tmp_path / "app.dsl"
    f.write_text(WORKSPACE_TEMPLATE.format(metrics=metrics), encoding="utf-8")
    (module,) = parse_modules([f])
    return module.fragment.workspaces[0].regions[0]


def test_biochart_board_parses(tmp_path: Path) -> None:
    region = _parse_region(
        tmp_path,
        [
            "kwh: sum(Reading.value_delta window week_from_monday on taken_at)",
            "elapsed_h: sum(Reading.elapsed_hours window week_from_monday on taken_at)",
            "avg_kw: kwh / elapsed_h",
            "last_week_kwh: sum(Reading.value_delta window previous_week on taken_at)",
            "last_day_kwh: sum(Reading.value_delta window last_complete_day on taken_at)",
        ],
    )
    kwh = region.aggregates["kwh"]
    assert isinstance(kwh, AggregateRef)
    assert kwh.window is not None
    assert kwh.window.kind == "week_from_monday"
    assert kwh.window.on == "taken_at"
    assert isinstance(region.aggregates["avg_kw"], DerivedMetric)
    last_week = region.aggregates["last_week_kwh"]
    assert isinstance(last_week, AggregateRef)
    assert last_week.window is not None
    assert last_week.window.kind == "previous_week"


def test_same_on_and_where_share_group_key(tmp_path: Path) -> None:
    region = _parse_region(
        tmp_path,
        [
            "kwh: sum(Reading.value_delta window week_from_monday on taken_at)",
            "hours: sum(Reading.elapsed_hours window week_from_monday on taken_at)",
            "last: sum(Reading.value_delta window previous_week on taken_at)",
        ],
    )
    kwh = region.aggregates["kwh"]
    hours = region.aggregates["hours"]
    last = region.aggregates["last"]
    assert isinstance(kwh, AggregateRef)
    assert isinstance(hours, AggregateRef)
    assert isinstance(last, AggregateRef)
    assert _window_group_key(kwh, "Reading") == _window_group_key(hours, "Reading")
    assert _window_group_key(kwh, "Reading") == _window_group_key(last, "Reading")


def test_monday_window_and_ratio_sql_contract() -> None:
    """Acceptance: Repository.aggregate SQL proves Monday bounds and SUM/SUM."""
    sql, _ = build_aggregate_sql(
        table_name="Reading",
        placeholder_style="%s",
        dimensions=[],
        measures={
            "kwh": "sum:value_delta",
            "hours": "sum:elapsed_hours",
            "avg_kw": "ratio:value_delta:elapsed_hours",
        },
        filters=None,
        measure_windows={
            "kwh": MeasureWindow(kind="week_from_monday", on="taken_at"),
            "hours": MeasureWindow(kind="week_from_monday", on="taken_at"),
            "avg_kw": MeasureWindow(kind="week_from_monday", on="taken_at"),
        },
    )
    assert "date_trunc('week', _anchor.last_at)" in sql
    assert "MAX(" in sql
    assert 'THEN "value_delta"' in sql
    assert 'THEN "elapsed_hours"' in sql
    assert "NULLIF" in sql
    assert sql.count("WITH _anchor") == 1


def _reading_repo(measures: dict[str, float]) -> MagicMock:
    taken_at = MagicMock()
    taken_at.name = "taken_at"
    taken_at.type = MagicMock()
    taken_at.type.kind = "datetime"
    repo = MagicMock()
    repo.entity_spec = MagicMock(fields=[taken_at])
    repo.db.placeholder = "%s"
    repo.aggregate = AsyncMock(return_value=[AggregateBucket(dimensions={}, measures=measures)])
    return repo


@pytest.mark.asyncio
async def test_windowed_metrics_batch_one_aggregate_call() -> None:
    """Same-entity last-reading windows share one Repository.aggregate round-trip."""
    repo = _reading_repo({"kwh": 80.0, "hours": 10.0})
    metrics = await _compute_aggregate_metrics(
        aggregates={
            "kwh": agg("sum(Reading.value_delta window week_from_monday on taken_at)"),
            "hours": agg("sum(Reading.elapsed_hours window week_from_monday on taken_at)"),
        },
        repositories={"Reading": repo},
        total=0,
        items=[],
        source_entity="Reading",
    )
    assert repo.aggregate.await_count == 1
    kwargs = repo.aggregate.await_args.kwargs
    assert set(kwargs["measures"]) == {"kwh", "hours"}
    assert kwargs["measure_windows"]["kwh"].kind == "week_from_monday"
    assert kwargs["measure_windows"]["hours"].on == "taken_at"
    by_label = {m["label"]: m["value"] for m in metrics}
    assert by_label["Kwh"] == 80.0
    assert by_label["Hours"] == 10.0
