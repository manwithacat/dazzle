"""#1558 (3c): regular list rows offer only the transitions valid from that
row's current state, in the row actions cell.

## Postmortem (humanqa 2026-07 — actions column)

**Adverse outcome:** state-transition *labels* (e.g. "In Progress", "Review")
were emitted as ``class="dz-tr-action dz-tr-transition"`` but CSS treated all
``.dz-tr-action`` as **fixed 1.75rem icon squares** inside a **4rem** chrome
column. Text stacked/overflowed; the column looked unstyled and broken.

**Why it shipped:** two orthogonal contracts collided without a joint test —

1. **Chrome contract** — actions cell is icon strip (view/edit/delete SVG),
   header was ``visually-hidden``, column width ~4rem.
2. **#1558 affordance contract** — valid SM transitions are offered *in that
   same cell* as **text labels**, not icons.

Gating tests only checked *which* transitions appeared (label text + hx-put),
not *layout class* or *CSS chip treatment*. This module now pins both.

**Deterministic fleet gate:** transition buttons MUST carry ``dz-tr-transition``
and CSS MUST give that class ``width: auto`` (not the icon square alone).

**Layering note:** these checks are *emitter/source shape* (regex over HTML/CSS
source). They do **not** prove header↔chip alignment in the browser. For
**layout concordance** (bounding boxes / computed style), see
``test_actions_column_geometry.py`` — that is the class of test that would have
caught left-stacked chips under a right-aligned ACTIONS title.
"""

from __future__ import annotations

import re
from pathlib import Path

from dazzle.render.context import TransitionContext
from dazzle.render.fragment.renderer._data_row import _render_table_row

_REPO = Path(__file__).resolve().parents[2]
_TABLE_CSS = _REPO / "packages" / "hatchi-maxchi" / "components" / "table.css"


def _t(frm, to):
    # Label formatting mirrors the compile build: action intent, not bare status.
    from dazzle.render.fragment.state_affordance import transition_action_label

    return TransitionContext(
        from_state=frm,
        to_state=to,
        label=transition_action_label(to),
        api_url="/api/tickets/{id}",
    )


def _table(**over):
    base = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Ticket",
        "state_transitions": (_t("open", "in_progress"), _t("in_progress", "resolved")),
        "status_field": "status",
        "transition_endpoint": "/api/tickets",
    }
    base.update(over)
    return base


def test_row_shows_only_current_state_transitions():
    html = _render_table_row(_table(), {"id": "1", "title": "T", "status": "open"})
    assert "Set to In Progress" in html  # open -> in_progress valid from open
    assert "Set to Resolved" not in html  # in_progress -> resolved NOT valid from open
    assert 'hx-put="/api/tickets/1"' in html


def test_row_in_later_state_shows_its_transitions():
    html = _render_table_row(_table(), {"id": "9", "title": "T", "status": "in_progress"})
    assert "Set to Resolved" in html
    assert "Set to In Progress" not in html


def test_row_without_state_machine_has_no_transition_buttons():
    html = _render_table_row(
        {"columns": [{"key": "title", "label": "Title", "type": "text"}], "entity_name": "Ticket"},
        {"id": "1", "title": "T", "status": "open"},
    )
    assert "hx-put" not in html  # byte-identical: no state transitions rendered


def test_unknown_state_shows_no_transitions():
    html = _render_table_row(_table(), {"id": "1", "title": "T", "status": ""})
    assert "hx-put" not in html


# ── Layout / chrome contracts (would have failed the adverse iteration) ───


def test_transition_buttons_carry_chip_class_not_icon_only():
    """Text transitions must opt into .dz-tr-transition (chip), not bare icon square."""
    html = _render_table_row(_table(), {"id": "1", "title": "T", "status": "open"})
    # Multi-word action label that cannot fit a 1.75rem square without stacking
    assert "Set to In Progress" in html
    assert re.search(
        r'class="dz-tr-action dz-tr-transition"[^>]*>\s*Set to In Progress\s*<',
        html,
    ), html
    # Action-intent label must not read as bare live status alone
    assert ">Active<" not in html


def test_transition_css_chip_is_not_fixed_icon_square():
    """CSS must size .dz-tr-transition as a label chip (width:auto), not 1.75rem."""
    css = _TABLE_CSS.read_text(encoding="utf-8")
    assert ".dz-tr-action.dz-tr-transition" in css or re.search(
        r"\.dz-tr-action\.dz-tr-transition|\.dz-tr-transition\s*\{",
        css,
    )
    # Extract the transition rule block(s)
    blocks = re.findall(
        r"\.dz-tr-action\.dz-tr-transition\s*\{([^}]+)\}",
        css,
        flags=re.S,
    )
    assert blocks, "missing .dz-tr-action.dz-tr-transition { … } rule in table.css"
    body = "\n".join(blocks)
    assert re.search(r"width\s*:\s*auto\b", body), (
        "transition chips must set width:auto so multi-word labels do not stack "
        f"in the icon square; got:\n{body}"
    )
    # Must not re-assert the icon square size on the chip rule
    assert not re.search(r"width\s*:\s*1\.75rem\b", body), body


def test_actions_column_css_wider_than_icon_strip():
    """Actions chrome must reserve room for chips + icons (not 4rem only)."""
    css = _TABLE_CSS.read_text(encoding="utf-8")
    # th-actions width should be clearly > 4rem after the fix
    m = re.search(
        r"\.dz-table-th-actions[^{]*\{([^}]+)\}",
        css,
        flags=re.S,
    )
    assert m, "missing .dz-table-th-actions rule"
    th_body = m.group(1)
    # Accept rem widths >= 7
    widths = [float(x) for x in re.findall(r"width\s*:\s*([\d.]+)rem", th_body)]
    assert widths and max(widths) >= 7.0, (
        f"actions header width too narrow for text chips: {th_body!r}"
    )


def test_actions_header_is_visible_not_sr_only():
    """With text transitions, Actions header must be visible chrome (not only SR)."""
    src = (
        _REPO / "src" / "dazzle" / "render" / "fragment" / "renderer" / "_render_tables.py"
    ).read_text(encoding="utf-8")
    assert "dz-table-th-actions" in src
    # Emission is split across string literals: ...th-actions">' + "Actions</th>"
    assert '"Actions</th>"' in src or "'Actions</th>'" in src or "Actions</th>" in src
    assert 'visually-hidden">Actions' not in src
    assert "visually-hidden'>Actions" not in src


def test_actions_header_and_cell_share_end_alignment():
    """Header title and chips must share text-align/end justification (humanqa)."""
    css = _TABLE_CSS.read_text(encoding="utf-8")
    for sel in (".dz-table-th-actions", ".dz-tr-actions-cell"):
        m = re.search(re.escape(sel) + r"[^{]*\{([^}]+)\}", css, flags=re.S)
        assert m, f"missing rule for {sel}"
        body = m.group(1)
        assert re.search(r"text-align\s*:\s*end\b", body) or re.search(
            r"text-align\s*:\s*right\b", body
        ), f"{sel} must end-align: {body!r}"
    # Chip strip: full-width flex-end (not shrink-to-content inline-flex)
    m = re.search(r"\.dz-tr-actions\s*\{([^}]+)\}", css, flags=re.S)
    assert m, "missing .dz-tr-actions rule"
    body = m.group(1)
    assert re.search(r"justify-content\s*:\s*flex-end\b", body), body
    assert re.search(r"display\s*:\s*flex\b", body), body
    assert re.search(r"width\s*:\s*100%", body), body


# ── sourcing + end-to-end (build_data_table -> render) ──────────────────────

from types import SimpleNamespace  # noqa: E402

from dazzle.core.strings import to_api_plural  # noqa: E402
from dazzle.http.runtime.handlers.list_handlers import (  # noqa: E402
    build_data_table,
    list_state_transitions,
)
from dazzle.render.fragment.renderer._data_row import render_data_table_rows  # noqa: E402


def _entity_with_sm():
    sm = SimpleNamespace(
        status_field="status",
        transitions=[
            SimpleNamespace(from_state="open", to_state="in_progress"),
            SimpleNamespace(from_state="in_progress", to_state="resolved"),
        ],
    )
    return SimpleNamespace(state_machine=sm, name="Ticket")


def test_list_state_transitions_sources_with_from_state():
    tx, sf, ep = list_state_transitions(_entity_with_sm(), "Ticket")
    assert sf == "status"
    assert ep == f"/{to_api_plural('Ticket')}"
    assert [(t.from_state, t.to_state) for t in tx] == [
        ("open", "in_progress"),
        ("in_progress", "resolved"),
    ]


def test_list_state_transitions_no_state_machine():
    assert list_state_transitions(SimpleNamespace(state_machine=None), "X") == ((), "", "")


def test_build_data_table_to_rows_end_to_end():
    tx, sf, ep = list_state_transitions(_entity_with_sm(), "Ticket")
    table_dict = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Ticket",
        "state_transitions": tx,
        "status_field": sf,
        "transition_endpoint": ep,
    }
    dt = build_data_table(table_dict, [{"id": "7", "title": "T", "status": "open"}])
    html = render_data_table_rows(dt)
    assert "Set to In Progress" in html and "Set to Resolved" not in html
    assert f'hx-put="{ep}/7"' in html
