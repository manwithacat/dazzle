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
