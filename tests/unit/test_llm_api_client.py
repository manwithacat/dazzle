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
