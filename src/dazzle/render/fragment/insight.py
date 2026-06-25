"""Pure deterministic NLG for display: insight_summary (#1470 Slice 1).

Every generated sentence must be TRUE for the data — the feature's whole value is
that it cannot hallucinate. Hence the guards below: no "% of total" when a signed
sum makes a part exceed the whole; no "0.00" citation for a non-zero value; an
honest "N of M groups" when some groups had no data; measure-agnostic "is highest"
(never "leads", which would mis-read a `min` metric); and a stable tiebreak so two
loads of tied data never disagree on the leader.
"""

import math
from dataclasses import dataclass
from typing import Any, Literal

from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.outliers import flag_outliers

_ADDITIVE = {"count", "sum"}


@dataclass(frozen=True, slots=True)
class InsightNarrative:
    """Deterministic narrative + its grounding (the cited values)."""

    lines: tuple[str, ...]
    citations: tuple[tuple[str, float], ...]
    scope: str
    badge: str = "Computed from live data"


@dataclass(frozen=True, slots=True)
class StoredInsight:
    """A pre-computed (eventually LLM-authored) narrative overlay (#1470 Slice 2a).

    Rendered ABOVE the deterministic citations (the always-present grounding),
    so the prose is always verifiable against the real values beneath it.
    """

    prose: tuple[str, ...]
    confidence: Literal["high", "medium", "low"]
    generated_at: str


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    if 0 < abs(v) < 0.005:  # 2dp would round a non-zero value to "0.00" — keep significance
        return f"{v:.3g}"
    return f"{v:.2f}"


def _num(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _scale_line(
    measure_name: str, group_label: str, n: int, dropped: int, total: float, additive: bool
) -> str:
    clause = (
        f"{n} {group_label}"
        if not dropped
        else f"{n} of {n + dropped} {group_label} (the rest had no data)"
    )
    return (
        f"{_fmt(total)} {measure_name} across {clause}."
        if additive
        else f"{measure_name} across {clause}."
    )


def _leader_line(
    pairs: list[tuple[str, float]], total: float, additive: bool, all_nonneg: bool
) -> str:
    best = max(v for _lbl, v in pairs)
    # Stable alphabetical tiebreak so tied data never names a different leader on a
    # re-render (the GROUP BY row order isn't guaranteed).
    leader_lbl = min(lbl for lbl, v in pairs if v == best)
    if additive and total > 0 and all_nonneg:
        return (
            f"{leader_lbl} is highest at {_fmt(best)} ({round(best / total * 100)}% of the total)."
        )
    return f"{leader_lbl} is highest at {_fmt(best)}."


def _outlier_line(
    pairs: list[tuple[str, float]], outlier_spec: ComparisonOutlierSpec
) -> str | None:
    flags = flag_outliers([v for _lbl, v in pairs], outlier_spec)
    for (lbl, v), flag in zip(pairs, flags, strict=True):
        if flag in ("low", "high"):
            return f"{lbl} is anomalously {flag} at {_fmt(v)}."
    return None


def build_insight_narrative(
    buckets: list[dict[str, Any]],
    *,
    measure_name: str,
    measure_func: str,
    group_label: str,
    scope_desc: str,
    outlier_spec: ComparisonOutlierSpec,
) -> InsightNarrative:
    """Build a grounded narrative (scale + leader + outlier) from grouped buckets.

    ``buckets`` are ``[{"label", "value"}, ...]``. Additive measures (count/sum)
    get a total + "% of total" (only when all values are non-negative); non-additive
    (avg/min/max) skip them. The outlier line reuses the shipped ``flag_outliers``.
    Every claim cites an exact value; groups with no usable value are reported, not
    silently dropped.
    """
    labeled = [(lbl, _num(b.get("value"))) for b in buckets if (lbl := str(b.get("label") or ""))]
    pairs: list[tuple[str, float]] = [(lbl, v) for lbl, v in labeled if v is not None]
    if not pairs:
        return InsightNarrative(("No data to summarise.",), (), scope_desc)

    n = len(pairs)
    additive = measure_func in _ADDITIVE
    all_nonneg = all(v >= 0 for _lbl, v in pairs)
    total = sum(v for _lbl, v in pairs)

    lines: list[str] = [
        _scale_line(measure_name, group_label, n, len(labeled) - n, total, additive),
        _leader_line(pairs, total, additive, all_nonneg),
    ]
    outlier = _outlier_line(pairs, outlier_spec)
    if outlier is not None:
        lines.append(outlier)

    return InsightNarrative(tuple(lines), tuple(pairs), scope_desc)
