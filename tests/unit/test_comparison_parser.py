from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"
entity Sale "Sale":
  id: uuid pk
  region: str(40)
  amount: decimal(12,2)

workspace ops "Ops":
  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
    rank_by: total
    order: asc
    outlier_method: sigma:2
"""

_DSL_THRESHOLD = """
module m
app a "A"
entity Sale "Sale":
  id: uuid pk
  region: str(40)
  amount: decimal(12,2)

workspace ops "Ops":
  league:
    source: Sale
    display: comparison
    group_by: region
    aggregate:
      total: sum(amount)
    rank_by: total
    outlier_method: threshold:low=90,high=120
"""


def _region(dsl: str, name: str):
    *_, fragment = parse_dsl(dsl, Path("t.dsl"))
    ws = fragment.workspaces[0]
    return next(r for r in ws.regions if r.name == name)


def test_parses_rank_order_outlier() -> None:
    r = _region(_DSL, "league")
    assert r.rank_by == "total"
    assert r.order == "asc"
    assert r.outlier is not None
    assert r.outlier.method == "sigma" and r.outlier.sigma_k == 2.0


def test_parses_threshold_outlier() -> None:
    r = _region(_DSL_THRESHOLD, "league")
    assert r.outlier is not None
    assert r.outlier.method == "threshold"
    assert r.outlier.threshold_low == 90.0
    assert r.outlier.threshold_high == 120.0
    assert r.order == "desc"  # default
