from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.http.runtime.workspace_region_computes import build_outlier_flags


def test_flags_aligned_to_items() -> None:
    items = [
        {"name": "A", "ms": 100},
        {"name": "B", "ms": 98},
        {"name": "C", "ms": 96},
        {"name": "D", "ms": 94},
        {"name": "E", "ms": 92},
        {"name": "F", "ms": 5},
    ]
    flags = build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="iqr"))
    assert len(flags) == len(items)
    assert flags[5] == "low"  # 5 is the low outlier vs the tight pack
    assert flags[0] is None


def test_small_n_no_flags() -> None:
    items = [{"ms": 1}, {"ms": 99}, {"ms": 2}]
    assert build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="iqr")) == [
        None,
        None,
        None,
    ]


def test_non_finite_and_none_excluded() -> None:
    items = [
        {"ms": 100},
        {"ms": 98},
        {"ms": 96},
        {"ms": 94},
        {"ms": 92},
        {"ms": None},
        {"ms": float("inf")},
        {"ms": 5},
    ]
    flags = build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="iqr"))
    assert flags[5] is None and flags[6] is None  # None + inf never flagged
    assert flags[7] == "low"  # 5 flags low vs the 6 finite pack values


def test_method_none_inert() -> None:
    items = [{"ms": 1}, {"ms": 2}, {"ms": 3}, {"ms": 4}, {"ms": 99}]
    assert (
        build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="none"))
        == [None] * 5
    )
