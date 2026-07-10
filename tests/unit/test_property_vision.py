"""#1567 slice 2 — property-vision glue (screenshot->score vs family exemplars),
heavy parts mocked. The real path is on-demand and subscription-billed."""

import json

import pytest

pytestmark = pytest.mark.gate


def _write_manifest(tmp_path, family="stripe", n_refs=1):
    refs = []
    for i in range(n_refs):
        png = tmp_path / f"{family}_{i}.png"
        png.write_bytes(b"\x89PNG fake")
        refs.append(
            {
                "family": family,
                "name": f"ref{i}",
                "url": "https://x",
                "theme": "light",
                "screenshot": str(png),
            }
        )
    manifest = tmp_path / "sitespec_references_manifest.json"
    manifest.write_text(json.dumps({"families": [family], "references": refs}))
    return manifest


def test_exemplars_for_finds_family_refs(tmp_path) -> None:
    from dazzle.qa.property_vision import exemplars_for

    manifest = _write_manifest(tmp_path, "stripe", 2)
    paths = exemplars_for("stripe", manifest_path=manifest)
    assert len(paths) == 2 and all(p.exists() for p in paths)


def test_exemplars_for_missing_family_raises(tmp_path) -> None:
    from dazzle.qa.property_vision import exemplars_for

    manifest = _write_manifest(tmp_path, "stripe", 1)
    with pytest.raises(KeyError):
        exemplars_for("paper", manifest_path=manifest)


def test_exemplars_for_missing_manifest_raises(tmp_path) -> None:
    from dazzle.qa.property_vision import exemplars_for

    with pytest.raises(FileNotFoundError):
        exemplars_for("stripe", manifest_path=tmp_path / "nope.json")


def test_score_property_glue(tmp_path) -> None:
    from dazzle.qa.property_vision import score_property
    from dazzle.qa.taste_panel import JudgeScore

    manifest = _write_manifest(tmp_path, "stripe", 1)
    captured = {}

    def fake_capture(url, out_png):
        captured["url"] = url
        out_png.write_bytes(b"\x89PNG fake")
        return out_png

    def fake_score(image, *, judge, repeat=0, model, client=None, dimensions=None):
        assert dimensions is not None  # must be the sitespec dims, not taste
        return [JudgeScore(image_id=image.image_id, dimension="hero_impact", score=7, judge=judge)]

    result = score_property(
        "http://localhost:3000/",
        "stripe",
        judges=2,
        model="fake",
        out_dir=tmp_path,
        capture=fake_capture,
        score_fn=fake_score,
        manifest_path=manifest,
    )
    assert captured["url"] == "http://localhost:3000/"
    assert result["scores"]["hero_impact"] == 7.0
    assert result["family"] == "stripe"
    assert result["exemplars"]  # resolved + reported


def test_score_property_missing_exemplars_is_usage_error(tmp_path) -> None:
    from dazzle.qa.property_vision import score_property

    called = {"capture": False}

    def fake_capture(url, out_png):
        called["capture"] = True
        return out_png

    with pytest.raises(FileNotFoundError):
        score_property(
            "http://x/",
            "stripe",
            judges=1,
            model="fake",
            out_dir=tmp_path,
            capture=fake_capture,
            manifest_path=tmp_path / "nope.json",
        )
    assert not called["capture"]  # usage error fires BEFORE any capture/billed call
