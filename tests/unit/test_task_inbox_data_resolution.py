"""Issue #1015 (v0.67.14): regression tests for the task_inbox
data resolution layer.

Covers `_build_task_inbox_payload` — the helper that produces
(items, chips) tuple from already-scoped source rows + IR config.
The MVP single-source path folds the region's items list against
the first as_task source; multi-source heterogeneous fanout is
deferred (chips render with count=0 until the per-source query
ship).
"""

from __future__ import annotations

from dazzle.core.ir.workspaces import TaskInboxConfig, TaskSource, TaskSourceTemplate
from dazzle_back.runtime.workspace_rendering import (
    _build_task_inbox_payload,
    _coerce_urgency,
)


def _config(*, sources: list[TaskSource] | None = None) -> TaskInboxConfig:
    return TaskInboxConfig(
        sources=sources
        or [
            TaskSource(
                source="Item",
                as_task=TaskSourceTemplate(
                    icon="register", title="Process {{ name }}", meta="{{ state }}"
                ),
            )
        ]
    )


def test_returns_empty_when_no_items_and_no_chips() -> None:
    items, chips = _build_task_inbox_payload(items=[], config=_config())
    assert items == []
    assert chips == []


def test_returns_empty_when_config_missing() -> None:
    items, chips = _build_task_inbox_payload(items=[{"id": "1"}], config=None)
    assert items == []
    assert chips == []


def test_builds_one_inbox_item_per_row_via_as_task() -> None:
    rows = [
        {"id": "i1", "name": "Alpha", "state": "pending"},
        {"id": "i2", "name": "Beta", "state": "review"},
    ]
    items, chips = _build_task_inbox_payload(items=rows, config=_config())
    assert len(items) == 2
    assert items[0]["item_id"] == "i1"
    assert items[0]["title"] == "Process Alpha"
    assert items[0]["meta"] == "pending"
    assert items[0]["icon"] == "register"
    assert items[1]["title"] == "Process Beta"


def test_skips_rows_without_id() -> None:
    rows = [
        {"id": "i1", "name": "Alpha", "state": "pending"},
        {"name": "no-id", "state": "x"},
        {"id": "", "name": "empty-id", "state": "x"},
    ]
    items, _ = _build_task_inbox_payload(items=rows, config=_config())
    assert len(items) == 1


def test_urgency_resolves_from_severity_or_priority_fields() -> None:
    rows = [
        {"id": "i1", "name": "A", "state": "x", "severity": "critical"},
        {"id": "i2", "name": "B", "state": "x", "priority": "low"},
        {"id": "i3", "name": "C", "state": "x", "urgency": "due"},
    ]
    items, _ = _build_task_inbox_payload(items=rows, config=_config())
    assert items[0]["urgency"] == "overdue"  # critical → overdue
    assert items[1]["urgency"] == "soon"  # low → soon
    assert items[2]["urgency"] == "due"


def test_urgency_defaults_to_later_without_signal() -> None:
    rows = [{"id": "i1", "name": "A", "state": "x"}]
    items, _ = _build_task_inbox_payload(items=rows, config=_config())
    assert items[0]["urgency"] == "later"


def test_count_as_source_emits_chip_with_label() -> None:
    cfg = _config(
        sources=[
            TaskSource(
                source="Item",
                as_task=TaskSourceTemplate(icon="x", title="Process {{ name }}"),
            ),
            TaskSource(source="Item", count_as="items in review"),
        ]
    )
    items, chips = _build_task_inbox_payload(items=[{"id": "i1", "name": "A"}], config=cfg)
    assert len(chips) == 1
    assert chips[0]["label"] == "items in review"
    # Single-source MVP: chip count is 0 until per-source filter eval lands.
    assert chips[0]["count"] == 0


def test_chips_only_config_emits_chips_no_items() -> None:
    cfg = _config(
        sources=[
            TaskSource(source="Item", count_as="alerts active"),
            TaskSource(source="Item", count_as="alerts ack'd"),
        ]
    )
    items, chips = _build_task_inbox_payload(items=[{"id": "i1"}], config=cfg)
    assert items == []
    assert len(chips) == 2


def test_no_as_task_source_means_no_per_row_items() -> None:
    cfg = _config(sources=[TaskSource(source="Item", count_as="x")])
    items, _ = _build_task_inbox_payload(items=[{"id": "i1"}, {"id": "i2"}], config=cfg)
    assert items == []


def test_first_as_task_source_wins_when_multiple_declared() -> None:
    cfg = _config(
        sources=[
            TaskSource(
                source="Item",
                as_task=TaskSourceTemplate(icon="primary", title="P {{ name }}"),
            ),
            TaskSource(
                source="Item",
                as_task=TaskSourceTemplate(icon="secondary", title="S {{ name }}"),
            ),
        ]
    )
    items, _ = _build_task_inbox_payload(items=[{"id": "i1", "name": "A"}], config=cfg)
    assert items[0]["icon"] == "primary"
    assert items[0]["title"] == "P A"


def test_coerce_urgency_passes_through_known_bands() -> None:
    for band in ("overdue", "due", "soon", "later"):
        assert _coerce_urgency(band) == band


def test_coerce_urgency_uppercase_normalizes() -> None:
    assert _coerce_urgency("CRITICAL") == "overdue"
    assert _coerce_urgency("High") == "overdue"


def test_coerce_urgency_unknown_falls_through_to_later() -> None:
    assert _coerce_urgency("rainbow") == "later"
