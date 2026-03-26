"""Session writer — JSONL-per-persona persistence for journey testing."""

import json
from datetime import date
from pathlib import Path
from typing import TextIO

from dazzle.agent.journey_models import AnalysisReport, JourneySession, JourneyStep


class SessionWriter:
    """Writes journey steps to per-persona JSONL files with immediate flush."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "screenshots").mkdir(exist_ok=True)
        self._handles: dict[str, TextIO] = {}

    def write_step(self, step: JourneyStep) -> None:
        """Append one JSON line to ``{persona}.jsonl``, flushed immediately."""
        persona = step.persona
        if persona not in self._handles:
            path = self.output_dir / f"{persona}.jsonl"
            self._handles[persona] = open(path, "a", encoding="utf-8")  # noqa: SIM115
        fh = self._handles[persona]
        fh.write(step.model_dump_json() + "\n")
        fh.flush()

    def save_screenshot(self, persona: str, step_id: str, png_bytes: bytes) -> str:
        """Write a PNG screenshot and return the relative path string."""
        rel = f"screenshots/{persona}-{step_id}.png"
        (self.output_dir / rel).write_bytes(png_bytes)
        return rel

    def write_analysis(self, report: AnalysisReport) -> None:
        """Write the cross-persona analysis report to ``analysis.json``."""
        (self.output_dir / "analysis.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )

    def load_session(self, persona: str) -> JourneySession:
        """Read a persona's JSONL file back into a ``JourneySession``."""
        path = self.output_dir / f"{persona}.jsonl"
        if not path.exists():
            msg = f"No session file for persona {persona!r}: {path}"
            raise FileNotFoundError(msg)

        steps: list[JourneyStep] = []
        for line in path.read_text(encoding="utf-8").strip().splitlines():
            steps.append(JourneyStep.model_validate(json.loads(line)))

        return JourneySession.from_steps(
            persona=persona,
            steps=steps,
            run_date=date.today().isoformat(),
        )

    def list_personas(self) -> list[str]:
        """Return persona names from existing JSONL files."""
        return sorted(p.stem for p in self.output_dir.glob("*.jsonl"))

    def close(self) -> None:
        """Close all open file handles."""
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()
