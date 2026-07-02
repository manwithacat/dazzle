"""#1492 (UX-maturity 1a) — `display: auto` shape->form resolver + default-flip.

Generalises the ad-hoc aggregate->SUMMARY / kanban promotions into one
`resolve_auto_display`. Since the default-flip, `resolve_region_display_mode`
makes a genuinely-unset `display:` (and an explicit `display: auto`) infer its
form, while an explicit verb stays authoritative.
"""

from types import SimpleNamespace

import pytest

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


_SM_TASK = _entity("Task", state_machine=object())
_TEMPORAL_EVENT = _entity("Event", fields=[_field("event_date", FieldTypeKind.DATE)])
# created_at/updated_at are present on almost every entity — must NOT make
# every list a timeline.
_AUTO_TS_CONTACT = _entity(
    "Contact",
    fields=[
        _field("created_at", FieldTypeKind.DATETIME, FieldModifier.AUTO_ADD),
        _field("updated_at", FieldTypeKind.DATETIME, FieldModifier.AUTO_UPDATE),
        _field("name", FieldTypeKind.STR),
    ],
)
_PLAIN = _entity("Plain", fields=[_field("name", FieldTypeKind.STR)])


@pytest.mark.parametrize(
    ("region", "entities", "expected"),
    [
        # aggregate shapes ---------------------------------------------------
        pytest.param(
            _region(aggregates={"total": object()}),
            {},
            "SUMMARY",
            id="scalar-aggregate-to-summary",
        ),
        pytest.param(
            _region(aggregates={"n": object()}, group_by="status"),
            {},
            "BAR_CHART",
            id="single-dim-aggregate-to-bar-chart",
        ),
        pytest.param(
            _region(aggregates={"n": object()}, group_by_dims=["system", "severity"]),
            {},
            "PIVOT_TABLE",
            id="multi-dim-aggregate-to-pivot-table",
        ),
        # entity-shape signals -----------------------------------------------
        pytest.param(
            _region(source="Task"),
            {"Task": _SM_TASK},
            "KANBAN",
            id="state-machine-to-kanban",
        ),
        pytest.param(
            _region(source="Event"),
            {"Event": _TEMPORAL_EVENT},
            "TIMELINE",
            id="meaningful-temporal-to-timeline",
        ),
        pytest.param(
            _region(source="Contact"),
            {"Contact": _AUTO_TS_CONTACT},
            "LIST",
            id="auto-timestamps-do-not-trigger-timeline",
        ),
        # precedence + fallback ----------------------------------------------
        pytest.param(
            _region(source="Task", aggregates={"n": object()}),
            {"Task": _SM_TASK},
            "SUMMARY",
            id="aggregate-wins-over-entity-shape",
        ),
        pytest.param(
            _region(source="Nope"),
            {},
            "LIST",
            id="unknown-source-falls-back-to-list",
        ),
        pytest.param(
            _region(source="Plain"),
            {"Plain": _PLAIN},
            "LIST",
            id="plain-entity-no-signal-falls-back-to-list",
        ),
    ],
)
def test_resolve_auto_display(region: SimpleNamespace, entities: dict, expected: str) -> None:
    """One (region shape, entities) -> resolved form row per #1492 contract."""
    assert resolve_auto_display(region, entities) == expected


@pytest.mark.parametrize(
    ("region", "entities", "expected"),
    [
        # A genuinely-unset `display:` (display_unset=True) with a scalar
        # aggregate now infers SUMMARY — the data-right form is the default,
        # no `display:` line.
        pytest.param(
            _region(display="list", display_unset=True, aggregates={"total": object()}),
            {},
            "SUMMARY",
            id="unset-display-infers-form-by-default",
        ),
        # An author who explicitly writes `display: list` is never re-inferred,
        # even on an aggregate region the resolver would otherwise promote.
        pytest.param(
            _region(display="list", display_unset=False, aggregates={"total": object()}),
            {},
            "LIST",
            id="explicit-list-is-authoritative-even-with-aggregates",
        ),
        pytest.param(
            _region(
                display="auto",
                display_unset=False,
                group_by="status",
                aggregates={"n": object()},
            ),
            {},
            "BAR_CHART",
            id="explicit-auto-routes-through-resolver",
        ),
        pytest.param(
            _region(display="kanban", display_unset=False),
            {},
            "KANBAN",
            id="explicit-kanban-is-passed-through-unchanged",
        ),
        pytest.param(
            _region(display="list", display_unset=True, source="Plain"),
            {"Plain": _PLAIN},
            "LIST",
            id="unset-plain-entity-still-lists",
        ),
    ],
)
def test_resolve_region_display_mode(
    region: SimpleNamespace, entities: dict, expected: str
) -> None:
    """Default-flip decision table (#1492 level 2->3): unset/auto infer,
    explicit verbs are authoritative."""
    assert resolve_region_display_mode(region, entities) == expected
