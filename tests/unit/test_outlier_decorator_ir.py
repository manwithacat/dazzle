from dazzle.core.ir.workspaces import ComparisonOutlierSpec, DisplayMode, WorkspaceRegion


def test_outlier_on_default_none() -> None:
    r = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert r.outlier_on is None


def test_outlier_on_set_with_method() -> None:
    r = WorkspaceRegion(
        name="r",
        display=DisplayMode.LIST,
        outlier_on="response_time_ms",
        outlier=ComparisonOutlierSpec(method="sigma", sigma_k=2.0),
    )
    assert r.outlier_on == "response_time_ms"
    assert r.outlier is not None and r.outlier.method == "sigma"
