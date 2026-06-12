"""Tests for LLM driver resolution and the Claude Code CLI shell-out.

The driver decides who pays for cognition — the developer's Claude
subscription (claude-cli) or the metered API (anthropic-api) — so the
resolution order and the subprocess billing guarantees are contract,
not implementation detail.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dazzle.llm.driver import (
    LLMDriverError,
    _parse_cli_json_output,
    call_claude_cli,
    resolve_llm_driver,
)


def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DAZZLE_LLM_DRIVER", raising=False)
    monkeypatch.delenv("DAZZLE_ENV", raising=False)


class TestResolveLlmDriver:
    def test_explicit_wins_over_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        monkeypatch.setenv("DAZZLE_LLM_DRIVER", "anthropic-api")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            assert (
                resolve_llm_driver(explicit="claude-cli", manifest_driver="anthropic-api")
                == "claude-cli"
            )

    def test_env_var_beats_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        monkeypatch.setenv("DAZZLE_LLM_DRIVER", "claude-cli")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            assert resolve_llm_driver(manifest_driver="anthropic-api") == "claude-cli"

    def test_manifest_drives_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            assert resolve_llm_driver(manifest_driver="claude-cli") == "claude-cli"

    def test_auto_prefers_api_key_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            assert resolve_llm_driver() == "anthropic-api"

    def test_auto_falls_back_to_cli_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            assert resolve_llm_driver() == "claude-cli"

    def test_auto_with_neither_raises_with_both_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=False):
            with pytest.raises(LLMDriverError) as exc:
                resolve_llm_driver()
        # The error must lay out BOTH onboarding paths (subscription + key).
        msg = str(exc.value)
        assert "claude.com/claude-code" in msg
        assert "console.anthropic.com" in msg

    def test_api_requested_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with pytest.raises(LLMDriverError, match="ANTHROPIC_API_KEY"):
            resolve_llm_driver(explicit="anthropic-api")

    def test_cli_requested_without_cli_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=False):
            with pytest.raises(LLMDriverError, match="not on PATH"):
                resolve_llm_driver(explicit="claude-cli")

    def test_unknown_driver_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with pytest.raises(LLMDriverError, match="Unknown LLM driver"):
            resolve_llm_driver(explicit="ollama")

    def test_manifest_auto_is_not_literal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A manifest saying "auto" resolves, never returns "auto"."""
        _no_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert resolve_llm_driver(manifest_driver="auto") == "anthropic-api"

    def test_explicit_cli_refused_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A deployed app must never resolve onto a developer subscription."""
        _no_env(monkeypatch)
        monkeypatch.setenv("DAZZLE_ENV", "production")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            with pytest.raises(LLMDriverError, match="development only"):
                resolve_llm_driver(explicit="claude-cli")

    def test_auto_cli_fallback_refused_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """auto + no key + CLI present must still refuse under production —
        the silent-fallback variant of the same guarantee."""
        _no_env(monkeypatch)
        monkeypatch.setenv("DAZZLE_ENV", "production")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            with pytest.raises(LLMDriverError, match="development only"):
                resolve_llm_driver()


class TestCallClaudeCli:
    def _completed(self, stdout: str) -> MagicMock:
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = stdout
        proc.stderr = ""
        return proc

    def test_strips_api_key_and_claudecode_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Billing guarantee: the CLI subprocess must never see the API
        key (would silently bill it) nor CLAUDECODE (would refuse to
        start inside a Claude Code session)."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
        monkeypatch.setenv("CLAUDECODE", "1")
        with patch("dazzle.llm.driver.subprocess.run") as mock_run:
            mock_run.return_value = self._completed('{"result": "ok"}')
            call_claude_cli("hi")
        env = mock_run.call_args.kwargs["env"]
        assert "ANTHROPIC_API_KEY" not in env
        assert "CLAUDECODE" not in env

    def test_passes_model_and_system_prompt(self) -> None:
        with patch("dazzle.llm.driver.subprocess.run") as mock_run:
            mock_run.return_value = self._completed('{"result": "ok"}')
            call_claude_cli("hi", system_prompt="be brief", model="claude-x")
        cmd = mock_run.call_args.args[0]
        assert cmd[:2] == ["claude", "--print"]
        assert "--system-prompt" in cmd and "be brief" in cmd
        assert "--model" in cmd and "claude-x" in cmd
        # Pure-completion contract: no built-ins, no MCP servers, deny-all
        # permissions — a visible tool eventually gets a tool_use turn
        # instead of text and the call dies as error_max_turns.
        assert "--tools" in cmd and "" in cmd
        assert "--strict-mcp-config" in cmd
        assert "--disallowedTools" in cmd and "*" in cmd
        # The prompt travels over stdin, never argv — flattened agent
        # history can exceed the macOS 256 KB per-argument kernel limit.
        assert "hi" not in cmd
        assert mock_run.call_args.kwargs["input"] == "hi"

    def test_refused_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        with pytest.raises(LLMDriverError, match="console.anthropic.com"):
            call_claude_cli("hi")

    def test_parses_json_envelope_with_usage(self) -> None:
        envelope = json.dumps(
            {"result": "the answer", "usage": {"input_tokens": 10, "output_tokens": 5}}
        )
        with patch("dazzle.llm.driver.subprocess.run") as mock_run:
            mock_run.return_value = self._completed(envelope)
            text, tokens = call_claude_cli("hi")
        assert text == "the answer"
        assert tokens == 15

    def test_nonzero_exit_raises_with_signin_hint(self) -> None:
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "not logged in"
        with patch("dazzle.llm.driver.subprocess.run", return_value=proc):
            with pytest.raises(LLMDriverError, match="signed in"):
                call_claude_cli("hi")

    def test_timeout_raises(self) -> None:
        with patch(
            "dazzle.llm.driver.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300),
        ):
            with pytest.raises(LLMDriverError, match="timed out"):
                call_claude_cli("hi")


class TestParseCliJsonOutput:
    def test_plain_text_falls_through(self) -> None:
        assert _parse_cli_json_output("just text\n") == ("just text", 0)

    def test_envelope_without_usage(self) -> None:
        assert _parse_cli_json_output('{"result": "r"}') == ("r", 0)

    def test_non_dict_json_raises(self) -> None:
        """JSON of the wrong shape must fail loudly — handing a structured
        envelope to callers as 'response text' breaks far from the cause."""
        with pytest.raises(LLMDriverError, match="unexpected shape"):
            _parse_cli_json_output('["a"]')

    def test_envelope_with_non_string_result_raises(self) -> None:
        with pytest.raises(LLMDriverError, match="unexpected shape"):
            _parse_cli_json_output('{"result": 42}')


class TestManifestLlmConfig:
    def test_llm_section_parsed(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            '[project]\nname = "x"\nroot = "x.core"\n\n[llm]\ndriver = "claude-cli"\n',
            encoding="utf-8",
        )
        assert load_manifest(toml).llm.driver == "claude-cli"

    def test_llm_section_defaults_to_auto(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text('[project]\nname = "x"\nroot = "x.core"\n', encoding="utf-8")
        assert load_manifest(toml).llm.driver == "auto"

    def test_blank_template_pins_claude_cli(self) -> None:
        """dazzle init's blank template must default new projects to the
        subscription driver — evaluating Dazzle requires no API credit."""
        from pathlib import Path

        import dazzle

        template = Path(dazzle.__file__).parent / "templates" / "blank" / "dazzle.toml"
        content = template.read_text(encoding="utf-8")
        assert "[llm]" in content
        assert 'driver = "claude-cli"' in content
