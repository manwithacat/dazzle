"""Load-bearing tests: each scanner function in contract_checker.py maps to
one or more tests here that prove the violation is unrepresentable at the
type level. When Phase 9 deletes the scanner, these tests are what stays."""

from collections.abc import Callable

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


@pytest.mark.parametrize(
    ("ctor", "exc", "match"),
    [
        # Replaces the find_nested_chromes scanner.
        pytest.param(
            lambda: Card(body=Card(body=Text("inner"))),
            CardSafetyError,
            "Card cannot directly contain another Card",
            id="card.card_in_body",
        ),
        pytest.param(
            lambda: Card(header=Card(body=Text("inner")), body=Text("body")),
            CardSafetyError,
            None,
            id="card.card_in_header",
        ),
        # A header is text-shaped; a Card-as-header re-introduces nested chrome.
        pytest.param(
            lambda: Surface(header=Card(body=Text("nested")), body=Text("body")),
            CardSafetyError,
            "header cannot be a Card",
            id="surface.card_as_header",
        ),
        # Region kind drives display behaviour; missing it is a static error.
        pytest.param(
            lambda: Region(body=Text("rows")),  # type: ignore[call-arg]
            TypeError,
            None,
            id="region.kind_missing",
        ),
        pytest.param(
            lambda: Region(kind="moonbeam", body=Text("body")),  # type: ignore[arg-type]
            ValueError,
            "invalid region kind",
            id="region.kind_invalid",
        ),
        pytest.param(
            lambda: Toolbar(),  # type: ignore[call-arg]
            TypeError,
            None,
            id="toolbar.label_missing",
        ),
        pytest.param(lambda: Tabs(tabs=()), ValueError, "at least one tab", id="tabs.empty"),
        pytest.param(
            lambda: Tabs(tabs=(("a", Text("1")), ("a", Text("2")))),
            ValueError,
            "duplicate tab key",
            id="tabs.duplicate_keys",
        ),
        pytest.param(
            lambda: Drawer(body=Text("body"), side="up"),  # type: ignore[arg-type]
            ValueError,
            "invalid side",
            id="drawer.side_invalid",
        ),
    ],
)
def test_rejects_invalid_construction(
    ctor: Callable[[], object], exc: type[Exception], match: str | None
) -> None:
    with pytest.raises(exc, match=match):
        ctor()


@pytest.mark.parametrize(
    ("ctor", "expected"),
    [
        pytest.param(lambda: Card(body=Text("c")), {"header": None, "footer": None}, id="card"),
        pytest.param(
            lambda: Surface(body=Text("c")), {"header": None, "footer": None}, id="surface"
        ),
        pytest.param(lambda: Toolbar(label="Actions"), {"actions": ()}, id="toolbar"),
        pytest.param(lambda: Drawer(body=Text("c")), {"side": "right"}, id="drawer"),
        pytest.param(lambda: Modal(body=Text("c")), {"size": "md"}, id="modal"),
    ],
)
def test_defaults(ctor: Callable[[], object], expected: dict[str, object]) -> None:
    obj = ctor()
    assert {key: getattr(obj, key) for key in expected} == expected


@pytest.mark.parametrize(
    "ctor",
    [
        # Replaces the find_duplicate_titles_in_cards scanner: the dashboard
        # slot owns titles, so a Region has no title field.
        pytest.param(lambda: Region(kind="list", body=Text("rows")), id="region"),
        # Surface's header IS its title slot; a title field would re-introduce
        # the duplicate-titles violation.
        pytest.param(lambda: Surface(body=Text("body")), id="surface"),
    ],
)
def test_has_no_title_field(ctor: Callable[[], object]) -> None:
    assert not hasattr(ctor(), "title")
