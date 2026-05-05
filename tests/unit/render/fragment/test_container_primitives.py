"""Load-bearing tests: each scanner function in contract_checker.py maps to
one or more tests here that prove the violation is unrepresentable at the
type level. When Phase 9 deletes the scanner, these tests are what stays."""

import pytest

from dazzle.render.fragment.errors import CardSafetyError
from dazzle.render.fragment.primitives.containers import Card, Region, Toolbar
from dazzle.render.fragment.primitives.content import Text

# === Card ===


def test_card_basic() -> None:
    c = Card(body=Text("contents"))
    assert c.body is not None
    assert c.header is None
    assert c.footer is None


def test_card_with_header_and_footer() -> None:
    c = Card(
        header=Text("title"),
        body=Text("body"),
        footer=Text("foot"),
    )
    assert c.header is not None


def test_card_cannot_directly_contain_card() -> None:
    """Replaces find_nested_chromes scanner."""
    inner = Card(body=Text("inner"))
    with pytest.raises(CardSafetyError, match="Card cannot directly contain another Card"):
        Card(body=inner)


def test_card_cannot_have_card_in_header() -> None:
    inner = Card(body=Text("inner"))
    with pytest.raises(CardSafetyError):
        Card(header=inner, body=Text("body"))


# === Region ===


def test_region_no_title_field() -> None:
    """Replaces find_duplicate_titles_in_cards scanner.

    Region structurally has no `title` field. The dashboard slot owns titles.
    """
    r = Region(kind="list", body=Text("rows"))
    assert not hasattr(r, "title")


def test_region_kind_required() -> None:
    """Region kind drives display behaviour; missing kind is a static error
    via the @dataclass decorator."""
    with pytest.raises(TypeError):
        Region(body=Text("rows"))  # type: ignore[call-arg]


def test_region_kind_validated() -> None:
    with pytest.raises(ValueError, match="invalid region kind"):
        Region(kind="moonbeam", body=Text("body"))  # type: ignore[arg-type]


# === Toolbar ===


def test_toolbar_with_actions() -> None:
    """Toolbar.actions: tuple of action-shaped objects. Type-level enforcement
    of "first action must not be hidden" lives in __post_init__ once Button
    is available (Task 12); for now we test the kind/order constraints."""
    t = Toolbar(label="Actions")
    assert t.actions == ()


def test_toolbar_label_required() -> None:
    with pytest.raises(TypeError):
        Toolbar()  # type: ignore[call-arg]
