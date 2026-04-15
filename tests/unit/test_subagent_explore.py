"""Tests for cycle 198's subagent_explore helpers.

Covers:
  - init_explore_run creates state_dir + findings + runner script
  - ExploreRunContext.to_dict is JSON-serializable
  - run_id defaults to a timestamp and is otherwise user-supplied
  - project_root inference from example_root works
  - read_findings validates top-level shape, accepts extra fields
  - write_runner_script embeds the right paths via repr-escaped values
  - Concurrent runs against the same example+persona get distinct dirs
    via unique run_ids
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    SubagentExploreFindings,
    init_explore_run,
    read_findings,
    write_runner_script,
)


def _make_example_tree(tmp_path: Path, name: str = "contact_manager") -> Path:
    """Build a minimal repo-like directory with an example underneath."""
    example_root = tmp_path / "examples" / name
    example_root.mkdir(parents=True)
    # Pretend .env doesn't exist — init_explore_run doesn't read it
    return example_root


class TestInitExploreRun:
    def test_creates_state_dir_under_project_root(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")

        assert ctx.state_dir.exists()
        assert ctx.state_dir.is_dir()
        # state_dir should be under <tmp_path>/dev_docs/ux_cycle_runs/
        assert "dev_docs/ux_cycle_runs" in str(ctx.state_dir)

    def test_findings_file_initialized_empty(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")

        assert ctx.findings_path.exists()
        data = json.loads(ctx.findings_path.read_text())
        assert data == {"proposals": [], "observations": []}

    def test_runner_script_written_to_state_dir(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")

        assert ctx.runner_script_path.exists()
        script = ctx.runner_script_path.read_text()
        # Should embed the example_root + persona + conn_path
        assert str(example_root.resolve()) in script
        assert "'user'" in script
        assert str(ctx.conn_path) in script

    def test_run_id_timestamp_default(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user")
        # Default run_id is an ISO-ish string like 20260415-003000
        assert len(ctx.run_id) == 15  # YYYYMMDD-HHMMSS
        assert ctx.run_id[8] == "-"

    def test_explicit_run_id_used_verbatim(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="custom-id")
        assert ctx.run_id == "custom-id"
        assert "custom-id" in str(ctx.state_dir)

    def test_does_not_reinitialize_existing_findings(self, tmp_path: Path) -> None:
        """Re-running init against the same run_id should not clobber a
        findings file that already has content."""
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.write_text(
            json.dumps({"proposals": [{"component_name": "x"}], "observations": []})
        )

        ctx2 = init_explore_run(example_root, "user", run_id="r1")
        assert ctx2.findings_path == ctx.findings_path
        data = json.loads(ctx2.findings_path.read_text())
        assert len(data["proposals"]) == 1

    def test_concurrent_run_ids_produce_distinct_dirs(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        a = init_explore_run(example_root, "user", run_id="a")
        b = init_explore_run(example_root, "user", run_id="b")
        assert a.state_dir != b.state_dir
        assert a.findings_path != b.findings_path

    def test_context_to_dict_is_json_serializable(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        # Must serialize cleanly — Paths must be stringified
        serialized = json.dumps(ctx.to_dict())
        parsed = json.loads(serialized)
        assert parsed["example_name"] == "contact_manager"
        assert parsed["persona_id"] == "user"
        assert parsed["run_id"] == "r1"
        assert parsed["helper_command"] == "python -m dazzle.agent.playwright_helper"


class TestWriteRunnerScript:
    def test_script_is_valid_python(self, tmp_path: Path) -> None:
        """Sanity: the generated script compiles without syntax errors."""
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        code = ctx.runner_script_path.read_text()
        # compile() raises SyntaxError if the generated script is malformed
        compile(code, str(ctx.runner_script_path), "exec")

    def test_script_uses_repr_escaped_paths(self, tmp_path: Path) -> None:
        """Paths containing spaces or special chars must survive the template."""
        example_root = tmp_path / "examples" / "app with spaces"
        example_root.mkdir(parents=True)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        code = ctx.runner_script_path.read_text()
        # repr() adds quotes; path should appear inside quotes
        assert (
            f"Path('{example_root.resolve()}')" in code
            or f'Path("{example_root.resolve()}")' in code
        )

    def test_write_runner_script_is_idempotent(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        first = ctx.runner_script_path.read_text()
        write_runner_script(ctx)
        second = ctx.runner_script_path.read_text()
        assert first == second


class TestReadFindings:
    def test_reads_valid_findings(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.write_text(
            json.dumps(
                {
                    "proposals": [{"component_name": "kanban-board", "description": "..."}],
                    "observations": [{"page": "/app", "note": "x", "severity": "minor"}],
                }
            )
        )
        findings = read_findings(ctx)
        assert len(findings.proposals) == 1
        assert findings.proposals[0]["component_name"] == "kanban-board"
        assert len(findings.observations) == 1

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.unlink()
        with pytest.raises(FileNotFoundError):
            read_findings(ctx)

    def test_wrong_top_level_shape_raises(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.write_text(json.dumps([]))  # list, not dict
        with pytest.raises(ValueError, match="top-level must be a dict"):
            read_findings(ctx)

    def test_proposals_wrong_type_raises(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.write_text(json.dumps({"proposals": "not a list"}))
        with pytest.raises(ValueError, match="proposals must be a list"):
            read_findings(ctx)

    def test_missing_keys_default_to_empty_lists(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.write_text(json.dumps({}))  # empty but valid dict
        findings = read_findings(ctx)
        assert findings.proposals == []
        assert findings.observations == []

    def test_extra_fields_passed_through_untouched(self, tmp_path: Path) -> None:
        example_root = _make_example_tree(tmp_path)
        ctx = init_explore_run(example_root, "user", run_id="r1")
        ctx.findings_path.write_text(
            json.dumps(
                {
                    "proposals": [
                        {
                            "component_name": "x",
                            "custom_field": "preserved",
                            "another": 42,
                        }
                    ],
                    "observations": [],
                }
            )
        )
        findings = read_findings(ctx)
        assert findings.proposals[0]["custom_field"] == "preserved"
        assert findings.proposals[0]["another"] == 42


class TestSubagentExploreFindings:
    def test_from_dict_happy_path(self) -> None:
        data = {
            "proposals": [{"component_name": "x"}],
            "observations": [{"page": "/", "note": "n", "severity": "minor"}],
        }
        f = SubagentExploreFindings.from_dict(data)
        assert len(f.proposals) == 1
        assert f.raw == data
