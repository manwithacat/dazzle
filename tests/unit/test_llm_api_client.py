"""Tests for dazzle.llm.api_client.LLMAPIClient — minimal coverage focused on
invariants consumed by the fitness investigator runner.

The LlmClient Protocol in dazzle/fitness/investigator/runner.py declares
`run_id: str` as required. Regression test below pins that contract.
"""

from __future__ import annotations

import pytest

from dazzle.llm.api_client import LLMAPIClient, LLMProvider


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop LLMAPIClient from shelling out to Claude CLI during construction."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-dummy")


class TestLLMAPIClientRunId:
    """Regression for fitness investigator — LlmClient Protocol requires run_id."""

    def test_run_id_is_set_on_construction(self) -> None:
        client = LLMAPIClient(provider=LLMProvider.ANTHROPIC)
        assert isinstance(client.run_id, str)
        assert client.run_id  # non-empty

    def test_run_id_is_unique_per_instance(self) -> None:
        a = LLMAPIClient(provider=LLMProvider.ANTHROPIC)
        b = LLMAPIClient(provider=LLMProvider.ANTHROPIC)
        assert a.run_id != b.run_id

    def test_run_id_is_stable_for_single_instance(self) -> None:
        client = LLMAPIClient(provider=LLMProvider.ANTHROPIC)
        first = client.run_id
        # Multiple reads — never regenerates
        assert client.run_id == first
        assert client.run_id == first


class TestStripCodeFence:
    """#1219: Claude wraps JSON in markdown fences by default. Normalise
    on read so analyze-spec stops crashing on \\`\\`\\`json\\n{...}\\n\\`\\`\\` output."""

    def test_strips_fenced_json(self) -> None:
        from dazzle.llm.api_client import _strip_code_fence

        wrapped = '```json\n{"k": "v"}\n```'
        assert _strip_code_fence(wrapped) == '{"k": "v"}'

    def test_strips_bare_fence_without_language(self) -> None:
        from dazzle.llm.api_client import _strip_code_fence

        wrapped = '```\n{"k": "v"}\n```'
        assert _strip_code_fence(wrapped) == '{"k": "v"}'

    def test_strips_unfenced_response_unchanged(self) -> None:
        from dazzle.llm.api_client import _strip_code_fence

        raw = '{"k": "v"}'
        assert _strip_code_fence(raw) == '{"k": "v"}'

    def test_handles_leading_whitespace(self) -> None:
        from dazzle.llm.api_client import _strip_code_fence

        wrapped = '\n  ```json\n{"k": "v"}\n```\n'
        assert _strip_code_fence(wrapped) == '{"k": "v"}'

    def test_handles_fence_without_trailing_newline(self) -> None:
        from dazzle.llm.api_client import _strip_code_fence

        wrapped = '```json\n{"k": "v"}```'
        assert _strip_code_fence(wrapped) == '{"k": "v"}'

    def test_preserves_inner_backticks(self) -> None:
        """Inner backticks inside the JSON payload (e.g. in string values)
        must not be stripped — only the fences at the boundary."""
        from dazzle.llm.api_client import _strip_code_fence

        wrapped = '```json\n{"code": "`backtick`"}\n```'
        assert _strip_code_fence(wrapped) == '{"code": "`backtick`"}'


class TestOpenAICompatibleBaseUrl:
    """OpenAI client with custom base_url (Ollama / proxies)."""

    def test_base_url_allows_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Prevent CLI fallback from stealing the path
        monkeypatch.setattr(
            "dazzle.llm.api_client.pick_available_subscription_driver",
            lambda: None,
        )
        client = LLMAPIClient(
            provider=LLMProvider.OPENAI,
            model="llama3.2",
            base_url="http://localhost:11434/v1",
        )
        assert client.base_url == "http://localhost:11434/v1"
        assert client.api_key == "local"
        assert client.provider == LLMProvider.OPENAI

    def test_call_openai_skips_json_force_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = LLMAPIClient(provider=LLMProvider.OPENAI, model="gpt-4o-mini")

        captured: dict = {}

        class _FakeCompletions:
            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                captured.update(kwargs)

                class _Msg:
                    content = "plain text"

                class _Choice:
                    message = _Msg()

                class _Usage:
                    prompt_tokens = 3
                    completion_tokens = 5

                class _Resp:
                    choices = [_Choice()]
                    usage = _Usage()

                return _Resp()

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            chat = _FakeChat()

        client.client = _FakeClient()  # type: ignore[assignment]
        result = client.complete_with_usage("sys", "user")
        assert result.text == "plain text"
        assert "response_format" not in captured
        assert result.tokens_in == 3
        assert result.tokens_out == 5

    def test_analyze_path_can_force_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = LLMAPIClient(provider=LLMProvider.OPENAI, model="gpt-4o-mini")
        captured: dict = {}

        class _FakeCompletions:
            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                captured.update(kwargs)

                class _Msg:
                    content = '{"ok": true}'

                class _Choice:
                    message = _Msg()

                class _Usage:
                    prompt_tokens = 1
                    completion_tokens = 1

                class _Resp:
                    choices = [_Choice()]
                    usage = _Usage()

                return _Resp()

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeClient:
            chat = _FakeChat()

        client.client = _FakeClient()  # type: ignore[assignment]
        client._call_openai("sys", "user", force_json=True)
        assert captured.get("response_format") == {"type": "json_object"}


class TestVertexGoogleProvider:
    """Vertex / Gemini path (Badger-compatible ADC contract)."""

    def test_requires_project_or_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        monkeypatch.delenv("VERTEX_PROJECT", raising=False)
        monkeypatch.setattr(
            "dazzle.llm.api_client.pick_available_subscription_driver",
            lambda: None,
        )
        with pytest.raises(ValueError, match="GCP project"):
            LLMAPIClient(provider=LLMProvider.GOOGLE, model="gemini-2.5-flash")

    def test_vertex_client_built_with_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        created: dict = {}

        class _FakeGenai:
            @staticmethod
            def Client(**kwargs):  # type: ignore[no-untyped-def]
                created.update(kwargs)
                return object()

        import sys
        import types

        fake_pkg = types.ModuleType("google")
        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = _FakeGenai.Client  # type: ignore[attr-defined]
        fake_pkg.genai = fake_genai  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "google", fake_pkg)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

        client = LLMAPIClient(
            provider=LLMProvider.GOOGLE,
            model="gemini-2.5-flash",
            project="badger-payroll",
            location="europe-west2",
        )
        assert client.project == "badger-payroll"
        assert client.location == "europe-west2"
        assert created == {
            "vertexai": True,
            "project": "badger-payroll",
            "location": "europe-west2",
        }
        assert client._vertex_client is not None

    def test_call_vertex_extracts_text_and_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        class _Usage:
            prompt_token_count = 11
            candidates_token_count = 7

        class _Resp:
            text = "hello from vertex"
            usage_metadata = _Usage()

        class _Models:
            def generate_content(self, **kwargs):  # type: ignore[no-untyped-def]
                return _Resp()

        class _FakeClient:
            models = _Models()

        import sys
        import types

        fake_pkg = types.ModuleType("google")
        fake_genai = types.ModuleType("google.genai")
        fake_types = types.ModuleType("google.genai.types")

        class _Cfg:
            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                self.kwargs = kwargs

        fake_types.GenerateContentConfig = _Cfg  # type: ignore[attr-defined]
        fake_genai.Client = lambda **kw: _FakeClient()  # type: ignore[attr-defined,misc]
        fake_genai.types = fake_types  # type: ignore[attr-defined]
        fake_pkg.genai = fake_genai  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "google", fake_pkg)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

        client = LLMAPIClient(
            provider=LLMProvider.GOOGLE,
            model="gemini-2.5-flash",
            project="p",
            location="global",
        )
        result = client.complete_with_usage("system", "user")
        assert result.text == "hello from vertex"
        assert result.tokens_in == 11
        assert result.tokens_out == 7
