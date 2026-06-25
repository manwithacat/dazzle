from dazzle.core.ir.workspaces import ToneBandSpec
from dazzle.http.runtime.workspace_region_computes import build_rag_tones

_BANDS = [
    ToneBandSpec(at=5.0, tone="destructive"),
    ToneBandSpec(at=1.0, tone="warning"),
    ToneBandSpec(at=0.0, tone="positive"),
]


def test_tones_by_band() -> None:
    items = [{"r": 7.0}, {"r": 2.0}, {"r": 0.5}, {"r": -1.0}]
    tones = build_rag_tones(items, column="r", bands=_BANDS)
    assert tones == ["destructive", "warning", "positive", None]  # -1 below all bands


def test_non_finite_and_none() -> None:
    items = [{"r": None}, {"r": float("inf")}, {"r": "x"}, {"r": 3.0}]
    tones = build_rag_tones(items, column="r", bands=_BANDS)
    assert tones == [None, None, None, "warning"]


def test_bands_unsorted_still_descending() -> None:
    bands = [ToneBandSpec(at=0.0, tone="positive"), ToneBandSpec(at=5.0, tone="destructive")]
    assert build_rag_tones([{"r": 9.0}], column="r", bands=bands) == ["destructive"]
