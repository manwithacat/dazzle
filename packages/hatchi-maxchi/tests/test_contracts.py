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
