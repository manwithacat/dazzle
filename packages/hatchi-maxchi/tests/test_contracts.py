"""Contract-module gates: every exemplar renders DOM conforming to its
own DOM_CONTRACT (spec 2026-07-10-hyperpart-contract-modules-design)."""

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

from contracts._kit import DomContract, JsonPairs, Node, OneOf, Present, validate_dom  # noqa: E402

_CONTRACT = DomContract(
    part="t",
    root="[data-x]",
    nodes=(
        Node(
            "[data-cell]",
            attrs={
                "data-kind": OneOf("a", "b"),
                "data-val": Present(),
                "data-opts": JsonPairs(required_when={"data-kind": "b"}),
            },
        ),
    ),
)


def test_validate_dom_accepts_conforming_fragment() -> None:
    html = (
        '<div data-x="1"><span data-cell data-kind="b" data-val="v" '
        'data-opts=\'[["x","X"]]\'>v</span></div>'
    )
    assert validate_dom(html, _CONTRACT) == []


def test_validate_dom_flags_bad_enum_missing_attr_and_bad_json() -> None:
    html = (
        '<div data-x="1">'
        '<span data-cell data-kind="z" data-val="v">v</span>'
        '<span data-cell data-kind="a">v</span>'
        '<span data-cell data-kind="b" data-val="v" data-opts="nope">v</span>'
        "</div>"
    )
    violations = validate_dom(html, _CONTRACT)
    assert len(violations) == 3
    assert any("data-kind" in v for v in violations)
    assert any("data-val" in v for v in violations)
    assert any("data-opts" in v for v in violations)


def test_validate_dom_missing_root_and_fragment_mode() -> None:
    html = '<span data-cell data-kind="a" data-val="v">v</span>'
    assert any("root" in v for v in validate_dom(html, _CONTRACT))
    assert validate_dom(html, _CONTRACT, require_root=False) == []


# ── Contract-module sweep ────────────────────────────────────────────

import importlib  # noqa: E402
import pkgutil  # noqa: E402

import contracts  # noqa: E402
import pytest  # noqa: E402


def _contract_modules():
    for m in pkgutil.iter_modules(contracts.__path__):
        if not m.name.startswith("_"):
            yield importlib.import_module(f"contracts.{m.name}")


def test_every_contract_module_has_the_required_surface() -> None:
    mods = list(_contract_modules())
    assert mods, "no contract modules found"
    for mod in mods:
        assert hasattr(mod, "DOM_CONTRACT"), f"{mod.__name__}: missing DOM_CONTRACT"


def test_exemplars_render_conforming_dom() -> None:
    """The core loop: every exemplar payload, rendered by the module's own
    render(), must satisfy the module's own DOM_CONTRACT."""
    checked = 0
    for mod in _contract_modules():
        exemplars = getattr(mod, "EXEMPLARS", None)
        render = getattr(mod, "render", None)
        if exemplars is None or render is None:
            continue  # root-only contracts (grid.py) have no ingestion side
        for ex in exemplars:
            html = render(ex)
            violations = validate_dom(html, mod.DOM_CONTRACT, require_root=False)
            assert not violations, f"{mod.__name__}: {violations}"
            checked += 1
    assert checked >= 3, "exemplar sweep is not exercising the #1573 shapes"


def test_grid_edit_normalises_the_1573_producer_shapes() -> None:
    from contracts.grid_edit import GridEditCell

    for raw in (
        [{"value": "open", "label": "Open"}, {"value": "closed", "label": "Closed"}],
        [("open", "Open"), ("closed", "Closed")],
        ["open", "closed"],  # the #1573 bare-string shape
    ):
        cell = GridEditCell(col="status", kind="select", value="open", label="Status", options=raw)
        assert cell.options is not None and all(
            isinstance(p, tuple) and len(p) == 2 for p in cell.options
        )

    with pytest.raises(ValueError):
        GridEditCell(col="status", kind="select", value="x", label="S")  # select w/o options
    with pytest.raises(ValueError):
        GridEditCell(col="t", kind="text", value="x", label="T", options=[("a", "A")])
