"""Tests for the fitness engine orchestrator (v1 task 19)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.config import FitnessConfig
from dazzle.fitness.engine import FitnessEngine, FitnessRunResult


@pytest.mark.asyncio
async def test_engine_runs_pass1_when_budget_available(tmp_path: Path) -> None:
    spec_md = tmp_path / "spec.md"
    spec_md.write_text("# App\n\nTriage tickets.\n")

    fake_app = MagicMock()
    fake_story = MagicMock()
    fake_story.id = "s1"
    fake_story.persona = "agent"
    fake_story.title = "triage"
    fake_story.steps = []
    fake_app.stories = [fake_story]
    fake_app.entities = []
    fake_app.personas = []

    fake_llm = MagicMock()
    fake_llm.complete.side_effect = [
        '[{"capability":"triage","persona":"agent"}]',  # spec_extractor
        '[{"capability":"triage","persona":"agent"}]',  # adversary
    ]

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value="transcript")

    fake_executor = MagicMock()

    fake_source = MagicMock()
    fake_source.fetch_rows.return_value = []

    engine = FitnessEngine(
        project_root=tmp_path,
        config=FitnessConfig(),
        app_spec=fake_app,
        spec_md_path=spec_md,
        agent=fake_agent,
        executor=fake_executor,
        snapshot_source=fake_source,
        llm=fake_llm,
    )

    result: FitnessRunResult = await engine.run()

    assert isinstance(result, FitnessRunResult)
    assert result.pass1_run_count >= 1
    assert result.findings is not None
    assert "run_id" in result.run_metadata
    assert "maturity" in result.run_metadata
    assert "cycle_at" in result.run_metadata
