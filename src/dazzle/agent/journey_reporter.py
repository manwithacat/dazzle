"""HTML report renderer for E2E journey testing results."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dazzle.agent.journey_models import AnalysisReport, JourneySession

# Template directory lives in dazzle_ui
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "dazzle_ui" / "templates"


def render_report(
    sessions: list[JourneySession],
    analysis: AnalysisReport,
    output_path: Path,
) -> None:
    """Render an E2E journey HTML report and write it to *output_path*."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("reports/e2e_journey.html")
    html = template.render(sessions=sessions, analysis=analysis)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
