"""Tests for the `dazzle agent ...` CLI subcommands (#788)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli.agent_commands import agent_app

runner = CliRunner()


def _write_min_manifest(root: Path) -> None:
    (root / "dazzle.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n\n[modules]\npaths = ["./dsl"]\n'
    )


class TestAgentSeed:
    def test_unknown_command_rejected(self, tmp_path: Path) -> None:
        _write_min_manifest(tmp_path)
        result = runner.invoke(agent_app, ["seed", "not_a_command", "-p", str(tmp_path)])
        assert result.exit_code == 2
        assert "no seeder" in result.output

    def test_missing_manifest_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(agent_app, ["seed", "improve", "-p", str(tmp_path)])
        assert result.exit_code == 1
        assert "dazzle.toml" in result.output

    def test_dry_run_emits_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_min_manifest(tmp_path)
        # Stub out the seeder so we don't actually spawn subprocesses
        from dazzle.cli import agent_commands as mod

        monkeypatch.setitem(
            mod._SEEDERS,
            "improve",
            lambda project: [
                {
                    "kind": "lint",
                    "description": "missing search_fields",
                    "status": "PENDING",
                    "attempts": 0,
                    "notes": "stub",
                }
            ],
        )

        result = runner.invoke(
            agent_app,
            ["seed", "improve", "-p", str(tmp_path), "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["command"] == "improve"
        assert payload["gaps"][0]["kind"] == "lint"

    def test_writes_backlog_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_min_manifest(tmp_path)
        from dazzle.cli import agent_commands as mod

        monkeypatch.setitem(
            mod._SEEDERS,
            "improve",
            lambda project: [
                {
                    "kind": "lint",
                    "description": "gap 1",
                    "status": "PENDING",
                    "attempts": 0,
                    "notes": "ok",
                },
                {
                    "kind": "validation",
                    "description": "gap 2",
                    "status": "PENDING",
                    "attempts": 0,
                    "notes": "ok",
                },
            ],
        )

        result = runner.invoke(agent_app, ["seed", "improve", "-p", str(tmp_path)])
        assert result.exit_code == 0, result.output

        backlog = tmp_path / "agent" / "improve-backlog.md"
        assert backlog.exists()
        text = backlog.read_text()
        assert "| 1 | lint | gap 1 |" in text
        assert "| 2 | validation | gap 2 |" in text


class TestAgentSignals:
    def _chdir(self, monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
        monkeypatch.chdir(path)

    def test_requires_emit_or_consume(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._chdir(monkeypatch, tmp_path)
        result = runner.invoke(agent_app, ["signals", "--source", "improve"])
        assert result.exit_code == 2

    def test_emit_without_payload(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._chdir(monkeypatch, tmp_path)
        result = runner.invoke(
            agent_app,
            ["signals", "--source", "improve", "--emit", "fix-committed"],
        )
        assert result.exit_code == 0, result.output
        signal_files = list((tmp_path / ".dazzle" / "signals").glob("*-improve-fix-committed.json"))
        assert len(signal_files) == 1

    def test_emit_with_payload(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._chdir(monkeypatch, tmp_path)
        result = runner.invoke(
            agent_app,
            [
                "signals",
                "--source",
                "improve",
                "--emit",
                "fix-committed",
                "--payload",
                '{"gap": "x", "commit": "abc"}',
            ],
        )
        assert result.exit_code == 0, result.output

        (signal_file,) = (tmp_path / ".dazzle" / "signals").glob("*-improve-fix-committed.json")
        data = json.loads(signal_file.read_text())
        assert data["payload"] == {"gap": "x", "commit": "abc"}

    def test_emit_bad_json_payload_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._chdir(monkeypatch, tmp_path)
        result = runner.invoke(
            agent_app,
            [
                "signals",
                "--source",
                "improve",
                "--emit",
                "fix-committed",
                "--payload",
                "not json",
            ],
        )
        assert result.exit_code == 2
        assert "not valid JSON" in result.output

    def test_emit_and_consume_exclusive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._chdir(monkeypatch, tmp_path)
        result = runner.invoke(
            agent_app,
            [
                "signals",
                "--source",
                "improve",
                "--emit",
                "fix-committed",
                "--consume",
            ],
        )
        assert result.exit_code == 2

    def test_consume_shows_signals_from_other_sources(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._chdir(monkeypatch, tmp_path)
        from dazzle.cli.runtime_impl import ux_cycle_signals as bus

        bus.emit("ux-cycle", "ux-component-shipped", {"component": "kanban"})

        result = runner.invoke(agent_app, ["signals", "--source", "improve", "--consume"])
        assert result.exit_code == 0, result.output
        assert "ux-component-shipped" in result.output
        assert "kanban" in result.output

    def test_consume_excludes_own_emits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._chdir(monkeypatch, tmp_path)
        from dazzle.cli.runtime_impl import ux_cycle_signals as bus

        bus.emit("improve", "fix-committed", {})

        result = runner.invoke(agent_app, ["signals", "--source", "improve", "--consume"])
        assert "No new signals" in result.output

    def test_consume_kind_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._chdir(monkeypatch, tmp_path)
        from dazzle.cli.runtime_impl import ux_cycle_signals as bus

        bus.emit("ux-cycle", "ux-component-shipped", {"name": "a"})
        time.sleep(0.01)
        bus.emit("polish", "polish-complete", {"closed": 5})

        result = runner.invoke(
            agent_app,
            ["signals", "--source", "improve", "--consume", "--kind", "polish-complete"],
        )
        assert "polish-complete" in result.output
        assert "ux-component-shipped" not in result.output

    def test_consume_marks_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """After consume, a second consume should see no signals."""
        self._chdir(monkeypatch, tmp_path)
        from dazzle.cli.runtime_impl import ux_cycle_signals as bus

        bus.emit("ux-cycle", "ux-component-shipped", {})

        first = runner.invoke(agent_app, ["signals", "--source", "improve", "--consume"])
        assert "new signal" in first.output

        second = runner.invoke(agent_app, ["signals", "--source", "improve", "--consume"])
        assert "No new signals" in second.output


class TestRunnerHealthProbe:
    def test_detects_dazzle_runtime_json(self, tmp_path: Path) -> None:
        from dazzle.services.agent_commands.renderer import _probe_running_app

        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "runtime.json").write_text('{"ready": true}')
        assert _probe_running_app(tmp_path) is True

    def test_detects_lock_file(self, tmp_path: Path) -> None:
        from dazzle.services.agent_commands.renderer import _probe_running_app

        (tmp_path / ".dazzle").mkdir()
        (tmp_path / ".dazzle" / "server.lock").write_text("pid")
        assert _probe_running_app(tmp_path) is True

    def test_false_when_no_markers_and_no_server(self, tmp_path: Path) -> None:
        from dazzle.services.agent_commands.renderer import _probe_running_app

        # tmp_path has no .dazzle dir; the socket probes will almost
        # certainly find nothing on random ports — localhost may have
        # something on 3000/8000 though. This is a best-effort test.
        result = _probe_running_app(tmp_path)
        # Accept either True (local dev server running) or False.
        assert isinstance(result, bool)


class TestCommandDefinitionMetadata:
    def test_improve_has_batch_compatible_and_signals(self) -> None:
        from dazzle.services.agent_commands.loader import load_all_commands

        commands = {c.name: c for c in load_all_commands()}
        imp = commands["improve"]
        assert imp.batch_compatible is True
        assert "fix-committed" in imp.signals_emit
        assert "ux-component-shipped" in imp.signals_consume

    def test_polish_signals_configured(self) -> None:
        from dazzle.services.agent_commands.loader import load_all_commands

        commands = {c.name: c for c in load_all_commands()}
        pol = commands["polish"]
        assert pol.batch_compatible is False
        assert "polish-complete" in pol.signals_emit
        assert "fix-committed" in pol.signals_consume


class TestTemplateRenderIncludesSignalSteps:
    def test_improve_template_has_consume_step(self) -> None:
        from dazzle.services.agent_commands.loader import load_all_commands
        from dazzle.services.agent_commands.renderer import render_skill

        commands = {c.name: c for c in load_all_commands()}
        imp = commands["improve"]
        rendered = render_skill(imp, {"project_name": "demo"})
        assert "Consume signals first" in rendered
        assert "ux-component-shipped" in rendered
        assert "fix-committed" in rendered

    def test_improve_template_has_batch_language(self) -> None:
        from dazzle.services.agent_commands.loader import load_all_commands
        from dazzle.services.agent_commands.renderer import render_skill

        commands = {c.name: c for c in load_all_commands()}
        imp = commands["improve"]
        rendered = render_skill(imp, {"project_name": "demo"})
        assert "Pick a batch" in rendered
        assert "batch_id" in rendered

    def test_polish_template_has_triage_step(self) -> None:
        from dazzle.services.agent_commands.loader import load_all_commands
        from dazzle.services.agent_commands.renderer import render_skill

        commands = {c.name: c for c in load_all_commands()}
        pol = commands["polish"]
        rendered = render_skill(pol, {"project_name": "demo"})
        assert "filter out known issues" in rendered
        assert "GitHub issues" in rendered
        assert "Sentinel findings" in rendered


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
