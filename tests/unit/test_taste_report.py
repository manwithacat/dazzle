"""Taste panel report builder."""

from pathlib import Path

from dazzle.qa.taste_panel import JudgeScore, PanelImage, PanelResult, build_report


def _result() -> PanelResult:
    pool = [
        PanelImage(
            image_id="img-00",
            source="dazzle",
            label="ops_dashboard/main/admin",
            path=Path("/tmp/a.png"),
            theme="light",
        ),
        PanelImage(
            image_id="img-01",
            source="reference",
            label="shadcn_dashboard",
            path=Path("/tmp/r.png"),
            theme="light",
        ),
    ]
    return PanelResult(
        scores=[JudgeScore("img-00", "perceived_craft", 5, 0)],
        means={"perceived_craft": {"dazzle": 5.0, "reference": 8.0}},
        noise={"perceived_craft": 0.3},
        verdict={
            "perceived_craft": {
                "dazzle": 5.0,
                "reference": 8.0,
                "margin": 0.6,
                "gap": 3.0,
                "parity": False,
            }
        },
        pool=pool,
    )


def test_build_report_json_shape() -> None:
    data, _md = build_report(_result())
    assert data["parity"] is False
    assert data["verdict"]["perceived_craft"]["gap"] == 3.0
    assert data["pool"][0]["label"] == "ops_dashboard/main/admin"
    assert data["counts"] == {"dazzle": 1, "reference": 1}


def test_build_report_markdown_contains_verdict_table() -> None:
    _data, md = build_report(_result())
    assert "# Taste Panel" in md
    assert "perceived_craft" in md
    assert "FAIL" in md  # parity=False renders as FAIL
    assert "5.0" in md and "8.0" in md
