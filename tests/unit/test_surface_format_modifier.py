"""#1470 Phase 2 Task 4 — parse the `format:` trailing modifier on surface fields."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"

entity Invoice "Invoice":
  id: uuid pk
  amount: money required
  rate: float
  title: str(80)

surface invoices "Invoices":
  uses entity Invoice
  mode: list
  section main:
    field amount "Amount" format: currency:GBP
    field rate "Rate" format: percent
    field title "Title"
"""


def _elements() -> dict:
    *_, fragment = parse_dsl(_DSL, Path("test.dsl"))
    surf = next(s for s in fragment.surfaces if s.name == "invoices")
    return {el.field_name: el for sec in surf.sections for el in sec.elements}


def test_format_modifier_with_arg() -> None:
    els = _elements()
    assert els["amount"].format is not None
    assert els["amount"].format.kind == "currency"
    assert els["amount"].format.arg == "GBP"


def test_format_modifier_bare_kind() -> None:
    els = _elements()
    assert els["rate"].format is not None
    assert els["rate"].format.kind == "percent"
    assert els["rate"].format.arg is None


def test_field_without_format_is_none() -> None:
    els = _elements()
    assert els["title"].format is None


def test_format_threads_into_surface_columns() -> None:
    """#1470 Phase 2 Task 6: the parsed `format:` reaches the column dict the
    adapter consumes (format_kind / format_arg)."""
    from dazzle.http.runtime.workspace_columns import build_surface_columns

    *_, fragment = parse_dsl(_DSL, Path("test.dsl"))
    entity = next(e for e in fragment.entities if e.name == "Invoice")
    surface = next(s for s in fragment.surfaces if s.name == "invoices")
    cols = {c["key"]: c for c in build_surface_columns(entity, surface)}
    amount = cols.get("amount_minor") or cols.get("amount")
    assert amount is not None
    assert amount["format_kind"] == "currency"
    assert amount["format_arg"] == "GBP"
    # `title` has no format: → no format keys on its column
    assert "format_kind" not in cols["title"]
