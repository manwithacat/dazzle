"""Tests for the subagent_explore helpers.

Covers:
  - init_explore_run creates state_dir + findings + runner script
  - ExploreRunContext.to_dict is JSON-serializable
  - run_id defaults to a timestamp and is otherwise user-supplied
  - project_root discovery walks upward for dazzle.toml (#789)
  - read_findings validates top-level shape, accepts extra fields
  - write_runner_script embeds the right paths via repr-escaped values
  - Concurrent runs against the same app+persona get distinct dirs
    via unique run_ids
  - Strategy validation rejects unknown strategies (#789)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    EXPLORE_STRATEGIES,
    SubagentExploreFindings,
    discover_project_root,
    init_explore_run,
    read_findings,
    write_runner_script,
)


def _make_app_tree(tmp_path: Path, name: str = "contact_manager") -> Path:
    """Build a minimal directory that resembles a Dazzle app root."""
    app_root = tmp_path / "examples" / name
    app_root.mkdir(parents=True)
    return app_root


class TestInitExploreRun:
    def test_creates_state_dir_under_project_root(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")

        assert ctx.state_dir.exists()
        assert ctx.state_dir.is_dir()
        assert "dev_docs/ux_cycle_runs" in str(ctx.state_dir)

    def test_findings_file_initialized_empty(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")

        assert ctx.findings_path.exists()
        data = json.loads(ctx.findings_path.read_text())
        assert data == {"proposals": [], "observations": []}

    def test_runner_script_written_to_state_dir(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")

        assert ctx.runner_script_path.exists()
        script = ctx.runner_script_path.read_text()
        assert str(app_root.resolve()) in script
        assert "'user'" in script
        assert str(ctx.conn_path) in script

    def test_run_id_timestamp_default(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user")
        assert len(ctx.run_id) == 15  # YYYYMMDD-HHMMSS
        assert ctx.run_id[8] == "-"

    def test_explicit_run_id_used_verbatim(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="custom-id")
        assert ctx.run_id == "custom-id"
        assert "custom-id" in str(ctx.state_dir)

    def test_does_not_reinitialize_existing_findings(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        ctx.findings_path.write_text(
            json.dumps({"proposals": [{"component_name": "x"}], "observations": []})
        )

        ctx2 = init_explore_run(app_root, "user", run_id="r1")
        assert ctx2.findings_path == ctx.findings_path
        data = json.loads(ctx2.findings_path.read_text())
        assert len(data["proposals"]) == 1

    def test_concurrent_run_ids_produce_distinct_dirs(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        a = init_explore_run(app_root, "user", run_id="a")
        b = init_explore_run(app_root, "user", run_id="b")
        assert a.state_dir != b.state_dir
        assert a.findings_path != b.findings_path

    def test_context_to_dict_is_json_serializable(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        serialized = json.dumps(ctx.to_dict())
        parsed = json.loads(serialized)
        assert parsed["app_name"] == "contact_manager"
        assert parsed["persona_id"] == "user"
        assert parsed["run_id"] == "r1"
        assert parsed["helper_command"] == "python -m dazzle.agent.playwright_helper"
        assert parsed["strategy"] == "edge_cases"  # default

    def test_app_root_defaults_to_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no app_root argument the substrate uses the current directory."""
        downstream = tmp_path / "downstream_app"
        downstream.mkdir()
        monkeypatch.chdir(downstream)
        ctx = init_explore_run(persona_id="user", run_id="r1")
        assert ctx.app_root == downstream.resolve()
        assert ctx.app_name == "downstream_app"

    def test_project_root_discovered_via_dazzle_toml(self, tmp_path: Path) -> None:
        """A dazzle.toml above app_root anchors the runs dir there (#789)."""
        (tmp_path / "dazzle.toml").write_text("[project]\nname='x'\nversion='0.1'\n")
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        assert str(tmp_path / "dev_docs" / "ux_cycle_runs") in str(ctx.state_dir)

    def test_project_root_falls_back_without_manifest(self, tmp_path: Path) -> None:
        """No dazzle.toml anywhere — base_runs_dir lands under app_root itself."""
        app_root = tmp_path / "lonely_app"
        app_root.mkdir()
        ctx = init_explore_run(app_root, "user", run_id="r1")
        assert str(app_root.resolve() / "dev_docs" / "ux_cycle_runs") in str(ctx.state_dir)

    def test_unknown_strategy_raises(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        with pytest.raises(ValueError, match="Unknown explore strategy"):
            init_explore_run(app_root, "user", strategy="not_real")

    def test_persona_id_required(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        with pytest.raises(ValueError, match="persona_id is required"):
            init_explore_run(app_root, "")

    @pytest.mark.parametrize("strategy", EXPLORE_STRATEGIES)
    def test_each_valid_strategy_accepted(self, tmp_path: Path, strategy: str) -> None:
        app_root = _make_app_tree(tmp_path, name=f"app_{strategy}")
        ctx = init_explore_run(app_root, "user", run_id="r1", strategy=strategy)
        assert ctx.strategy == strategy


class TestDiscoverProjectRoot:
    def test_finds_dazzle_toml_in_start(self, tmp_path: Path) -> None:
        (tmp_path / "dazzle.toml").write_text("")
        assert discover_project_root(tmp_path) == tmp_path.resolve()

    def test_finds_dazzle_toml_in_ancestor(self, tmp_path: Path) -> None:
        (tmp_path / "dazzle.toml").write_text("")
        child = tmp_path / "sub" / "grandchild"
        child.mkdir(parents=True)
        assert discover_project_root(child) == tmp_path.resolve()

    def test_falls_back_to_start_when_not_found(self, tmp_path: Path) -> None:
        child = tmp_path / "orphan"
        child.mkdir()
        assert discover_project_root(child) == child.resolve()


class TestWriteRunnerScript:
    def test_script_is_valid_python(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        code = ctx.runner_script_path.read_text()
        compile(code, str(ctx.runner_script_path), "exec")

    def test_script_uses_repr_escaped_paths(self, tmp_path: Path) -> None:
        app_root = tmp_path / "examples" / "app with spaces"
        app_root.mkdir(parents=True)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        code = ctx.runner_script_path.read_text()
        assert f"Path('{app_root.resolve()}')" in code or f'Path("{app_root.resolve()}")' in code

    def test_write_runner_script_is_idempotent(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        first = ctx.runner_script_path.read_text()
        write_runner_script(ctx)
        second = ctx.runner_script_path.read_text()
        assert first == second


class TestReadFindings:
    def test_reads_valid_findings(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
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
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        ctx.findings_path.unlink()
        with pytest.raises(FileNotFoundError):
            read_findings(ctx)

    def test_wrong_top_level_shape_raises(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        ctx.findings_path.write_text(json.dumps([]))
        with pytest.raises(ValueError, match="top-level must be a dict"):
            read_findings(ctx)

    def test_proposals_wrong_type_raises(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        ctx.findings_path.write_text(json.dumps({"proposals": "not a list"}))
        with pytest.raises(ValueError, match="proposals must be a list"):
            read_findings(ctx)

    def test_missing_keys_default_to_empty_lists(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
        ctx.findings_path.write_text(json.dumps({}))
        findings = read_findings(ctx)
        assert findings.proposals == []
        assert findings.observations == []

    def test_extra_fields_passed_through_untouched(self, tmp_path: Path) -> None:
        app_root = _make_app_tree(tmp_path)
        ctx = init_explore_run(app_root, "user", run_id="r1")
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
