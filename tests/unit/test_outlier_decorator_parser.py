from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"
entity System "System":
  id: uuid pk
  name: str(40)
  response_time_ms: int

workspace ops "Ops":
  health:
    source: System
    display: list
    outlier_on: response_time_ms
    outlier_method: sigma:2
"""


def _region(name: str):
    *_, fragment = parse_dsl(_DSL, Path("t.dsl"))
    ws = fragment.workspaces[0]
    return next(r for r in ws.regions if r.name == name)


def test_parses_outlier_on_and_method() -> None:
    r = _region("health")
    assert r.outlier_on == "response_time_ms"
    assert r.outlier is not None
    assert r.outlier.method == "sigma" and r.outlier.sigma_k == 2.0
