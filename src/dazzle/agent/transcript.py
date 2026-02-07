"""
Agent transcript: complete record of an agent run.

The transcript is the primary output of a DazzleAgent mission. It records
every step (observation, decision, action, result) and mission-specific
observations (gaps, assertions, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Step

# =============================================================================
# Observation (mission-specific findings)
# =============================================================================


@dataclass
class Observation:
    """A mission-specific observation recorded by the agent."""

    category: str  # "gap", "assertion", "issue", "success"
    severity: str  # "critical", "high", "medium", "low", "info"
    title: str
    description: str
    location: str = ""  # URL or surface name where observed
    related_artefacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    step_number: int = 0


# =============================================================================
# Transcript
# =============================================================================


@dataclass
class AgentTranscript:
    """Complete record of an agent run."""

    mission_name: str
    steps: list[Step] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    outcome: str = "pending"  # completed, budget_exceeded, max_steps, error
    error: str | None = None
    duration_ms: float = 0.0
    tokens_used: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_observation(self, obs: Observation) -> None:
        """Add a mission-specific observation."""
        if self.steps:
            obs.step_number = self.steps[-1].step_number
        self.observations.append(obs)

    def summary(self) -> str:
        """Human-readable summary of the transcript."""
        lines = [
            f"Mission: {self.mission_name}",
            f"Outcome: {self.outcome}",
            f"Steps: {len(self.steps)}",
            f"Observations: {len(self.observations)}",
            f"Duration: {self.duration_ms / 1000:.1f}s",
            f"Tokens: {self.tokens_used:,}",
        ]
        if self.error:
            lines.append(f"Error: {self.error}")

        if self.observations:
            lines.append("")
            lines.append("Observations:")
            for obs in self.observations:
                lines.append(f"  [{obs.severity}] {obs.title} @ {obs.location}")

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "mission_name": self.mission_name,
            "outcome": self.outcome,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "started_at": self.started_at.isoformat(),
            "model": self.model,
            "metadata": self.metadata,
            "step_count": len(self.steps),
            "steps": [
                {
                    "step_number": s.step_number,
                    "url": s.state.url,
                    "action_type": s.action.type.value,
                    "action_target": s.action.target,
                    "action_value": s.action.value,
                    "reasoning": s.action.reasoning,
                    "result": s.result.message,
                    "error": s.result.error,
                    "duration_ms": s.duration_ms,
                    "tokens_used": s.tokens_used,
                }
                for s in self.steps
            ],
            "observations": [
                {
                    "category": o.category,
                    "severity": o.severity,
                    "title": o.title,
                    "description": o.description,
                    "location": o.location,
                    "related_artefacts": o.related_artefacts,
                    "metadata": o.metadata,
                    "step_number": o.step_number,
                }
                for o in self.observations
            ],
        }

    def to_html_report(self, output_path: Path, project_name: str = "") -> Path:
        """Generate an HTML report of this transcript."""
        output_path.mkdir(parents=True, exist_ok=True)

        total_steps = len(self.steps)
        total_obs = len(self.observations)
        obs_by_severity: dict[str, list[Observation]] = {}
        for obs in self.observations:
            obs_by_severity.setdefault(obs.severity, []).append(obs)

        timestamp = self.started_at.strftime("%Y-%m-%d %H:%M:%S")

        # Severity colors
        sev_colors = {
            "critical": "#dc2626",
            "high": "#ea580c",
            "medium": "#d97706",
            "low": "#2563eb",
            "info": "#6b7280",
        }

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Agent Report - {self.mission_name}</title>
    <style>
        :root {{ --bg: #f8fafc; --card: #fff; --border: #e2e8f0; --text: #1e293b; --muted: #64748b; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
        .meta {{ color: var(--muted); margin-bottom: 1.5rem; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; text-align: center; }}
        .stat-value {{ font-size: 1.75rem; font-weight: bold; }}
        .stat-label {{ color: var(--muted); font-size: 0.875rem; }}
        .section {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 1.5rem; overflow: hidden; }}
        .section-header {{ padding: 0.75rem 1rem; background: #f1f5f9; font-weight: 600; border-bottom: 1px solid var(--border); }}
        .obs {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }}
        .obs:last-child {{ border-bottom: none; }}
        .sev {{ display: inline-block; padding: 0.125rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; color: white; }}
        .step {{ padding: 0.5rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.875rem; cursor: pointer; }}
        .step:hover {{ background: #f8fafc; }}
        .step-num {{ display: inline-block; width: 24px; height: 24px; border-radius: 50%; background: var(--text); color: white; text-align: center; line-height: 24px; font-size: 0.75rem; margin-right: 0.5rem; }}
        .step-action {{ font-weight: 500; }}
        .step-target {{ color: var(--muted); font-family: monospace; font-size: 0.8rem; }}
        .step-error {{ color: #dc2626; }}
        .step-detail {{ display: none; padding: 0.5rem 1rem 0.5rem 3rem; background: #f8fafc; font-size: 0.8rem; font-family: monospace; white-space: pre-wrap; }}
    </style>
</head>
<body>
<div class="container">
    <h1>{self.mission_name}</h1>
    <p class="meta">{project_name} &bull; {timestamp} &bull; {self.model} &bull; {self.outcome}</p>

    <div class="summary">
        <div class="stat"><div class="stat-value">{total_steps}</div><div class="stat-label">Steps</div></div>
        <div class="stat"><div class="stat-value">{total_obs}</div><div class="stat-label">Observations</div></div>
        <div class="stat"><div class="stat-value">{self.tokens_used:,}</div><div class="stat-label">Tokens</div></div>
        <div class="stat"><div class="stat-value">{self.duration_ms / 1000:.1f}s</div><div class="stat-label">Duration</div></div>
    </div>
"""

        # Observations section
        if self.observations:
            html += '    <div class="section">\n'
            html += '        <div class="section-header">Observations</div>\n'
            for obs in self.observations:
                color = sev_colors.get(obs.severity, "#6b7280")
                html += '        <div class="obs">\n'
                html += f'            <span class="sev" style="background:{color}">{obs.severity}</span>\n'
                html += f"            <strong>{_esc(obs.title)}</strong>\n"
                html += f"            <span class='step-target'>@ {_esc(obs.location)}</span>\n"
                html += f"            <div style='margin-top:0.25rem;color:var(--muted);font-size:0.875rem'>{_esc(obs.description)}</div>\n"
                html += "        </div>\n"
            html += "    </div>\n"

        # Steps section
        html += '    <div class="section">\n'
        html += '        <div class="section-header">Steps</div>\n'
        for step in self.steps:
            err_class = " step-error" if step.result.error else ""
            target_display = _esc((step.action.target or "")[:60])
            reason = _esc(step.action.reasoning[:100]) if step.action.reasoning else ""
            html += f"        <div class=\"step{err_class}\" onclick=\"var d=this.nextElementSibling;d.style.display=d.style.display==='block'?'none':'block'\">\n"
            html += f'            <span class="step-num">{step.step_number}</span>\n'
            html += f'            <span class="step-action">{step.action.type.value}</span>\n'
            html += f'            <span class="step-target">{target_display}</span>\n'
            if reason:
                html += f"            <span style='color:var(--muted);font-size:0.8rem'> &mdash; {reason}</span>\n"
            if step.result.error:
                html += f"            <span class='step-error'> [{_esc(step.result.error[:60])}]</span>\n"
            html += "        </div>\n"
            html += f'        <div class="step-detail">URL: {_esc(step.state.url)}\nResult: {_esc(step.result.message)}\n{_esc(step.result.error or "")}</div>\n'
        html += "    </div>\n"

        html += "</div>\n</body>\n</html>"

        report_file = (
            output_path
            / f"agent_report_{self.mission_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        report_file.write_text(html)
        return report_file


def _esc(text: str) -> str:
    """Escape HTML."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
