"""Data models for the Dazzle visual QA toolkit."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class CapturedScreen:
    """A screenshot captured for a persona/workspace combination."""

    persona: str
    workspace: str
    url: str
    screenshot: Path
    viewport: str = "desktop"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Finding:
    """A single QA finding from visual inspection of a screen."""

    category: str
    severity: str
    location: str
    description: str
    suggestion: str


@dataclass
class QAReport:
    """Aggregated QA findings for an application."""

    app: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "medium")

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "low")

    @property
    def total(self) -> int:
        return len(self.findings)
