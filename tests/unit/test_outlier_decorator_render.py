from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self, name: str) -> None:
        self.name = name
        self.title = None
        self.display = "list"
        self.empty_message = None
        self.row_action = None


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def _ctx() -> dict:
    return {
        "items": [
            {"name": "Fast", "ms": 100},
            {"name": "Slow", "ms": 5},
        ],
        "columns": [
            {"key": "name", "label": "Name", "type": "text"},
            {"key": "ms", "label": "Response (ms)", "type": "text"},
        ],
        "outlier_on": "ms",
        "outlier_flags": [None, "low"],
    }


def test_flagged_cell_has_tone_badge() -> None:
    html = _render(WorkspaceRegionAdapter().build(_FakeRegion("health"), _ctx()))
    assert 'data-dz-tone="warning"' in html
    assert "⚠" in html
    assert "low" in html
    assert "100" in html and "5" in html


def test_no_flags_renders_plain_list() -> None:
    ctx = _ctx()
    ctx["outlier_flags"] = [None, None]
    html = _render(WorkspaceRegionAdapter().build(_FakeRegion("health"), ctx))
    assert 'data-dz-tone="warning"' not in html
    assert "100" in html and "5" in html


def test_outlier_on_unset_is_ordinary_list() -> None:
    ctx = _ctx()
    ctx["outlier_on"] = ""
    ctx["outlier_flags"] = []
    html = _render(WorkspaceRegionAdapter().build(_FakeRegion("health"), ctx))
    assert "⚠" not in html
