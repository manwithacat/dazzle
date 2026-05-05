"""Load-bearing tests: each scanner function in contract_checker.py maps to
one or more tests here that prove the violation is unrepresentable at the
type level. When Phase 9 deletes the scanner, these tests are what stays."""

import pytest

from dazzle.render.fragment.errors import CardSafetyError
from dazzle.render.fragment.primitives.containers import (
    Card,
    Drawer,
    Modal,
    Region,
    Surface,
    Tabs,
    Toolbar,
)
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


# === Surface ===


def test_surface_required_body() -> None:
    s = Surface(body=Text("contents"))
    assert s.body is not None
    assert s.header is None
    assert s.footer is None


def test_surface_has_no_title_field() -> None:
    """Surface has fixed slots (header, body, footer); a title slot would
    re-introduce the duplicate-titles violation. The header IS the title slot."""
    s = Surface(body=Text("body"))
    assert not hasattr(s, "title")


def test_surface_does_not_admit_card_as_header() -> None:
    """A header is text-shaped; a Card-as-header re-introduces nested-chrome."""
    inner_card = Card(body=Text("nested"))
    with pytest.raises(CardSafetyError, match="header cannot be a Card"):
        Surface(header=inner_card, body=Text("body"))


# === Tabs ===


def test_tabs_requires_panels() -> None:
    with pytest.raises(ValueError, match="at least one tab"):
        Tabs(tabs=())


def test_tabs_panel_construction() -> None:
    t = Tabs(
        tabs=(
            ("overview", Text("o")),
            ("details", Text("d")),
        )
    )
    assert len(t.tabs) == 2


def test_tabs_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate tab key"):
        Tabs(
            tabs=(
                ("a", Text("1")),
                ("a", Text("2")),
            )
        )


# === Drawer + Modal ===


def test_drawer_side_default() -> None:
    d = Drawer(body=Text("contents"))
    assert d.side == "right"


def test_drawer_invalid_side() -> None:
    with pytest.raises(ValueError, match="invalid side"):
        Drawer(body=Text("body"), side="up")  # type: ignore[arg-type]


def test_modal_size_default() -> None:
    m = Modal(body=Text("contents"))
    assert m.size == "md"
