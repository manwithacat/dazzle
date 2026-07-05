"""Byte anchors for the folded `embedded` + `list-region` row archetypes (#1511).

Phase 3 of the list-render convergence (design
`docs/superpowers/specs/2026-06-28-list-render-convergence-design.md` §3) folds
`_emit_table` (embedded) and `_emit_list_region` (region) onto the one shared
`assemble_list_row` seam. The data-table archetype is pinned byte-for-byte by
`test_data_row_characterization_1505.py`; these tests are the equivalent anchors
for the two archetypes that gained the `data-dz-list-kind` marker + the
converged clickable-row drill in Phase 3, so an accidental attribute / class /
cell-order regression in the seam is caught for them too.

The cell *content* is deliberately trivial (single-char values, a literal action
button) so the assertions pin the row *skeleton* the seam owns, not the
per-archetype cell rendering.
"""

import re

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import ListColumn, ListRegion, Table
from dazzle.render.fragment.renderer import FragmentRenderer


def _body_rows(html: str) -> list[str]:
    """The `<tbody>` `<tr>…</tr>` rows (drops the `<thead>` header row)."""
    tbody = re.search(r"<tbody>(.*)</tbody>", html, re.DOTALL)
    inner = tbody.group(1) if tbody else html
    return re.findall(r"<tr\b.*?</tr>", inner, re.DOTALL)


def _render(emit_name: str, fragment: object) -> list[str]:
    r = FragmentRenderer()
    return _body_rows(getattr(r, emit_name)(fragment, RenderContext()))


class TestEmbeddedArchetype:
    """`_emit_table` → `data-dz-list-kind="embedded"`, `dz-table__row`."""

    def test_plain_row(self) -> None:
        rows = _render("_emit_table", Table(columns=("Name", "Age"), rows=(("Ada", "36"),)))
        assert rows == [
            '<tr data-dz-list-kind="embedded" class="dz-table__row"><td>Ada</td><td>36</td></tr>'
        ]

    def test_linked_row_owns_the_drill(self) -> None:
        rows = _render(
            "_emit_table",
            Table(columns=("Name",), rows=(("Ada",),), row_links=("/x/1",)),
        )
        assert rows == [
            '<tr data-dz-list-kind="embedded" '
            'class="dz-table__row dz-table__row--linked" '
            'hx-get="/x/1" hx-push-url="true" hx-trigger="click" '
            'hx-preload="mouseover" hx-target="body" hx-swap="innerHTML" tabindex="0">'
            "<td>Ada</td></tr>"
        ]

    def test_bulk_select_row_carries_id_and_checkbox(self) -> None:
        rows = _render(
            "_emit_table",
            Table(
                columns=("Name",),
                rows=(("Ada",),),
                bulk_select=True,
                row_ids=("id1",),
            ),
        )
        # Row id precedes the marker; the checkbox cell stops propagation.
        # Convergence C0a: an identified row also carries the stable morph-key
        # `id` (`dz-grid-row-<id>`, the HM grid contract) so a live selection
        # follows its row across an idiomorph re-sort/paginate.
        assert rows[0].startswith(
            '<tr id="dz-grid-row-id1" data-dz-row-id="id1" data-dz-list-kind="embedded" '
            'class="dz-table__row"><td class="dz-tr-checkbox-cell" '
            'onclick="event.stopPropagation()">'
        )
        assert rows[0].endswith("<td>Ada</td></tr>")


class TestListRegionArchetype:
    """`_emit_list_region` → `data-dz-list-kind="region"`, `dz-list-row`."""

    def _col(self) -> tuple[ListColumn, ...]:
        return (ListColumn(key="name", label="Name"),)

    def test_plain_row_keeps_legacy_trailing_space(self) -> None:
        rows = _render(
            "_emit_list_region",
            ListRegion(columns=self._col(), rows=(("Ada",),), total=1),
        )
        assert rows == ['<tr data-dz-list-kind="region" class="dz-list-row "><td>Ada</td></tr>']

    def test_linked_row_owns_the_drill(self) -> None:
        rows = _render(
            "_emit_list_region",
            ListRegion(columns=self._col(), rows=(("Ada",),), row_links=("/y/1",), total=1),
        )
        assert rows == [
            '<tr data-dz-list-kind="region" class="dz-list-row is-clickable" '
            'hx-get="/y/1" hx-push-url="true" hx-trigger="click" '
            'hx-preload="mouseover" hx-target="body" hx-swap="innerHTML" tabindex="0">'
            "<td>Ada</td></tr>"
        ]

    def test_action_cell_stops_propagation(self) -> None:
        rows = _render(
            "_emit_list_region",
            ListRegion(
                columns=self._col(),
                rows=(("Ada",),),
                row_action_label="Go",
                row_actions=("<button>Go</button>",),
                total=1,
            ),
        )
        assert rows == [
            '<tr data-dz-list-kind="region" class="dz-list-row "><td>Ada</td>'
            '<td class="dz-list-row-action" onclick="event.stopPropagation()">'
            "<button>Go</button></td></tr>"
        ]

    def test_drill_and_action_compose_without_entanglement(self) -> None:
        # The §3.2 orthogonality invariant: the row owns the bare-click drill
        # AND the action cell stops propagation, so they never co-fire.
        rows = _render(
            "_emit_list_region",
            ListRegion(
                columns=self._col(),
                rows=(("Ada",),),
                row_links=("/y/1",),
                row_action_label="Go",
                row_actions=("<button>Go</button>",),
                total=1,
            ),
        )
        assert rows == [
            '<tr data-dz-list-kind="region" class="dz-list-row is-clickable" '
            'hx-get="/y/1" hx-push-url="true" hx-trigger="click" '
            'hx-preload="mouseover" hx-target="body" hx-swap="innerHTML" tabindex="0">'
            "<td>Ada</td>"
            '<td class="dz-list-row-action" onclick="event.stopPropagation()">'
            "<button>Go</button></td></tr>"
        ]

    def test_hidden_action_keeps_arity_with_empty_cell(self) -> None:
        # #1148: a hidden action ("" in row_actions) still emits the cell so the
        # column count matches the `<thead>` action column.
        rows = _render(
            "_emit_list_region",
            ListRegion(
                columns=self._col(),
                rows=(("Ada",),),
                row_action_label="Go",
                row_actions=("",),
                total=1,
            ),
        )
        assert rows[0].endswith(
            '<td class="dz-list-row-action" onclick="event.stopPropagation()"></td></tr>'
        )
