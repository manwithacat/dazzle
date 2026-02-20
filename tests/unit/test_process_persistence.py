"""Tests for process persistence layer."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.core.ir.process import (
    ProcessesContainer,
    ProcessSpec,
    ProcessStepSpec,
    ProcessTriggerKind,
    ProcessTriggerSpec,
    StepKind,
)
from dazzle.core.process_persistence import (
    add_processes,
    load_process_index,
    load_processes,
    save_processes,
)


def _make_process(
    name: str = "test_process",
    title: str = "Test Process",
    implements: list[str] | None = None,
) -> ProcessSpec:
    """Create a minimal ProcessSpec for testing."""
    return ProcessSpec(
        name=name,
        title=title,
        implements=implements or [],
        trigger=ProcessTriggerSpec(kind=ProcessTriggerKind.MANUAL),
        steps=[
            ProcessStepSpec(name="step_one", kind=StepKind.SERVICE, service="do_thing"),
        ],
    )


class TestSaveAndLoad:
    """Test save/load round-trip."""

    def test_save_and_load(self, tmp_path: Path):
        proc = _make_process(implements=["ST-001"])
        save_processes(tmp_path, [proc])

        loaded = load_processes(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].name == "test_process"
        assert loaded[0].implements == ["ST-001"]
        assert loaded[0].steps[0].name == "step_one"

    def test_save_creates_directory(self, tmp_path: Path):
        proc = _make_process()
        result_path = save_processes(tmp_path, [proc])

        assert result_path.exists()
        assert ".dazzle/processes/processes.json" in str(result_path)

    def test_load_empty(self, tmp_path: Path):
        assert load_processes(tmp_path) == []

    def test_load_corrupt_file(self, tmp_path: Path):
        processes_dir = tmp_path / ".dazzle" / "processes"
        processes_dir.mkdir(parents=True)
        (processes_dir / "processes.json").write_text("not json")

        assert load_processes(tmp_path) == []

    def test_load_seeds_fallback(self, tmp_path: Path):
        seeds_dir = tmp_path / "dsl" / "seeds" / "processes"
        seeds_dir.mkdir(parents=True)

        container = ProcessesContainer(processes=[_make_process()])
        (seeds_dir / "processes.json").write_text(
            json.dumps(container.model_dump(mode="json"), indent=2)
        )

        loaded = load_processes(tmp_path)
        assert len(loaded) == 1

    def test_runtime_takes_precedence_over_seeds(self, tmp_path: Path):
        # Seeds has proc_a
        seeds_dir = tmp_path / "dsl" / "seeds" / "processes"
        seeds_dir.mkdir(parents=True)
        container_seeds = ProcessesContainer(processes=[_make_process("from_seeds")])
        (seeds_dir / "processes.json").write_text(
            json.dumps(container_seeds.model_dump(mode="json"), indent=2)
        )

        # Runtime has proc_b
        save_processes(tmp_path, [_make_process("from_runtime")])

        loaded = load_processes(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].name == "from_runtime"


class TestAddProcesses:
    """Test add_processes merge logic."""

    def test_add_new(self, tmp_path: Path):
        save_processes(tmp_path, [_make_process("existing")])
        result = add_processes(tmp_path, [_make_process("new_one")])
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"existing", "new_one"}

    def test_skip_duplicate(self, tmp_path: Path):
        save_processes(tmp_path, [_make_process("existing", title="Original")])
        result = add_processes(tmp_path, [_make_process("existing", title="Updated")])
        assert len(result) == 1
        assert result[0].title == "Original"

    def test_overwrite_duplicate(self, tmp_path: Path):
        save_processes(tmp_path, [_make_process("existing", title="Original")])
        result = add_processes(
            tmp_path, [_make_process("existing", title="Updated")], overwrite=True
        )
        assert len(result) == 1
        assert result[0].title == "Updated"


class TestProcessIndex:
    """Test lightweight index loading."""

    def test_index_returns_summaries(self, tmp_path: Path):
        save_processes(
            tmp_path,
            [_make_process("proc_a", implements=["ST-001", "ST-002"])],
        )

        index = load_process_index(tmp_path)
        assert len(index) == 1
        assert index[0]["name"] == "proc_a"
        assert index[0]["implements"] == ["ST-001", "ST-002"]
        assert index[0]["step_count"] == 1

    def test_index_empty(self, tmp_path: Path):
        assert load_process_index(tmp_path) == []


class TestAppFactoryProcessMerge:
    """Test that create_app_factory merges DSL + persisted processes.

    Verifies the fix for #343: persisted processes from
    .dazzle/processes/processes.json are now loaded and merged with
    DSL-parsed processes, with DSL taking precedence on name conflicts.
    """

    def test_persisted_processes_loaded(self, tmp_path: Path) -> None:
        """Persisted processes are picked up when DSL has none."""
        save_processes(tmp_path, [_make_process("persisted_a"), _make_process("persisted_b")])

        dsl_processes: list[ProcessSpec] = []
        persisted = load_processes(tmp_path)
        dsl_names = {p.name for p in dsl_processes}
        merged = dsl_processes + [p for p in persisted if p.name not in dsl_names]

        assert len(merged) == 2
        assert {p.name for p in merged} == {"persisted_a", "persisted_b"}

    def test_dsl_takes_precedence(self, tmp_path: Path) -> None:
        """When a process exists in both DSL and persisted, DSL wins."""
        save_processes(tmp_path, [_make_process("shared", title="Persisted Version")])

        dsl_processes = [_make_process("shared", title="DSL Version")]
        persisted = load_processes(tmp_path)
        dsl_names = {p.name for p in dsl_processes}
        merged = dsl_processes + [p for p in persisted if p.name not in dsl_names]

        assert len(merged) == 1
        assert merged[0].title == "DSL Version"

    def test_combined_merge(self, tmp_path: Path) -> None:
        """DSL and persisted processes merge without duplicates."""
        save_processes(
            tmp_path,
            [_make_process("only_persisted"), _make_process("both", title="Persisted")],
        )

        dsl_processes = [_make_process("only_dsl"), _make_process("both", title="DSL")]
        persisted = load_processes(tmp_path)
        dsl_names = {p.name for p in dsl_processes}
        merged = dsl_processes + [p for p in persisted if p.name not in dsl_names]

        assert len(merged) == 3
        names = {p.name for p in merged}
        assert names == {"only_dsl", "only_persisted", "both"}
        # "both" should be the DSL version
        both_proc = next(p for p in merged if p.name == "both")
        assert both_proc.title == "DSL"


class TestProcessesContainer:
    """Test the Pydantic container model."""

    def test_round_trip(self):
        proc = _make_process()
        container = ProcessesContainer(processes=[proc])
        data = container.model_dump(mode="json")
        restored = ProcessesContainer.model_validate(data)
        assert len(restored.processes) == 1
        assert restored.processes[0].name == "test_process"
