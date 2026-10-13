"""
Agent transcript: complete record of an agent run.

The transcript is the primary output of a DazzleAgent mission. It records
every step (observation, decision, action, result) and mission-specific
observations (gaps, assertions, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime
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


def _esc(text: str) -> str:
    """Escape HTML."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
