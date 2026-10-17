"""Fragment renderer ↔ bundle conformance gate (#1799).

Every ``dz-*`` class a typed Fragment primitive emits must have at least one
rule in the built bundle (``static/dist/dazzle.min.css``), or be a structural
class HaTchi-MaXchi declares rule-less on purpose (``SEMANTIC_ONLY`` in
``packages/hatchi-maxchi/build.py`` — HM owns the class vocabulary, ADR-0053).

The drift this pins: the renderer emitted ``dz-card__body``,
``dz-badge--variant-*``, ``dz-kpi__*`` and ``<table class="dz-table">`` while
the bundle styled ``dz-card-body``, ``dz-badge[data-dz-tone]``, nothing, and a
``.dz-table`` list-shell div — so a consumer composing Card / KPI / Badge /
Table got unstyled output and wrote ~75 lines of shims.

Each primitive renders its exhaustiveness sample, one variant per value of
every ``Literal`` / ``bool`` field (and of its token dataclass fields), plus
the richer samples below for slots the minimal sample leaves empty. The
Dazzle-side allowlist is deliberately empty: a class that should carry no
rule goes into HM's ``SEMANTIC_ONLY`` with its reason, where HM's own
``test_semantic_only_list_is_not_stale`` keeps it honest.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import re
import typing
from collections.abc import Iterator
from functools import cache
from pathlib import Path

import pytest

from dazzle.render.fragment import (
    KPI,
    URL,
    Card,
    CohortStripRegion,
    DayTimelineRegion,
    EntityCardRegion,
    Fragment,
    Slot,
    Table,
    Text,
)
from dazzle.render.fragment.primitives.data import (
    CohortStripCell,
    CohortStripLensTab,
    DayTimelineSlot,
    EntityCardSection,
)
from dazzle.render.fragment.renderer import FragmentRenderer
from tests.unit.render.fragment.test_fragment_exhaustiveness import _sample_for

_REPO = Path(__file__).resolve().parents[4]
_BUNDLE_CSS = _REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "dist" / "dazzle.min.css"
_HM_BUILD = _REPO / "packages" / "hatchi-maxchi" / "build.py"

_TOKENS_MODULE = "dazzle.render.fragment.tokens"
_CLASS_ATTR = re.compile(r'class="([^"]*)"')
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SELECTOR_CLASS = re.compile(r"\.(dz-[A-Za-z0-9_-]+)")


@cache
def _styled_classes() -> frozenset[str]:
    """Every `dz-*` class named in any selector of the built bundle."""
    css = _CSS_COMMENT.sub("", _BUNDLE_CSS.read_text(encoding="utf-8"))
    return frozenset(_SELECTOR_CLASS.findall(css))


@cache
def _semantic_only() -> frozenset[str]:
    spec = importlib.util.spec_from_file_location("_hm_build_conformance", _HM_BUILD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return frozenset(mod.SEMANTIC_ONLY)


def _rich_samples(ptype: type) -> tuple[object, ...]:
    """Samples that fill the slots `_sample_for` leaves empty."""
    if ptype is Card:
        return (Card(header=Text("h"), body=Text("b"), footer=Text("f")),)
    if ptype is KPI:
        return (KPI(label="k", value="1", delta="+1"),)
    if ptype is Table:
        return (
            Table(
                columns=("a",),
                rows=(("v",), ("w",)),
                row_links=("/x", None),
                bulk_select=True,
                row_ids=("1", "2"),
            ),
        )
    if ptype is CohortStripRegion:
        cells = tuple(
            CohortStripCell(
                member_id=str(i),
                member_name="Ada Lovelace",
                primary_value="72%",
                subtitle="Year 10",
                tone=tone,
                drill_url=drill,
                action_html="<span>act</span>",
            )
            for i, (tone, drill) in enumerate((("good", "/m/1"), ("warn", ""), ("bad", "/m/3")))
        )
        lenses = (
            CohortStripLensTab(id="a", label="A", is_active=True),
            CohortStripLensTab(id="b", label="B", is_active=False),
        )
        return (CohortStripRegion(region_name="c", endpoint=URL("/c"), lenses=lenses, cells=cells),)
    if ptype is DayTimelineRegion:
        slots = tuple(
            DayTimelineSlot(
                slot_id=str(i),
                label="Period",
                position=pos,
                body="<p>b</p>",
                drill_url=drill,
                action_html="<span>act</span>",
            )
            for i, (pos, drill) in enumerate((("before", ""), ("active", "/s/2"), ("after", "")))
        )
        return (DayTimelineRegion(region_name="d", slots=slots),)
    if ptype is EntityCardRegion:
        modes = ("halo", "flags", "mini_bars", "stamps", "thread_summary", "quick_actions")
        sections = tuple(
            EntityCardSection(
                section_id=m,
                label=m,
                mode=m,  # type: ignore[arg-type]
                body="<p>b</p>",
                column="sidebar" if i % 2 else "main",
            )
            for i, m in enumerate(modes)
        )
        return (EntityCardRegion(region_name="e", sections=sections, record_label="Ada"),)
    return ()


def _literal_values(hint: object) -> list[object]:
    if hint is bool:
        return [True, False]
    if typing.get_origin(hint) is typing.Literal:
        return list(typing.get_args(hint))
    values: list[object] = []
    for arg in typing.get_args(hint):
        if typing.get_origin(arg) is typing.Literal:
            values.extend(typing.get_args(arg))
        elif isinstance(arg, type) and arg.__module__ == _TOKENS_MODULE:
            # Token dataclasses (CardTokens …): vary each of their fields too.
            values.extend(_variants(arg()))
    return values


def _variants(obj: object) -> Iterator[object]:
    """`obj`, then one copy per value of each Literal / bool / token field."""
    yield obj
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        return
    hints = typing.get_type_hints(type(obj))
    for f in dataclasses.fields(obj):
        for value in _literal_values(hints.get(f.name)):
            try:
                yield dataclasses.replace(obj, **{f.name: value})
            except (TypeError, ValueError):
                continue  # a value this sample's other fields reject


def _rendered_classes(ptype: type) -> set[str]:
    renderer = FragmentRenderer()
    classes: set[str] = set()
    for sample in (_sample_for(ptype), *_rich_samples(ptype)):
        for variant in _variants(sample):
            html = renderer.render(variant)  # type: ignore[arg-type]
            for attr in _CLASS_ATTR.findall(html):
                classes.update(c for c in attr.split() if c.startswith("dz-"))
    return classes


@pytest.mark.parametrize(
    "ptype",
    [t for t in typing.get_args(Fragment) if t is not Slot],
    ids=lambda t: t.__name__,
)
def test_every_emitted_class_has_a_bundle_rule(ptype: type) -> None:
    unstyled = sorted(_rendered_classes(ptype) - _styled_classes() - _semantic_only())
    assert not unstyled, (
        f"{ptype.__name__} emits dz-* classes with no rule in dazzle.min.css: {unstyled}. "
        "Emit the HaTchi-MaXchi class for this part, style the class in "
        "packages/hatchi-maxchi/components/, or (only if it is a genuinely structural "
        "hook) add it to SEMANTIC_ONLY in packages/hatchi-maxchi/build.py with the reason "
        "— then rebuild the dist (scripts/build_dist.py)."
    )


def test_embedded_table_is_not_the_list_shell() -> None:
    """`.dz-table` is the grid's list-shell div (`display: flex`); a `<table>`
    carrying it loses column layout — the one drift a class-exists check
    cannot see, because the shell class does have rules."""
    html = FragmentRenderer().render(Table(columns=("a",), rows=(("v",),)))
    assert not re.search(r'<table[^>]*class="[^"]*\bdz-table\b(?!-)', html), html
