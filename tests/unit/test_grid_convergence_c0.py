"""C0a of the HM `grid` convergence (dev_docs/2026-07-05-grid-convergence-plan.md):
additive server-contract attributes, no UI flip.

- Every bulk-selectable row carries a stable ``id="dz-grid-row-<row-id>"`` — the
  idiomorph MORPH KEY the primitive's selection contract rides on (a live
  selection follows its ROW across a re-sort/paginate). ``data-dz-row-id`` stays
  the payload anchor; the id encodes it so the two agree.
- Both pagination footers stamp ``data-dz-grid-total`` — the server-authoritative
  matched total the primitive's all-matching affordance + selection count read.
"""

from dazzle.http.runtime.htmx_render import _render_table_pagination
from dazzle.render.fragment import URL, FragmentRenderer, Pagination
from dazzle.render.fragment.renderer._data_row import (
    ARCHETYPE_DATA_TABLE,
    assemble_list_row,
)


class TestRowMorphKey:
    def test_row_with_row_id_gains_grid_morph_key(self) -> None:
        html = assemble_list_row(
            archetype=ARCHETYPE_DATA_TABLE,
            cells_html="<td>x</td>",
            row_id_attr="abc-123",
        )
        assert 'id="dz-grid-row-abc-123"' in html, (
            "a row with a row-id needs the stable morph-key id (grid contract)"
        )
        assert 'data-dz-row-id="abc-123"' in html, "the payload anchor stays"

    def test_explicit_dom_id_wins_over_derived_morph_key(self) -> None:
        html = assemble_list_row(
            archetype=ARCHETYPE_DATA_TABLE,
            cells_html="<td>x</td>",
            row_id_attr="abc-123",
            dom_id="my-anchor",
        )
        assert 'id="my-anchor"' in html
        assert "dz-grid-row-" not in html, "an explicit dom_id is already a morph key"

    def test_row_without_row_id_gets_no_id(self) -> None:
        html = assemble_list_row(
            archetype=ARCHETYPE_DATA_TABLE,
            cells_html="<td>x</td>",
        )
        assert "id=" not in html.split(">", 1)[0], "no row-id → no derived id"


class TestPaginationTotalStamp:
    _TABLE = {
        "total": 42,
        "page_size": 10,
        "page": 2,
        "table_id": "dt-widgets",
        "api_endpoint": "/api/widgets",
    }

    def test_htmx_table_pagination_carries_total(self) -> None:
        html = _render_table_pagination(self._TABLE)
        assert 'data-dz-grid-total="42"' in html, (
            "the footer must stamp the matched total (grid all-matching contract)"
        )

    def test_fragment_pagination_carries_total(self) -> None:
        p = Pagination(
            endpoint=URL("/api/widgets"),
            region_name="widgets",
            page=1,
            page_size=10,
            total=42,
        )
        html = FragmentRenderer().render(p)
        assert 'data-dz-grid-total="42"' in html
