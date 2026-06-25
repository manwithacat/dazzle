from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"
entity System "System":
  id: uuid pk
  name: str(40)
  error_rate: decimal(5,2)

workspace ops "Ops":
  health:
    source: System
    display: list
    rag_on: error_rate
    tone_bands:
      - at: 5
        tone: destructive
      - at: 1
        tone: warning
      - at: 0
        tone: positive
"""


def _region(name: str):
    *_, fragment = parse_dsl(_DSL, Path("t.dsl"))
    return next(r for r in fragment.workspaces[0].regions if r.name == name)


def test_parses_rag_on_and_bands() -> None:
    r = _region("health")
    assert r.rag_on == "error_rate"
    assert [(b.at, b.tone) for b in r.tone_bands] == [
        (5.0, "destructive"),
        (1.0, "warning"),
        (0.0, "positive"),
    ]
