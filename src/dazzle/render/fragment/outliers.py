"""Pure statistical outlier flagging for display: comparison (#1470)."""

import statistics
from typing import Literal

from dazzle.core.ir.workspaces import ComparisonOutlierSpec

Flag = Literal["low", "high"]


def _flag_by_fences(
    values: list[float | None], low_fence: float | None, high_fence: float | None
) -> list[Flag | None]:
    """Flag each non-None value below ``low_fence`` (``low``) / above ``high_fence``."""
    out: list[Flag | None] = [None] * len(values)
    for i, v in enumerate(values):
        if v is None:
            continue
        if low_fence is not None and v < low_fence:
            out[i] = "low"
        elif high_fence is not None and v > high_fence:
            out[i] = "high"
    return out


def _iqr_fences(nums: list[float]) -> tuple[float, float] | None:
    """Tukey fences (Q1-1.5·IQR, Q3+1.5·IQR), or None when spread is zero."""
    q1, _q2, q3 = statistics.quantiles(nums, n=4)  # exclusive method (default)
    iqr = q3 - q1
    if iqr == 0:
        return None
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def _sigma_fences(nums: list[float], spec: ComparisonOutlierSpec) -> tuple[float, float] | None:
    """Mean ± k·σ fences (population σ), or None when σ is zero."""
    # `or 2.0` would mis-handle a schema-legal sigma_k=0.0 (falsy); be explicit.
    k = spec.sigma_k if spec.sigma_k is not None else 2.0
    mean = statistics.fmean(nums)
    sd = statistics.pstdev(nums)
    if sd == 0:
        return None
    return mean - k * sd, mean + k * sd


def flag_outliers(values: list[float | None], spec: ComparisonOutlierSpec) -> list[Flag | None]:
    """Return a per-row flag aligned to ``values`` (``None`` where not flagged).

    ``iqr``/``sigma`` skip flagging below 4 numeric values (small-N guard) and
    when the spread is zero (all-equal). ``threshold`` applies at any N. ``None``
    values are excluded from the distribution and never flagged.
    """
    if spec.method == "none":
        return [None] * len(values)

    if spec.method == "threshold":
        return _flag_by_fences(values, spec.threshold_low, spec.threshold_high)

    nums = [float(v) for v in values if v is not None]
    if len(nums) < 4:
        return [None] * len(values)

    fences: tuple[float, float] | None = None
    if spec.method == "iqr":
        fences = _iqr_fences(nums)
    elif spec.method == "sigma":
        fences = _sigma_fences(nums, spec)

    if fences is None:
        return [None] * len(values)
    return _flag_by_fences(values, fences[0], fences[1])
