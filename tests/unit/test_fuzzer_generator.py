"""Tests for Haiku-based DSL generator."""

from unittest.mock import MagicMock, patch

from dazzle.testing.fuzzer.generator import (
    PROMPT_VARIATIONS,
    build_generation_prompt,
    generate_samples,
)


class TestPromptConstruction:
    def test_prompt_includes_grammar_summary(self) -> None:
        prompt = build_generation_prompt(
            seed_dsl='entity Task "Task":\n  id: uuid pk\n',
            variation="entity-heavy",
        )
        assert "entity" in prompt
        assert "surface" in prompt

    def test_prompt_includes_seed_dsl(self) -> None:
        seed = 'entity Task "Task":\n  id: uuid pk\n'
        prompt = build_generation_prompt(seed_dsl=seed, variation="entity-heavy")
        assert seed in prompt

    def test_all_variations_produce_valid_prompts(self) -> None:
        seed = 'entity Task "Task":\n  id: uuid pk\n'
        for variation in PROMPT_VARIATIONS:
            prompt = build_generation_prompt(seed_dsl=seed, variation=variation)
            assert len(prompt) > 100


class TestGenerateSamples:
    @patch("dazzle.testing.fuzzer.generator.anthropic")
    def test_generate_returns_list_of_strings(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='entity Foo "Foo":\n  id: uuid pk\n')]
        mock_client.messages.create.return_value = mock_response

        samples = generate_samples(
            seed_dsl='entity Task "Task":\n  id: uuid pk\n',
            count=2,
        )
        assert isinstance(samples, list)
        assert len(samples) == 2
        assert all(isinstance(s, str) for s in samples)

    @patch("dazzle.testing.fuzzer.generator.anthropic")
    def test_generate_cycles_through_variations(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='entity Bar "Bar":\n  id: uuid pk\n')]
        mock_client.messages.create.return_value = mock_response

        count = len(PROMPT_VARIATIONS) + 2
        samples = generate_samples(
            seed_dsl='entity Task "Task":\n  id: uuid pk\n',
            count=count,
        )
        assert len(samples) == count
