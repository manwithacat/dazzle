"""Regression guard for #1189.

The `EventSpec.version` IR field exists with default ``"1.0"`` but the parser
ignored a ``version:`` declaration in the DSL — the field never wired up to
DSL input. This test pins the parse path: a ``version: "X.Y"`` line on an
``event`` becomes ``event.version == "X.Y"``; the default is still ``"1.0"``.

Breaking-change detection across versions (the harder half of #1189) needs
schema history / diffing and is left for a future design.
"""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_WITH_VERSION = """\
module t

event_model:
  event OrderCreated:
    topic: orders
    version: "2.1"
    fields:
      order_id: uuid required
"""

_WITHOUT_VERSION = """\
module t

event_model:
  event OrderCreated:
    topic: orders
    fields:
      order_id: uuid required
"""


def _events(text: str) -> list:
    _, _, _, _, _, fragment = parse_dsl(text, Path("test.dsl"))
    assert fragment.event_model is not None
    return fragment.event_model.events


def test_event_version_parses_from_dsl() -> None:
    events = _events(_WITH_VERSION)
    assert events, "expected at least one event"
    assert events[0].name == "OrderCreated"
    assert events[0].version == "2.1"


def test_event_version_defaults_to_1_0_when_omitted() -> None:
    events = _events(_WITHOUT_VERSION)
    assert events[0].version == "1.0"
