"""Pipeline_steps literal values must not become emdash (oral #161)."""

from __future__ import annotations

from dazzle.render.filters import clerk_pipeline_stage_value
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakePipeline:
    name = "alert_pipeline"
    title = "Alert pipeline"
    display = "pipeline_steps"
    empty_message = "No pipeline data available."


def test_clerk_pipeline_stage_value_counts_and_literals() -> None:
    assert clerk_pipeline_stage_value(12) == 12
    assert clerk_pipeline_stage_value(12.0) == 12
    assert clerk_pipeline_stage_value(0) == 0
    assert clerk_pipeline_stage_value("Daily 02:00 UTC") == "Daily 02:00 UTC"
    assert clerk_pipeline_stage_value("zzz") == "zzz"
    assert clerk_pipeline_stage_value("1e2") == "1e2"
    assert clerk_pipeline_stage_value("") is None
    assert clerk_pipeline_stage_value(None) is None


def test_pipeline_html_renders_literal_not_emdash() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakePipeline(),
            {
                "pipeline_stage_data": [
                    {"label": "Active", "value": 12.0, "caption": "currently firing"},
                    {
                        "label": "Audit",
                        "value": "Daily 02:00 UTC",
                        "caption": "external compliance log",
                    },
                    {"label": "Leftover", "value": "zzz"},
                ],
            },
        )
    )
    assert "Daily 02:00 UTC" in html
    assert ">12<" in html or ">12</span>" in html
    assert "zzz" in html
    assert "currently firing" in html
    assert "external compliance log" in html
    # No omitted-literal emdash: every stage has a headline.
    assert html.count("dz-pipeline-stage-value") == 3
    assert "—" not in html
