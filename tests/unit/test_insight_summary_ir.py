from dazzle.core.ir.workspaces import DisplayMode


def test_insight_summary_display_mode() -> None:
    assert DisplayMode.INSIGHT_SUMMARY.value == "insight_summary"
