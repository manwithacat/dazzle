from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.outliers import flag_outliers


def test_iqr_flags_low_and_high() -> None:
    vals = [10, 11, 12, 13, 14, 100, -50]  # 100 high, -50 low vs the pack
    out = flag_outliers(vals, ComparisonOutlierSpec(method="iqr"))
    assert out[5] == "high"
    assert out[6] == "low"
    assert out[0] is None


def test_iqr_small_n_no_flags() -> None:
    assert flag_outliers([1, 99, 2], ComparisonOutlierSpec(method="iqr")) == [None, None, None]


def test_all_equal_no_flags() -> None:
    assert flag_outliers([5, 5, 5, 5, 5], ComparisonOutlierSpec(method="iqr")) == [None] * 5


def test_sigma() -> None:
    # 4-identical + 1 outlier lands the outlier exactly at mean+2σ (a degenerate
    # shape), so flag at k=1.5 where 200 clears the fence unambiguously.
    out = flag_outliers([10, 10, 10, 10, 200], ComparisonOutlierSpec(method="sigma", sigma_k=1.5))
    assert out[4] == "high"


def test_sigma_default_k_when_none() -> None:
    # sigma_k unset → defaults to 2.0; 200 clears the mean+2σ fence over a varied pack.
    out = flag_outliers([10, 11, 9, 10, 12, 200], ComparisonOutlierSpec(method="sigma"))
    assert out[5] == "high"


def test_sigma_k_zero_flags_any_deviation() -> None:
    # sigma_k=0.0 is schema-legal: fence collapses to the mean, so any value off
    # the mean flags. Guards against the `or 2.0` falsy-zero footgun.
    out = flag_outliers([10, 10, 10, 10, 12], ComparisonOutlierSpec(method="sigma", sigma_k=0.0))
    assert out[4] == "high"


def test_threshold_low_high() -> None:
    spec = ComparisonOutlierSpec(method="threshold", threshold_low=90.0, threshold_high=120.0)
    assert flag_outliers([85, 100, 130], spec) == ["low", None, "high"]


def test_threshold_applies_at_small_n() -> None:
    spec = ComparisonOutlierSpec(method="threshold", threshold_low=90.0)
    assert flag_outliers([85, 100], spec) == ["low", None]


def test_none_excluded_and_not_flagged() -> None:
    out = flag_outliers([10, 11, 12, 13, 14, None, 100], ComparisonOutlierSpec(method="iqr"))
    assert out[5] is None  # None never flagged
    assert out[6] == "high"


def test_method_none() -> None:
    assert flag_outliers([1, 2, 3, 4, 99], ComparisonOutlierSpec(method="none")) == [None] * 5
