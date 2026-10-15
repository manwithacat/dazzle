import pytest

from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.outliers import flag_outliers


@pytest.mark.parametrize(
    ("values", "spec", "expected"),
    [
        pytest.param(
            [10, 11, 12, 13, 14, 100, -50],
            {"method": "iqr"},
            [None, None, None, None, None, "high", "low"],
            id="iqr-flags-low-and-high",
        ),
        pytest.param([1, 99, 2], {"method": "iqr"}, [None] * 3, id="iqr-small-n-no-flags"),
        pytest.param([5, 5, 5, 5, 5], {"method": "iqr"}, [None] * 5, id="iqr-all-equal-no-flags"),
        pytest.param(
            [10, 11, 12, 13, 14, None, 100],
            {"method": "iqr"},
            [None, None, None, None, None, None, "high"],
            id="none-excluded-and-never-flagged",
        ),
        # 4-identical + 1 outlier lands exactly at mean+2σ (degenerate), so
        # flag at k=1.5 where 200 clears the fence unambiguously.
        pytest.param(
            [10, 10, 10, 10, 200],
            {"method": "sigma", "sigma_k": 1.5},
            [None, None, None, None, "high"],
            id="sigma-explicit-k",
        ),
        # sigma_k unset → 2.0; 200 clears the mean+2σ fence over a varied pack.
        pytest.param(
            [10, 11, 9, 10, 12, 200],
            {"method": "sigma"},
            [None, None, None, None, None, "high"],
            id="sigma-default-k-when-none",
        ),
        # sigma_k=0.0 is schema-legal: the fence collapses to the mean, so any
        # value off the mean flags. Guards the `or 2.0` falsy-zero footgun.
        pytest.param(
            [10, 10, 10, 10, 12],
            {"method": "sigma", "sigma_k": 0.0},
            ["low", "low", "low", "low", "high"],
            id="sigma-k-zero-flags-any-deviation",
        ),
        pytest.param(
            [85, 100, 130],
            {"method": "threshold", "threshold_low": 90.0, "threshold_high": 120.0},
            ["low", None, "high"],
            id="threshold-low-and-high",
        ),
        pytest.param(
            [85, 100],
            {"method": "threshold", "threshold_low": 90.0},
            ["low", None],
            id="threshold-applies-at-small-n",
        ),
        pytest.param([1, 2, 3, 4, 99], {"method": "none"}, [None] * 5, id="method-none"),
    ],
)
def test_flag_outliers(values: list, spec: dict, expected: list) -> None:
    assert flag_outliers(values, ComparisonOutlierSpec(**spec)) == expected
