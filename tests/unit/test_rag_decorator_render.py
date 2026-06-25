from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self) -> None:
        self.name = "health"
        self.title = None
        self.display = "list"
        self.empty_message = None
        self.row_action = None


def _render(ctx: dict) -> str:
    return FragmentRenderer().render(WorkspaceRegionAdapter().build(_FakeRegion(), ctx))


def _ctx() -> dict:
    return {
        "items": [{"name": "A", "rate": 7}, {"name": "B", "rate": 0.2}],
        "columns": [
            {"key": "name", "label": "Name", "type": "text"},
            {"key": "rate", "label": "Rate", "type": "text"},
        ],
        "rag_on": "rate",
        "rag_tones": ["destructive", "positive"],
    }


def test_rag_cell_has_band_tone_badge() -> None:
    html = _render(_ctx())
    assert 'data-dz-tone="destructive"' in html
    assert 'data-dz-tone="positive"' in html
    assert "critical" in html and "good" in html  # derived labels
    assert "7" in html and "0.2" in html  # values still render


def test_no_rag_when_unset() -> None:
    ctx = _ctx()
    ctx["rag_on"] = ""
    ctx["rag_tones"] = []
    html = _render(ctx)
    assert "destructive" not in html


def test_rag_label_escaping() -> None:
    ctx = _ctx()
    ctx["rag_tones"] = ['"><script>alert(1)</script>', "positive"]
    html = _render(ctx)
    assert "<script>alert(1)</script>" not in html
