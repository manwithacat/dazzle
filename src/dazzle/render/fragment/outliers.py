"""Pure statistical outlier flagging for display: comparison (#1470)."""

import statistics
from typing import Literal

from dazzle.core.ir.workspaces import ComparisonOutlierSpec

Flag = Literal["low", "high"]


def flag_outliers(values: list[float | None], spec: ComparisonOutlierSpec) -> list[Flag | None]:
    """Return a per-row flag aligned to ``values`` (``None`` where not flagged).

    ``iqr``/``sigma`` skip flagging below 4 numeric values (small-N guard) and
    when the spread is zero (all-equal). ``threshold`` applies at any N. ``None``
    values are excluded from the distribution and never flagged.
    """
    out: list[Flag | None] = [None] * len(values)
    if spec.method == "none":
        return out

    if spec.method == "threshold":
        low, high = spec.threshold_low, spec.threshold_high
        for i, v in enumerate(values):
            if v is None:
                continue
            if low is not None and v < low:
                out[i] = "low"
            elif high is not None and v > high:
                out[i] = "high"
        return out

    nums = [float(v) for v in values if v is not None]
    if len(nums) < 4:
        return out

    if spec.method == "iqr":
        q1, _q2, q3 = statistics.quantiles(nums, n=4)  # exclusive method (default)
        iqr = q3 - q1
        if iqr == 0:
            return out
        low_fence, high_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for i, v in enumerate(values):
            if v is None:
                continue
            if v < low_fence:
                out[i] = "low"
            elif v > high_fence:
                out[i] = "high"
        return out

    if spec.method == "sigma":
        # `or 2.0` would mis-handle a schema-legal sigma_k=0.0 (falsy); be explicit.
        k = spec.sigma_k if spec.sigma_k is not None else 2.0
        mean = statistics.fmean(nums)
        sd = statistics.pstdev(nums)
        if sd == 0:
            return out
        for i, v in enumerate(values):
            if v is None:
                continue
            if v < mean - k * sd:
                out[i] = "low"
            elif v > mean + k * sd:
                out[i] = "high"
        return out

    return out
