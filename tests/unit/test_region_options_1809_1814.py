"""#1809 / #1814 (AegisMark): region presentation options.

* ``filters: none``  — a list region hides its filter/search bar.
* ``exclude: <region>`` — omit rows a sibling region shows on its first page.
* ``eager: true|false`` — override the default fold per region.
* ``limit:`` on ``display: comparison`` — top-N after ranking, in the one SQL.

Parse + validate + render through the public path; the live-Postgres proof of
``filters:`` / ``exclude:`` / comparison ``limit:`` is
``tests/integration/test_region_options_pg.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.http.runtime.aggregate import Dimension, build_aggregate_sql
from dazzle.http.runtime.query_builder import FilterOperator, QueryBuilder
from dazzle.http.runtime.workspace_region_computes import build_comparison_inputs
from dazzle.page.runtime.workspace_renderer import (
    build_workspace_context,
    render_workspace_content_typed,
)

_HEAD = """module t
app t "T"

entity Stack "Stack":
  id: uuid pk
  title: str(200) required
  status: enum[draft, marked]=draft

entity Note "Note":
  id: uuid pk
  body: str(200) required
"""


def _appspec(text: str) -> ir.AppSpec:
    *_, fragment = parse_dsl(text, Path("t.dsl"))
    module = ir.ModuleIR(name="t", file=Path("t.dsl"), fragment=fragment)
    return build_appspec([module], "t")


def _desk(*regions: str) -> str:
    return _HEAD + '\nworkspace desk "Desk":\n' + "".join(regions)


_RESUME = "  resume:\n    source: Stack\n    display: list\n    limit: 1\n"


def test_options_parse_into_the_region_ir() -> None:
    spec = _appspec(
        _desk(
            _RESUME,
            "  recent:\n    source: Stack\n    display: list\n"
            "    filters: none\n    exclude: resume\n    eager: true\n",
            "  later:\n    source: Stack\n    display: list\n    eager: false\n",
        )
    )
    resume, recent, later = spec.workspaces[0].regions
    assert (resume.filters_hidden, resume.exclude, resume.eager) == (False, None, None)
    assert (recent.filters_hidden, recent.exclude, recent.eager) == (True, "resume", True)
    assert later.eager is False


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("filters: some", "Expected 'none'"),
        ("eager: maybe", "eager must be 'true' or 'false'"),
    ],
)
def test_option_grammar_rejects_bad_values(snippet: str, message: str) -> None:
    text = _desk(f"  r:\n    source: Stack\n    {snippet}\n")
    with pytest.raises(ParseError, match=message):
        parse_dsl(text, Path("t.dsl"))


@pytest.mark.parametrize(
    ("recent_body", "extra_regions", "code"),
    [
        ("exclude: ghost", "", "E_EXCLUDE_UNKNOWN_REGION"),
        ("exclude: recent", "", "E_EXCLUDE_SELF"),
        ("exclude: notes", "  notes:\n    source: Note\n    display: list\n", "E_EXCLUDE_ENTITY"),
        (
            "exclude: pulse",
            "  pulse:\n    source: Stack\n    display: metrics\n",
            "E_EXCLUDE_DISPLAY",
        ),
    ],
)
def test_validator_rejects_bad_exclude(recent_body: str, extra_regions: str, code: str) -> None:
    text = _desk(
        _RESUME,
        f"  recent:\n    source: Stack\n    display: list\n    {recent_body}\n",
        extra_regions,
    )
    errors, _warnings, _ = lint_appspec(_appspec(text))
    assert any(code in e for e in errors), errors


def test_validator_rejects_an_exclude_cycle() -> None:
    text = _desk(
        "  a:\n    source: Stack\n    display: list\n    exclude: b\n",
        "  b:\n    source: Stack\n    display: list\n    exclude: a\n",
    )
    errors, _warnings, _ = lint_appspec(_appspec(text))
    assert any("E_EXCLUDE_CYCLE" in e for e in errors), errors


def test_valid_options_lint_clean() -> None:
    text = _desk(
        _RESUME,
        "  recent:\n    source: Stack\n    display: list\n    filters: none\n    exclude: resume\n",
    )
    errors, _warnings, _ = lint_appspec(_appspec(text))
    assert not [e for e in errors if "EXCLUDE" in e or "filters" in e], errors


def test_filters_none_on_a_non_list_display_warns() -> None:
    text = _desk("  pulse:\n    source: Stack\n    display: metrics\n    filters: none\n")
    _errors, warnings, _ = lint_appspec(_appspec(text))
    assert any("filters: none" in w for w in warnings), warnings


def _card_triggers(html: str) -> dict[str, str]:
    """region name -> hx-trigger of its dashboard card skeleton."""
    out: dict[str, str] = {}
    for m in re.finditer(r'hx-get="/api/workspaces/desk/regions/(\w+)[^"]*"[^>]*', html):
        trig = re.search(r'hx-trigger="([^"]*)"', m.group(0))
        if trig:
            out.setdefault(m.group(1), trig.group(1))
    return out


def test_eager_overrides_the_default_fold() -> None:
    regions = [f"  r{i}:\n    source: Stack\n    display: list\n" for i in range(5)]
    # r3 (below the fold of three) is promoted; r1 (inside it) is demoted.
    regions[3] += "    eager: true\n"
    regions[1] += "    eager: false\n"
    spec = _appspec(_desk(*regions))
    ctx = build_workspace_context(spec.workspaces[0], app_spec=spec)
    html = render_workspace_content_typed(
        workspace=ctx, catalog=[], fold_count=ctx.fold_count, primary_actions=[]
    )
    triggers = _card_triggers(html)
    eager = {name for name, trig in triggers.items() if trig.startswith("load")}
    assert eager == {"r0", "r2", "r3"}, triggers
    assert triggers["r4"].startswith("intersect once")


def test_aggregate_sql_ranks_before_it_limits() -> None:
    sql, _params = build_aggregate_sql(
        table_name="Stack",
        placeholder_style="%s",
        dimensions=[Dimension(name="status")],
        measures={"n": "count"},
        filters=None,
        limit=2,
        rank_by=("n", "desc"),
    )
    assert 'ORDER BY "n" DESC NULLS LAST, "Stack"."status"' in sql
    assert sql.endswith("LIMIT 2")
    # NULL buckets are dropped by the caller, so they must not take a slot.
    assert '"Stack"."status" IS NOT NULL' in sql
    unranked, _ = build_aggregate_sql(
        table_name="Stack",
        placeholder_style="%s",
        dimensions=[Dimension(name="status")],
        measures={"n": "count"},
        filters=None,
    )
    assert '"n" DESC' not in unranked


def test_not_in_subquery_filter_composes_into_the_where_clause() -> None:
    builder = QueryBuilder(table_name="Stack")
    builder.add_filter("id__not_in_subquery", ('SELECT "id" FROM "Stack" LIMIT %s', [1]))
    builder.add_filter("status", "draft")
    where, params = builder.build_where_clause()
    assert FilterOperator.NOT_IN_SUBQUERY == "not_in_subquery"
    assert where == 'WHERE "id" NOT IN (SELECT "id" FROM "Stack" LIMIT %s) AND "status" = %s'
    assert params == [1, "draft"]


def test_comparison_limit_cuts_after_ranking() -> None:
    buckets = [
        {"label": n, "metrics": {"n": v}, "value": v} for n, v in (("a", 1), ("b", 5), ("c", 3))
    ]
    rows, max_value = build_comparison_inputs(
        group_by="department",
        bucketed_metrics=buckets,
        items=[],
        columns=[],
        rank_by="n",
        order="desc",
        outlier_spec=ir.ComparisonOutlierSpec(),
        limit=2,
    )
    assert [(r["rank"], r["label"]) for r in rows] == [(1, "b"), (2, "c")]
    assert max_value == 5
