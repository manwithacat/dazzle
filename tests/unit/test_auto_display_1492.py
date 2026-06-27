"""#1492 (UX-maturity 1a) — `display: auto` shape->form resolver.

Generalises the ad-hoc aggregate->SUMMARY / kanban promotions into one
`resolve_auto_display`. Opt-in: only `display: auto` regions route through it.
"""

from types import SimpleNamespace

from dazzle.core.ir.fields import FieldModifier, FieldType, FieldTypeKind
from dazzle.page.runtime.auto_display import resolve_auto_display


def _region(**kw) -> SimpleNamespace:
    base = {"source": "", "aggregates": {}, "group_by": None, "group_by_dims": None}
    base.update(kw)
    return SimpleNamespace(**base)


def _field(name: str, kind: FieldTypeKind, *mods: FieldModifier) -> SimpleNamespace:
    return SimpleNamespace(name=name, type=FieldType(kind=kind), modifiers=list(mods))


def _entity(name: str, *, fields=None, state_machine=None) -> SimpleNamespace:
    return SimpleNamespace(name=name, fields=fields or [], state_machine=state_machine)


# ── aggregate shapes ──────────────────────────────────────────────────────


def test_scalar_aggregate_to_summary() -> None:
    r = _region(aggregates={"total": object()})
    assert resolve_auto_display(r, {}) == "SUMMARY"


def test_single_dim_aggregate_to_bar_chart() -> None:
    r = _region(aggregates={"n": object()}, group_by="status")
    assert resolve_auto_display(r, {}) == "BAR_CHART"


def test_multi_dim_aggregate_to_pivot_table() -> None:
    r = _region(aggregates={"n": object()}, group_by_dims=["system", "severity"])
    assert resolve_auto_display(r, {}) == "PIVOT_TABLE"


# ── entity-shape signals ──────────────────────────────────────────────────


def test_state_machine_to_kanban() -> None:
    ent = _entity("Task", state_machine=object())
    r = _region(source="Task")
    assert resolve_auto_display(r, {"Task": ent}) == "KANBAN"


def test_meaningful_temporal_to_timeline() -> None:
    ent = _entity("Event", fields=[_field("event_date", FieldTypeKind.DATE)])
    r = _region(source="Event")
    assert resolve_auto_display(r, {"Event": ent}) == "TIMELINE"


def test_auto_timestamps_do_not_trigger_timeline() -> None:
    # created_at/updated_at are present on almost every entity — must NOT make
    # every list a timeline.
    ent = _entity(
        "Contact",
        fields=[
            _field("created_at", FieldTypeKind.DATETIME, FieldModifier.AUTO_ADD),
            _field("updated_at", FieldTypeKind.DATETIME, FieldModifier.AUTO_UPDATE),
            _field("name", FieldType(kind=FieldTypeKind.STR).kind),
        ],
    )
    r = _region(source="Contact")
    assert resolve_auto_display(r, {"Contact": ent}) == "LIST"


# ── precedence + fallback ─────────────────────────────────────────────────


def test_aggregate_wins_over_entity_shape() -> None:
    ent = _entity("Task", state_machine=object())
    r = _region(source="Task", aggregates={"n": object()})
    assert resolve_auto_display(r, {"Task": ent}) == "SUMMARY"


def test_unknown_source_falls_back_to_list() -> None:
    assert resolve_auto_display(_region(source="Nope"), {}) == "LIST"


def test_plain_entity_no_signal_falls_back_to_list() -> None:
    ent = _entity("Plain", fields=[_field("name", FieldType(kind=FieldTypeKind.STR).kind)])
    assert resolve_auto_display(_region(source="Plain"), {"Plain": ent}) == "LIST"
