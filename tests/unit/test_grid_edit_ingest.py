"""#1573 class closure: the ONE ingestion boundary for grid-edit seams."""

import pytest

from dazzle.render.fragment.ingest import GridEditCell, edit_span_attrs

pytestmark = pytest.mark.gate


@pytest.mark.parametrize(
    "raw",
    [
        [{"value": "open", "label": "Open"}],
        [("open", "Open")],
        ["open"],  # the #1573 bare-string producer
    ],
)
def test_producer_shapes_normalise_to_pairs(raw) -> None:
    cell = GridEditCell(col="status", kind="select", value="open", label="Status", options=raw)
    assert cell.options in ([("open", "Open")], [("open", "open")])


def test_select_requires_options_and_others_forbid_them() -> None:
    with pytest.raises(ValueError):
        GridEditCell(col="s", kind="select", value="x", label="S")
    with pytest.raises(ValueError):
        GridEditCell(col="t", kind="text", value="x", label="T", options=[("a", "A")])


def test_edit_span_attrs_emits_the_contract_attributes() -> None:
    cell = GridEditCell(col="status", kind="select", value="o<p", label='S"x', options=["open"])
    attrs = edit_span_attrs(cell)
    assert 'data-dz-grid-edit="status"' in attrs
    assert 'data-dz-edit-kind="select"' in attrs
    assert "o&lt;p" in attrs and "&quot;" in attrs  # escaping holds
    assert "data-dz-edit-options=" in attrs


def test_non_select_omits_options_attr() -> None:
    attrs = edit_span_attrs(GridEditCell(col="t", kind="text", value="v", label="T"))
    assert "data-dz-edit-options" not in attrs
