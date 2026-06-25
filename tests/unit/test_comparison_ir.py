from dazzle.core.ir.workspaces import ComparisonOutlierSpec, DisplayMode, WorkspaceRegion


def test_comparison_display_mode() -> None:
    assert DisplayMode.COMPARISON.value == "comparison"


def test_outlier_spec_defaults() -> None:
    s = ComparisonOutlierSpec()
    assert s.method == "iqr"
    assert s.sigma_k is None and s.threshold_low is None and s.threshold_high is None


def test_region_comparison_fields() -> None:
    r = WorkspaceRegion(
        name="league",
        display=DisplayMode.COMPARISON,
        rank_by="rate",
        order="asc",
        outlier=ComparisonOutlierSpec(method="sigma", sigma_k=2.0),
    )
    assert r.rank_by == "rate"
    assert r.order == "asc"
    assert r.outlier is not None and r.outlier.method == "sigma" and r.outlier.sigma_k == 2.0


def test_region_comparison_defaults() -> None:
    r = WorkspaceRegion(name="league", display=DisplayMode.COMPARISON)
    assert r.rank_by is None and r.order == "desc" and r.outlier is None
