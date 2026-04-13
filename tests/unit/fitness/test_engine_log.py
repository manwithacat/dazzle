"""Task 21 — engine appends a log line per run."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.config import FitnessConfig
from dazzle.fitness.engine import FitnessEngine


@pytest.mark.asyncio
async def test_engine_appends_log_line(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("# App\n\nTriage tickets.\n")

    fake_app = MagicMock()
    fake_app.stories = []
    fake_app.entities = []
    fake_app.personas = []

    fake_llm = MagicMock()
    fake_llm.complete.return_value = "[]"

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value="transcript")

    fake_executor = MagicMock()

    fake_source = MagicMock()
    fake_source.fetch_rows.return_value = []

    engine = FitnessEngine(
        project_root=tmp_path,
        config=FitnessConfig(),
        app_spec=fake_app,
        spec_md_path=spec,
        agent=fake_agent,
        executor=fake_executor,
        snapshot_source=fake_source,
        llm=fake_llm,
    )
    await engine.run()

    log_path = tmp_path / "dev_docs" / "fitness-log.md"
    assert log_path.exists()
    text = log_path.read_text()
    assert "jaccard" in text.lower() or "independence" in text.lower()
