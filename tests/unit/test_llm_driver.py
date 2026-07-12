"""Tests for multi-provider LLM driver resolution and subscription CLI shell-outs.

Drivers decide who pays for cognition — a developer's subscription
(claude-cli / grok-cli) or the metered Anthropic API (anthropic-api) —
so the resolution order and the subprocess billing guarantees are
contract, not implementation detail.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dazzle.llm.driver import (
    DRIVER_CLAUDE_CLI,
    DRIVER_GROK_CLI,
    LLMDriverError,
    _parse_cli_json_output,
    call_claude_cli,
    call_grok_cli,
    call_subscription_cli,
    is_subscription_driver,
    pick_available_subscription_driver,
    resolve_llm_driver,
)


def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DAZZLE_LLM_DRIVER", raising=False)
    monkeypatch.delenv("DAZZLE_ENV", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)


class TestIsSubscriptionDriver:
    def test_cli_drivers_are_subscription(self) -> None:
        assert is_subscription_driver("claude-cli")
        assert is_subscription_driver("grok-cli")
        assert not is_subscription_driver("anthropic-api")
        assert not is_subscription_driver("auto")


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

    def test_manifest_grok_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
            assert resolve_llm_driver(manifest_driver="grok-cli") == "grok-cli"

    def test_auto_prefers_api_key_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
                assert resolve_llm_driver() == "anthropic-api"

    def test_auto_falls_back_to_claude_cli_without_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
                assert resolve_llm_driver() == "claude-cli"

    def test_auto_falls_back_to_grok_when_only_grok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=False):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
                assert resolve_llm_driver() == "grok-cli"

    def test_auto_with_neither_raises_with_all_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.claude_cli_available", return_value=False):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=False):
                with pytest.raises(LLMDriverError) as exc:
                    resolve_llm_driver()
        msg = str(exc.value)
        assert "claude.com/claude-code" in msg
        assert "grok" in msg.lower()
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

    def test_grok_requested_without_cli_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        with patch("dazzle.llm.driver.grok_cli_available", return_value=False):
            with pytest.raises(LLMDriverError, match="Grok Build CLI"):
                resolve_llm_driver(explicit="grok-cli")

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

    def test_explicit_grok_refused_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_env(monkeypatch)
        monkeypatch.setenv("DAZZLE_ENV", "production")
        with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
            with pytest.raises(LLMDriverError, match="development only"):
                resolve_llm_driver(explicit="grok-cli")

    def test_auto_cli_fallback_refused_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """auto + no key + CLI present must still refuse under production —
        the silent-fallback variant of the same guarantee."""
        _no_env(monkeypatch)
        monkeypatch.setenv("DAZZLE_ENV", "production")
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            with pytest.raises(LLMDriverError, match="development only"):
                resolve_llm_driver()


class TestPickAvailableSubscriptionDriver:
    def test_prefers_claude_when_both(self) -> None:
        with patch("dazzle.llm.driver.claude_cli_available", return_value=True):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
                assert pick_available_subscription_driver() == DRIVER_CLAUDE_CLI

    def test_grok_when_only_grok(self) -> None:
        with patch("dazzle.llm.driver.claude_cli_available", return_value=False):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
                assert pick_available_subscription_driver() == DRIVER_GROK_CLI

    def test_none_when_neither(self) -> None:
        with patch("dazzle.llm.driver.claude_cli_available", return_value=False):
            with patch("dazzle.llm.driver.grok_cli_available", return_value=False):
                assert pick_available_subscription_driver() is None


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
        assert "--tools" in cmd and "" in cmd
        assert "--strict-mcp-config" in cmd
        assert "--disallowedTools" in cmd and "*" in cmd
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


class TestCallGrokCli:
    def _completed(self, stdout: str) -> MagicMock:
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = stdout
        proc.stderr = ""
        return proc

    def test_strips_metered_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("XAI_API_KEY", "xai-secret")
        monkeypatch.setenv("GROK_API_KEY", "grok-secret")
        with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
            with patch("dazzle.llm.driver.subprocess.run") as mock_run:
                mock_run.return_value = self._completed('{"result": "ok"}')
                call_grok_cli("hi")
        env = mock_run.call_args.kwargs["env"]
        assert "ANTHROPIC_API_KEY" not in env
        assert "XAI_API_KEY" not in env
        assert "GROK_API_KEY" not in env

    def test_passes_model_and_system_prompt(self) -> None:
        with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
            with patch("dazzle.llm.driver.subprocess.run") as mock_run:
                mock_run.return_value = self._completed('{"result": "ok"}')
                call_grok_cli("hi", system_prompt="be brief", model="grok-4.5")
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "grok"
        assert "--single" in cmd and "hi" in cmd
        assert "--system-prompt-override" in cmd and "be brief" in cmd
        assert "--model" in cmd and "grok-4.5" in cmd
        assert "--output-format" in cmd and "json" in cmd
        assert "--disallowed-tools" in cmd and "*" in cmd

    def test_long_prompt_uses_prompt_file(self) -> None:
        long = "x" * 3000
        with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
            with patch("dazzle.llm.driver.subprocess.run") as mock_run:
                mock_run.return_value = self._completed('{"result": "ok"}')
                call_grok_cli(long)
        cmd = mock_run.call_args.args[0]
        assert "--prompt-file" in cmd
        assert "--single" not in cmd

    def test_refused_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        with pytest.raises(LLMDriverError, match="development only"):
            call_grok_cli("hi")

    def test_parses_grok_shaped_response_field(self) -> None:
        with patch("dazzle.llm.driver.grok_cli_available", return_value=True):
            with patch("dazzle.llm.driver.subprocess.run") as mock_run:
                mock_run.return_value = self._completed('{"response": "from grok"}')
                text, tokens = call_grok_cli("hi")
        assert text == "from grok"
        assert tokens == 0


class TestCallSubscriptionCli:
    def test_dispatches_to_claude(self) -> None:
        with patch("dazzle.llm.driver.call_claude_cli", return_value=("c", 1)) as mock:
            assert call_subscription_cli(DRIVER_CLAUDE_CLI, "p") == ("c", 1)
            mock.assert_called_once()

    def test_dispatches_to_grok(self) -> None:
        with patch("dazzle.llm.driver.call_grok_cli", return_value=("g", 2)) as mock:
            assert call_subscription_cli(DRIVER_GROK_CLI, "p") == ("g", 2)
            mock.assert_called_once()

    def test_rejects_api_driver(self) -> None:
        with pytest.raises(LLMDriverError, match="not a subscription"):
            call_subscription_cli("anthropic-api", "p")


class TestParseCliJsonOutput:
    def test_plain_text_falls_through(self) -> None:
        assert _parse_cli_json_output("just text\n") == ("just text", 0)

    def test_envelope_without_usage(self) -> None:
        assert _parse_cli_json_output('{"result": "r"}') == ("r", 0)

    def test_non_dict_json_raises(self) -> None:
        with pytest.raises(LLMDriverError, match="unexpected shape"):
            _parse_cli_json_output('["a"]')

    def test_envelope_with_non_string_result_raises(self) -> None:
        with pytest.raises(LLMDriverError, match="unexpected shape"):
            _parse_cli_json_output('{"result": 42}')

    def test_total_tokens_field(self) -> None:
        assert _parse_cli_json_output('{"text": "ok", "usage": {"total_tokens": 9}}') == (
            "ok",
            9,
        )


class TestManifestLlmConfig:
    def test_llm_section_parsed(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            '[project]\nname = "x"\nroot = "x.core"\n\n[llm]\ndriver = "claude-cli"\n',
            encoding="utf-8",
        )
        assert load_manifest(toml).llm.driver == "claude-cli"

    def test_llm_section_grok_cli(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            '[project]\nname = "x"\nroot = "x.core"\n\n[llm]\ndriver = "grok-cli"\n',
            encoding="utf-8",
        )
        assert load_manifest(toml).llm.driver == "grok-cli"

    def test_llm_section_defaults_to_auto(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text('[project]\nname = "x"\nroot = "x.core"\n', encoding="utf-8")
        assert load_manifest(toml).llm.driver == "auto"

    def test_blank_template_uses_auto(self) -> None:
        """dazzle init's blank template must default to auto so either
        subscription CLI (or an API key) works without editing dazzle.toml."""
        from pathlib import Path

        import dazzle

        template = Path(dazzle.__file__).parent / "templates" / "blank" / "dazzle.toml"
        content = template.read_text(encoding="utf-8")
        assert "[llm]" in content
        assert 'driver = "auto"' in content
        assert "grok-cli" in content
