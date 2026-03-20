"""Tests for the SessionWriter — JSONL-per-persona persistence layer."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from dazzle.agent.journey_models import (
    AnalysisReport,
    JourneySession,
    JourneyStep,
    Verdict,
)
from dazzle.agent.journey_writer import SessionWriter


def _make_step(
    persona: str = "admin",
    step_number: int = 1,
    *,
    story_id: str | None = None,
    verdict: Verdict = Verdict.PASS,
) -> JourneyStep:
    return JourneyStep(
        persona=persona,
        story_id=story_id,
        phase="explore",
        step_number=step_number,
        action="click",
        target="button#save",
        url_before="http://localhost:3000/tasks",
        url_after="http://localhost:3000/tasks",
        expectation="Page loads",
        observation="Page loaded successfully",
        verdict=verdict,
        reasoning="Matched expectation",
        timestamp=datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC),
    )


def _make_report() -> AnalysisReport:
    return AnalysisReport(
        run_id="run-001",
        dazzle_version="0.44.0",
        deployment_url="http://localhost:3000",
        personas_analysed=2,
        personas_failed=[],
        total_steps=5,
        total_stories=2,
        verdict_counts={"pass": 4, "fail": 1},
        cross_persona_patterns=[],
        dead_ends=[],
        nav_breaks=[],
        scope_leaks=[],
        recommendations=[],
    )


class TestSessionWriterInit:
    def test_creates_output_dir(self, tmp_path: pytest.TempPathFactory) -> None:
        out = tmp_path / "sessions" / "run-1"
        writer = SessionWriter(out)
        assert writer.output_dir.exists()

    def test_creates_screenshots_subdir(self, tmp_path: pytest.TempPathFactory) -> None:
        out = tmp_path / "sessions" / "run-1"
        SessionWriter(out)
        assert (out / "screenshots").is_dir()


class TestWriteStep:
    def test_writes_jsonl_line(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        step = _make_step(persona="admin", step_number=1)
        writer.write_step(step)

        jsonl_path = tmp_path / "admin.jsonl"
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["persona"] == "admin"
        assert data["step_number"] == 1
        assert data["verdict"] == "pass"

    def test_multiple_steps_append(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        writer.write_step(_make_step(persona="admin", step_number=1))
        writer.write_step(_make_step(persona="admin", step_number=2))
        writer.write_step(_make_step(persona="admin", step_number=3))

        lines = (tmp_path / "admin.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3
        for i, line in enumerate(lines, start=1):
            assert json.loads(line)["step_number"] == i

    def test_different_personas_get_separate_files(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        writer.write_step(_make_step(persona="admin"))
        writer.write_step(_make_step(persona="teacher"))

        assert (tmp_path / "admin.jsonl").exists()
        assert (tmp_path / "teacher.jsonl").exists()

    def test_flush_immediate(self, tmp_path: pytest.TempPathFactory) -> None:
        """Data is readable immediately after write_step returns."""
        writer = SessionWriter(tmp_path)
        writer.write_step(_make_step())
        # Read without closing the writer
        content = (tmp_path / "admin.jsonl").read_text()
        assert len(content.strip()) > 0


class TestSaveScreenshot:
    def test_saves_png_file(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        png_bytes = b"\x89PNG\r\n\x1a\nfake"
        result = writer.save_screenshot("admin", "step-1", png_bytes)

        saved = tmp_path / "screenshots" / "admin-step-1.png"
        assert saved.exists()
        assert saved.read_bytes() == png_bytes
        assert result == "screenshots/admin-step-1.png"

    def test_returns_relative_path(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        path = writer.save_screenshot("teacher", "step-5", b"img")
        assert path == "screenshots/teacher-step-5.png"


class TestWriteAnalysis:
    def test_writes_analysis_json(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        report = _make_report()
        writer.write_analysis(report)

        analysis_path = tmp_path / "analysis.json"
        assert analysis_path.exists()
        data = json.loads(analysis_path.read_text())
        assert data["run_id"] == "run-001"
        assert data["personas_analysed"] == 2
        assert data["verdict_counts"] == {"pass": 4, "fail": 1}


class TestLoadSession:
    def test_round_trip(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        steps = [
            _make_step(persona="admin", step_number=1, story_id="story-1"),
            _make_step(persona="admin", step_number=2, story_id="story-1"),
        ]
        for s in steps:
            writer.write_step(s)

        session = writer.load_session("admin")
        assert isinstance(session, JourneySession)
        assert session.persona == "admin"
        assert len(session.steps) == 2
        assert session.steps[0].step_number == 1
        assert session.steps[1].step_number == 2

    def test_load_missing_persona_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        with pytest.raises(FileNotFoundError):
            writer.load_session("nonexistent")


class TestListPersonas:
    def test_empty_dir(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        assert writer.list_personas() == []

    def test_lists_from_jsonl_files(self, tmp_path: pytest.TempPathFactory) -> None:
        writer = SessionWriter(tmp_path)
        writer.write_step(_make_step(persona="admin"))
        writer.write_step(_make_step(persona="teacher"))
        writer.write_step(_make_step(persona="student"))

        personas = writer.list_personas()
        assert sorted(personas) == ["admin", "student", "teacher"]
