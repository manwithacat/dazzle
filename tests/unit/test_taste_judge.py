"""Judge runner — vision call shaping, JSON parsing, retries, panel orchestration."""

import json
from pathlib import Path
from typing import Any

import pytest

from dazzle.core.taste_rubric import dimensions_for_theme
from dazzle.qa.taste_panel import (
    PanelImage,
    TastePanelError,
    run_panel,
    score_image,
)

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcff9fa10e0002d20161e6b1c8be0000000049454e44ae426082"
)


class FakeMessages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]

        class Block:
            def __init__(self, t: str) -> None:
                self.text = t

        class Msg:
            content = [Block(text)]

        return Msg()


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = FakeMessages(responses)


def _image(tmp_path: Path, theme: str = "light", source: str = "dazzle") -> PanelImage:
    p = tmp_path / f"{theme}.png"
    p.write_bytes(PNG_1PX)
    return PanelImage(image_id=f"img-{theme}", source=source, label="x", path=p, theme=theme)


def _valid_response(theme: str) -> str:
    dims = dimensions_for_theme(theme)
    return json.dumps({"scores": {d.key: 7 for d in dims}, "worst_detail": "flat buttons"})


def test_score_image_parses_scores_for_light_theme(tmp_path: Path) -> None:
    img = _image(tmp_path, "light")
    client = FakeClient([_valid_response("light")])
    scores = score_image(img, judge=1, client=client)
    assert len(scores) == 5  # dark_mode_integrity excluded for light
    assert {s.dimension for s in scores} == {d.key for d in dimensions_for_theme("light")}
    assert all(s.score == 7 and s.judge == 1 and s.image_id == "img-light" for s in scores)
    # The request contained the image and no identity leak
    call = client.messages.calls[0]
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert '"x"' not in json.dumps(content[1])  # label never sent


def test_score_image_dark_includes_dark_dimension(tmp_path: Path) -> None:
    img = _image(tmp_path, "dark")
    client = FakeClient([_valid_response("dark")])
    scores = score_image(img, judge=0, client=client)
    assert "dark_mode_integrity" in {s.dimension for s in scores}
    assert len(scores) == 6


def test_score_image_retries_then_raises_on_garbage(tmp_path: Path) -> None:
    img = _image(tmp_path, "light")
    client = FakeClient(["not json", "still not json", "nope"])
    with pytest.raises(TastePanelError):
        score_image(img, judge=0, client=client)
    assert len(client.messages.calls) == 3  # initial + 2 retries


def test_score_image_clamps_out_of_range_scores(tmp_path: Path) -> None:
    img = _image(tmp_path, "light")
    dims = dimensions_for_theme("light")
    bad = json.dumps({"scores": {d.key: 15 for d in dims}, "worst_detail": ""})
    client = FakeClient([bad])
    scores = score_image(img, judge=0, client=client)
    assert all(s.score == 10 for s in scores)


def test_run_panel_end_to_end_with_fake_client(tmp_path: Path) -> None:
    dz = _image(tmp_path, "light", source="dazzle")
    ref_path = tmp_path / "ref.png"
    ref_path.write_bytes(PNG_1PX)
    ref = PanelImage(
        image_id="img-ref", source="reference", label="r", path=ref_path, theme="light"
    )
    # Every call returns 7s — enough responses for judges * images + noise repeats
    client = FakeClient([_valid_response("light")] * 50)
    result = run_panel([dz, ref], judges=2, noise_runs=2, noise_subset=2, seed=1, client=client)
    assert result.means["perceived_craft"]["dazzle"] == pytest.approx(7.0)
    assert result.verdict["perceived_craft"]["parity"] is True
    # judges * images = 4 base calls, + noise: subset(2) * noise_runs(2) extra
    assert len(client.messages.calls) == 4 + 2 * 2
