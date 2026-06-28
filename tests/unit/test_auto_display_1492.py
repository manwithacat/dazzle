"""#1492 (UX-maturity 1a) — `display: auto` shape->form resolver + default-flip.

Generalises the ad-hoc aggregate->SUMMARY / kanban promotions into one
`resolve_auto_display`. Since the default-flip, `resolve_region_display_mode`
makes a genuinely-unset `display:` (and an explicit `display: auto`) infer its
form, while an explicit verb stays authoritative.
"""

from types import SimpleNamespace

from dazzle.core.ir.fields import FieldModifier, FieldType, FieldTypeKind
from dazzle.page.runtime.auto_display import (
    resolve_auto_display,
    resolve_region_display_mode,
)


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


# ── default-flip: resolve_region_display_mode (#1492 level 2->3) ───────────────


def test_unset_display_infers_form_by_default() -> None:
    # A genuinely-unset `display:` (display_unset=True) with a scalar aggregate
    # now infers SUMMARY — the data-right form is the default, no `display:` line.
    r = _region(display="list", display_unset=True, aggregates={"total": object()})
    assert resolve_region_display_mode(r, {}) == "SUMMARY"


def test_explicit_list_is_authoritative_even_with_aggregates() -> None:
    # An author who explicitly writes `display: list` is never re-inferred,
    # even on an aggregate region the resolver would otherwise promote.
    r = _region(display="list", display_unset=False, aggregates={"total": object()})
    assert resolve_region_display_mode(r, {}) == "LIST"


def test_explicit_auto_routes_through_resolver() -> None:
    r = _region(display="auto", display_unset=False, group_by="status", aggregates={"n": object()})
    assert resolve_region_display_mode(r, {}) == "BAR_CHART"


def test_explicit_kanban_is_passed_through_unchanged() -> None:
    r = _region(display="kanban", display_unset=False)
    assert resolve_region_display_mode(r, {}) == "KANBAN"


def test_unset_plain_entity_still_lists() -> None:
    ent = _entity("Plain", fields=[_field("name", FieldType(kind=FieldTypeKind.STR).kind)])
    r = _region(display="list", display_unset=True, source="Plain")
    assert resolve_region_display_mode(r, {"Plain": ent}) == "LIST"
