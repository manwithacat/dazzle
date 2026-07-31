"""Fleet gate: state-machine list rows never put text chips in icon squares.

Humanqa postmortem (2026-07): transition *labels* shared ``.dz-tr-action`` with
icon-only chrome. Layout tests must cover every example appspec that has a
state machine **and** a list surface — not only a synthetic Ticket fixture.

For each (example, entity):
  1. Source transitions via ``list_state_transitions`` (same path as list HTMX).
  2. Render one row per distinct ``from_state`` that has outgoing edges.
  3. Assert every emitted transition control carries ``dz-tr-action dz-tr-transition``.
  4. Assert multi-word labels still use the chip class (would break 1.75rem squares).

CSS packing contracts remain in ``test_list_row_state_affordance.py``; this file
is the **fleet emitter** sweep.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.handlers.list_handlers import (
    build_data_table,
    list_state_transitions,
)
from dazzle.http.runtime.workspace_columns import (
    build_entity_columns,
    build_surface_columns,
)
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

_REPO = Path(__file__).resolve().parents[2]
_EXAMPLES = _REPO / "examples"

_CHIP_BTN = re.compile(
    r'<button[^>]*class="[^"]*dz-tr-action dz-tr-transition[^"]*"[^>]*>\s*([^<]+?)\s*</button>',
    re.I,
)


def _example_dirs() -> list[Path]:
    if not _EXAMPLES.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(_EXAMPLES.iterdir()):
        if not d.is_dir():
            continue
        if (d / "dazzle.toml").is_file() or (d / "dsl").is_dir():
            out.append(d)
    return out


def _sm_list_cases() -> list[tuple[str, str, object, object]]:
    """(example, entity_name, entity_spec, list_surface_or_None)."""
    cases: list[tuple[str, str, object, object]] = []
    for d in _example_dirs():
        try:
            spec = load_project_appspec(d)
        except Exception:
            continue
        ents = list(getattr(getattr(spec, "domain", None), "entities", None) or [])
        surfaces = list(getattr(spec, "surfaces", None) or [])
        list_by_entity: dict[str, object] = {}
        for s in surfaces:
            eref = getattr(s, "entity_ref", None)
            mode = getattr(s, "mode", None)
            mode_val = getattr(mode, "value", mode)
            if eref and str(mode_val).lower() == "list" and eref not in list_by_entity:
                list_by_entity[eref] = s
        for ent in ents:
            sm = getattr(ent, "state_machine", None)
            if not sm or not getattr(sm, "transitions", None):
                continue
            if ent.name not in list_by_entity:
                continue
            cases.append((d.name, ent.name, ent, list_by_entity[ent.name]))
    return cases


_CASES = _sm_list_cases()


def _columns_for(spec_enums: object, ent: object, list_surf: object) -> list[dict]:
    if list_surf is not None:
        cols = build_surface_columns(ent, list_surf, spec_enums)
        if cols:
            return cols
    return build_entity_columns(ent, spec_enums) or [{"key": "id", "label": "Id", "type": "text"}]


def _row_item(ent: object, status_field: str, status: str) -> dict:
    item: dict = {"id": "fleet-gate-1", status_field: status}
    # Satisfy first text-ish column so the row is non-empty
    for f in getattr(ent, "fields", None) or []:
        name = getattr(f, "name", None)
        if not name or name in ("id", status_field):
            continue
        kind = getattr(getattr(f, "type", None), "kind", None)
        kind_val = getattr(kind, "value", kind)
        if kind_val in ("str", "text"):
            item[name] = "Fleet gate"
            break
    return item


@pytest.mark.parametrize(
    ("example", "entity_name", "ent", "list_surf"),
    _CASES,
    ids=[f"{e}/{n}" for e, n, _, __ in _CASES] or ["no-sm-list-entities"],
)
def test_fleet_sm_list_row_transitions_use_chip_class(
    example: str, entity_name: str, ent: object, list_surf: object
) -> None:
    if not _CASES:
        pytest.skip("no example apps with SM + list surface")

    tx, status_field, endpoint = list_state_transitions(ent, entity_name)
    assert tx, f"{example}/{entity_name}: expected transitions from SM"
    assert status_field and endpoint

    # Reload enums from appspec for column builder
    d = _EXAMPLES / example
    spec = load_project_appspec(d)
    cols = _columns_for(spec.enums, ent, list_surf)
    # Ensure status field is present so gating has a value path
    if not any(c.get("key") == status_field for c in cols):
        cols = list(cols) + [{"key": status_field, "label": status_field, "type": "badge"}]

    from_states = sorted({t.from_state for t in tx})
    assert from_states

    for st in from_states:
        # Only states that have at least one outgoing edge produce chips
        outgoing = [t for t in tx if t.from_state == st]
        if not outgoing:
            continue
        item = _row_item(ent, status_field, st)
        table_dict = {
            "columns": cols,
            "entity_name": entity_name,
            "api_endpoint": endpoint,
            "state_transitions": tx,
            "status_field": status_field,
            "transition_endpoint": endpoint,
            "inline_editable": [],
            "bulk_actions": False,
        }
        html = render_data_table_rows(build_data_table(table_dict, [item]))
        chips = _CHIP_BTN.findall(html)
        assert chips, (
            f"{example}/{entity_name} status={st!r}: expected dz-tr-transition "
            f"chip(s) for {[t.to_state for t in outgoing]}; html snippet missing class"
        )
        expected_labels = {t.label for t in outgoing}
        got = {c.strip() for c in chips}
        # Every outgoing edge should appear as a labelled chip
        missing = expected_labels - got
        assert not missing, (
            f"{example}/{entity_name} status={st!r}: missing chip labels {missing}; got {got}"
        )
        # Multi-word labels are the packing footgun — require chip class (regex already)
        for lab in expected_labels:
            if " " in lab:
                assert re.search(
                    rf'class="dz-tr-action dz-tr-transition"[^>]*>\s*{re.escape(lab)}\s*<',
                    html,
                ), f"{example}/{entity_name}: multi-word {lab!r} not on chip button"


def test_fleet_sm_list_sweep_is_non_empty() -> None:
    """Guard: if examples lose all SM lists, the parametrized suite would no-op."""
    assert len(_CASES) >= 5, (
        f"expected several SM+list entities under examples/; found {len(_CASES)}: "
        f"{[(e, n) for e, n, _, __ in _CASES]}"
    )
