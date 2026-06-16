"""Exercises the `fixtures/tenant_hierarchy` worked example (ADR-0036 + ADR-0037).

Proves the committed worked example (a) validates clean and (b) compiles the
hierarchy-aware `current_tenant` scopes as documented — a depth-3 self-or-ancestor
disjunction on READ, a single leaf check on WRITE. The cross-tenant isolation
property is proven against real Postgres in
``tests/integration/test_current_tenant_scope_pg.py``.
"""

from __future__ import annotations

import glob
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_appspec

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "tenant_hierarchy"


def _appspec():
    dsls = [Path(p) for p in glob.glob(str(_FIXTURE / "dsl" / "*.dsl"))]
    return build_appspec(parse_modules(dsls), "tenant_hierarchy.core")


def _report(appspec):
    return next(e for e in appspec.domain.entities if e.name == "Report")


def _scope(appspec, op_suffix):
    return next(s for s in _report(appspec).access.scopes if str(s.operation).endswith(op_suffix))


def test_fixture_validates_clean() -> None:
    errors: list[str] = []
    for d in glob.glob(str(_FIXTURE / "dsl" / "*.dsl")):
        frag = parse_dsl(Path(d).read_text(), Path(d))[5]
        errors.extend(str(e) for e in validate_appspec(frag))
    assert errors == [], errors


def test_hierarchy_edges_parsed() -> None:
    appspec = _appspec()
    by_name = {e.name: e for e in appspec.domain.entities}
    assert by_name["Region"].tenant_host.parent is None  # root
    assert by_name["Trust"].tenant_host.parent == "region"
    assert by_name["School"].tenant_host.parent == "trust"
    assert by_name["Region"].membership is not None  # membership on the root only
    assert by_name["Trust"].membership is None
    assert by_name["School"].membership is None


def test_report_read_scope_expands_depth3_disjunction() -> None:
    pred = _scope(_appspec(), "read").predicate
    assert type(pred).__name__ == "BoolComposite"
    assert str(pred.op) == "or"
    legs = [
        (type(c).__name__, getattr(c, "field", None) or getattr(c, "path", None))
        for c in pred.children
    ]
    assert ("ColumnCheck", "school") in legs
    assert ("PathCheck", ["school", "trust"]) in legs
    assert ("PathCheck", ["school", "trust", "region"]) in legs


def test_report_write_scope_stays_single() -> None:
    pred = _scope(_appspec(), "update").predicate
    assert type(pred).__name__ == "ColumnCheck"
    assert pred.field == "school"
    assert pred.value.current_tenant is True
