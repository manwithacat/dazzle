from dazzle.core.ir.workspaces import DisplayMode, ToneBandSpec, WorkspaceRegion


def test_rag_on_default() -> None:
    r = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert r.rag_on is None and r.tone_bands == []


def test_rag_on_with_bands() -> None:
    r = WorkspaceRegion(
        name="r",
        display=DisplayMode.LIST,
        rag_on="error_rate",
        tone_bands=[
            ToneBandSpec(at=5.0, tone="destructive"),
            ToneBandSpec(at=0.0, tone="positive"),
        ],
    )
    assert r.rag_on == "error_rate"
    assert r.tone_bands[0].at == 5.0 and r.tone_bands[0].tone == "destructive"
