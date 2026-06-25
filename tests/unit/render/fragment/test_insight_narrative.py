from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.insight import build_insight_narrative

_SPEC = ComparisonOutlierSpec(method="iqr")


def _n(buckets, func="count"):
    return build_insight_narrative(
        buckets,
        measure_name="alerts",
        measure_func=func,
        group_label="teams",
        scope_desc="across all teams",
        outlier_spec=_SPEC,
    )


def test_additive_scale_leader_outlier() -> None:
    buckets = [
        {"label": "Platform", "value": 20},
        {"label": "Payments", "value": 19},
        {"label": "Growth", "value": 18},
        {"label": "Data", "value": 17},
        {"label": "Infra", "value": 16},
        {"label": "ML", "value": 1},
    ]
    n = _n(buckets)
    joined = " ".join(n.lines)
    assert "91 alerts across 6 teams" in joined  # total = sum
    assert "Platform is highest at 20" in joined and "%" in joined  # additive → pct
    assert "anomalously low" in joined and "ML" in joined  # 1 is the low outlier
    assert ("Platform", 20.0) in n.citations
    assert n.scope == "across all teams"
    assert n.badge


def test_non_additive_skips_total_and_pct() -> None:
    buckets = [
        {"label": "A", "value": 40},
        {"label": "B", "value": 50},
        {"label": "C", "value": 45},
    ]
    n = _n(buckets, func="avg")
    joined = " ".join(n.lines)
    assert "across 3 teams" in joined
    assert "%" not in joined  # non-additive → no percentage
    assert "B is highest at 50" in joined


def test_negative_sum_suppresses_percentage() -> None:
    # A signed sum where the leader exceeds the net total — never claim ">100%".
    n = _n(
        [
            {"label": "A", "value": 150},
            {"label": "B", "value": 50},
            {"label": "Returns", "value": -80},
        ],
        func="sum",
    )
    joined = " ".join(n.lines)
    assert "%" not in joined  # negative bucket → no misleading percentage
    assert "A is highest at 150" in joined


def test_tiny_float_not_formatted_as_zero() -> None:
    # A non-zero value must not be cited as "0.00".
    n = _n([{"label": "A", "value": 10}, {"label": "B", "value": 0.004}], func="avg")
    joined = " ".join(n.lines)
    assert "0.00" not in joined


def test_dropped_groups_reported_not_hidden() -> None:
    n = _n(
        [
            {"label": "Alpha", "value": 10},
            {"label": "Beta", "value": 20},
            {"label": "Gamma", "value": None},
        ],
        func="count",
    )
    joined = " ".join(n.lines)
    assert "2 of 3 teams" in joined and "no data" in joined


def test_tied_leader_is_stable_alphabetical() -> None:
    a = _n([{"label": "Beta", "value": 50}, {"label": "Alpha", "value": 50}], func="count")
    b = _n([{"label": "Alpha", "value": 50}, {"label": "Beta", "value": 50}], func="count")
    # Same data, different row order → same leader (alphabetical tiebreak).
    assert "Alpha is highest" in " ".join(a.lines)
    assert "Alpha is highest" in " ".join(b.lines)


def test_flat_data_no_outlier_line() -> None:
    buckets = [{"label": x, "value": 5} for x in "ABCDE"]
    n = _n(buckets)
    assert not any("anomal" in line for line in n.lines)


def test_empty_buckets() -> None:
    n = _n([])
    assert n.lines == ("No data to summarise.",)
    assert n.citations == ()


def test_one_group_scale_and_leader_only() -> None:
    n = _n([{"label": "Solo", "value": 7}])
    joined = " ".join(n.lines)
    assert "7 alerts across 1 teams" in joined
    assert "Solo is highest at 7" in joined
    assert not any("anomal" in line for line in n.lines)
