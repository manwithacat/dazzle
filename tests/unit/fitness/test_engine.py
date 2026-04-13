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


@pytest.mark.asyncio
async def test_engine_runs_contract_walk_in_pass1(tmp_path: Path) -> None:
    """If contract_paths is set, Pass 1 runs walk_contract for each contract."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from dazzle.fitness.config import FitnessConfig
    from dazzle.fitness.engine import FitnessEngine
    from dazzle.fitness.walker import WalkResult

    # Stub SnapshotSource
    class _StubSource:
        def fetch_rows(self, table, columns):
            return []

    # Stub LLM
    class _StubLlm:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            return ""

    class _StubObserver:
        async def snapshot(self) -> str:
            return "<html>stub</html>"

    app_spec = MagicMock(entities=[], stories=[], personas=[])
    spec_md = tmp_path / "SPEC.md"
    spec_md.write_text("# spec\n")

    contract_path = tmp_path / "test-component.md"
    contract_path.write_text(
        "# test-component\n\n"
        "## Quality Gates\n\n"
        "1. First gate must hold\n"
        "2. Second gate must hold\n"
    )

    engine = FitnessEngine(
        project_root=tmp_path,
        config=FitnessConfig(max_tokens_per_cycle=100_000),
        app_spec=app_spec,
        spec_md_path=spec_md,
        agent=MagicMock(),
        executor=MagicMock(),
        snapshot_source=_StubSource(),
        llm=_StubLlm(),
        contract_paths=[contract_path],
        contract_observer=_StubObserver(),
    )

    # Patch walk_contract so we can assert it was invoked with the parsed contract.
    with patch(
        "dazzle.fitness.engine.walk_contract",
        new=AsyncMock(
            return_value=WalkResult(
                story_id="contract:test-component",
                persona="fitness_contract",
                steps_executed=2,
            )
        ),
    ) as mock_walk:
        result = await engine.run()

    # walk_contract called once with the parsed contract
    assert mock_walk.await_count == 1
    call_kwargs = mock_walk.call_args.kwargs
    assert call_kwargs["contract"].component_name == "test-component"
    assert len(call_kwargs["contract"].quality_gates) == 2
    # The engine must forward its stored observer to the walker verbatim
    assert call_kwargs["observer"] is engine._contract_observer

    # pass1_run_count reflects the contract walk (no stories in this appspec)
    assert result.pass1_run_count == 1


@pytest.mark.asyncio
async def test_engine_raises_when_contract_paths_set_without_observer(
    tmp_path: Path,
) -> None:
    from unittest.mock import MagicMock

    from dazzle.fitness.config import FitnessConfig
    from dazzle.fitness.engine import FitnessEngine

    class _StubSource:
        def fetch_rows(self, table, columns):
            return []

    class _StubLlm:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            return ""

    app_spec = MagicMock(entities=[], stories=[], personas=[])
    spec_md = tmp_path / "SPEC.md"
    spec_md.write_text("# spec\n")

    contract_path = tmp_path / "test-component.md"
    contract_path.write_text("# test\n\n## Quality Gates\n\n1. A\n")

    engine = FitnessEngine(
        project_root=tmp_path,
        config=FitnessConfig(max_tokens_per_cycle=100_000),
        app_spec=app_spec,
        spec_md_path=spec_md,
        agent=MagicMock(),
        executor=MagicMock(),
        snapshot_source=_StubSource(),
        llm=_StubLlm(),
        contract_paths=[contract_path],
        contract_observer=None,  # missing — should fail at run time
    )

    with pytest.raises(ValueError, match="contract_observer"):
        await engine.run()
