"""#1567 — the on-demand component-vision glue (render→score), mocked heavy parts.

The real path (Playwright screenshot + a live judge client) is subscription-billed
and manual; here we exercise the render + aggregation glue with both injected.
"""

import pytest

from dazzle.testing.ux_catalogue import render_region_by_name, showcase_region_names

pytestmark = pytest.mark.gate


def test_showcase_region_names_nonempty() -> None:
    names = showcase_region_names()
    assert names
    assert "cat_list" in names


def test_render_region_by_name_returns_html() -> None:
    html = render_region_by_name("cat_list")
    assert "<" in html and len(html) > 50


def test_render_region_by_name_unknown_raises() -> None:
    with pytest.raises(KeyError):
        render_region_by_name("no_such_region")


def test_score_component_region_glue(tmp_path) -> None:
    from dazzle.qa.component_vision import score_component_region
    from dazzle.qa.taste_panel import JudgeScore

    captured: dict[str, str] = {}

    def fake_capture(html: str, out_png):
        captured["html"] = html
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n fake")
        return out_png

    def fake_score(image, *, judge, repeat=0, model, client=None):
        return [
            JudgeScore(image_id=image.image_id, dimension="finish_polish", score=7, judge=judge),
            JudgeScore(image_id=image.image_id, dimension="hero_impact", score=6, judge=judge),
        ]

    result = score_component_region(
        "cat_list",
        judges=2,
        model="fake-model",
        capture=fake_capture,
        score_fn=fake_score,
        out_dir=tmp_path,
    )
    assert captured["html"]  # render happened
    assert result["region"] == "cat_list"
    assert result["scores"]["finish_polish"] == 7.0
    assert result["scores"]["hero_impact"] == 6.0


def test_score_component_region_unknown_raises(tmp_path) -> None:
    from dazzle.qa.component_vision import score_component_region

    with pytest.raises(KeyError):
        score_component_region("nope", judges=1, model="x", out_dir=tmp_path)
