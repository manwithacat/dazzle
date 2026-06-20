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
from dazzle.http.runtime.workspace_card_data import (
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


# ───────────────── Multi-source fan-out (#1015 v0.67.15) ────────


def test_multi_source_fan_out_emits_one_set_of_items_per_source() -> None:
    """When `items_per_source` is supplied, each as_task source
    contributes its own per-row task items."""
    cfg = _config(
        sources=[
            TaskSource(
                source="Alpha",
                as_task=TaskSourceTemplate(icon="alpha", title="A {{ name }}"),
            ),
            TaskSource(
                source="Beta",
                as_task=TaskSourceTemplate(icon="beta", title="B {{ name }}"),
            ),
        ]
    )
    items, chips = _build_task_inbox_payload(
        items=[],
        config=cfg,
        items_per_source={
            0: [{"id": "a1", "name": "Alice"}, {"id": "a2", "name": "Bob"}],
            1: [{"id": "b1", "name": "Carol"}],
        },
    )
    assert len(items) == 3
    assert chips == []
    titles = [i["title"] for i in items]
    assert "A Alice" in titles
    assert "A Bob" in titles
    assert "B Carol" in titles
    # icons routed per-source.
    icons_by_title = {i["title"]: i["icon"] for i in items}
    assert icons_by_title["A Alice"] == "alpha"
    assert icons_by_title["B Carol"] == "beta"


def test_multi_source_namespaces_item_ids_to_avoid_collision() -> None:
    """Two sources can have rows with identical ids (each lives in
    its own entity); the helper namespaces them with a source prefix."""
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="{{ name }}"),
            ),
            TaskSource(
                source="B",
                as_task=TaskSourceTemplate(icon="x", title="{{ name }}"),
            ),
        ]
    )
    items, _ = _build_task_inbox_payload(
        items=[],
        config=cfg,
        items_per_source={
            0: [{"id": "shared", "name": "FromA"}],
            1: [{"id": "shared", "name": "FromB"}],
        },
    )
    ids = [i["item_id"] for i in items]
    assert ids == ["src0-shared", "src1-shared"]


def test_multi_source_count_as_chip_uses_real_row_count() -> None:
    """Multi-source path counts rows directly per source, replacing
    the MVP single-source path's count=0 placeholder."""
    cfg = _config(
        sources=[
            TaskSource(source="A", count_as="manuscripts ready"),
            TaskSource(source="B", count_as="alerts active"),
        ]
    )
    _, chips = _build_task_inbox_payload(
        items=[],
        config=cfg,
        items_per_source={
            0: [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}],  # 3 rows
            1: [{"id": "a1"}],  # 1 row
        },
    )
    assert chips[0]["label"] == "manuscripts ready"
    assert chips[0]["count"] == 3
    assert chips[1]["label"] == "alerts active"
    assert chips[1]["count"] == 1


def test_multi_source_mixed_as_task_and_count_as() -> None:
    """The spec's heterogeneous shape: some sources contribute
    typed items, others contribute summary chips."""
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="{{ name }}"),
            ),
            TaskSource(source="B", count_as="manuscripts ready"),
            TaskSource(
                source="C",
                as_task=TaskSourceTemplate(icon="y", title="C {{ name }}"),
            ),
        ]
    )
    items, chips = _build_task_inbox_payload(
        items=[],
        config=cfg,
        items_per_source={
            0: [{"id": "a1", "name": "Alpha"}],
            1: [{"id": "b1"}, {"id": "b2"}],  # 2 → chip count
            2: [{"id": "c1", "name": "Gamma"}],
        },
    )
    assert len(items) == 2  # only as_task sources contribute items
    assert len(chips) == 1
    assert chips[0]["count"] == 2


def test_multi_source_missing_source_index_treated_as_empty() -> None:
    """Defensive: if upstream fetched only some of the configured
    sources, the helper treats missing indices as empty rather than
    crashing."""
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="{{ name }}"),
            ),
            TaskSource(source="B", count_as="ready"),
        ]
    )
    items, chips = _build_task_inbox_payload(
        items=[],
        config=cfg,
        items_per_source={
            0: [{"id": "a1", "name": "A"}],
            # source 1 missing
        },
    )
    assert len(items) == 1
    assert chips[0]["count"] == 0


def test_multi_source_overrides_single_source_fallback() -> None:
    """When items_per_source is provided, it wins over the
    fallback `items` list — the single-source path is bypassed
    entirely so callers don't accidentally double-count."""
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="{{ name }}"),
            ),
        ]
    )
    items, _ = _build_task_inbox_payload(
        items=[{"id": "fallback", "name": "Should-not-appear"}],
        config=cfg,
        items_per_source={0: [{"id": "real", "name": "From-fan-out"}]},
    )
    assert len(items) == 1
    assert items[0]["title"] == "From-fan-out"


def test_multi_source_empty_dict_falls_through_to_single_source() -> None:
    """An empty dict (truthy → False, len 0 → falsy) falls through
    to the MVP single-source path. This lets callers signal "no
    fan-out attempted" without a separate flag."""
    cfg = _config(
        sources=[
            TaskSource(
                source="A",
                as_task=TaskSourceTemplate(icon="x", title="{{ name }}"),
            ),
        ]
    )
    items, _ = _build_task_inbox_payload(
        items=[{"id": "fb", "name": "Fallback"}],
        config=cfg,
        items_per_source={},
    )
    assert items[0]["title"] == "Fallback"
    # Single-source MVP doesn't namespace the id.
    assert items[0]["item_id"] == "fb"
