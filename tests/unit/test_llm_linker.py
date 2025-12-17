"""
Unit tests for LLM linker validation.

Tests the linker validation rules for llm_model, llm_config, and llm_intent
as part of Issue #33: LLM Jobs as First-Class Events.
"""

from pathlib import Path

import pytest

from dazzle.core.errors import LinkError
from dazzle.core.ir import (
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
    ModuleFragment,
    ModuleIR,
)
from dazzle.core.linker_impl import SymbolTable, build_symbol_table, validate_references


def make_module(
    name: str,
    llm_models: list[LLMModelSpec] | None = None,
    llm_intents: list[LLMIntentSpec] | None = None,
    llm_config: LLMConfigSpec | None = None,
) -> ModuleIR:
    """Helper to create a module with LLM constructs."""
    return ModuleIR(
        name=name,
        file=Path(f"{name}.dazzle"),
        fragment=ModuleFragment(
            llm_models=llm_models or [],
            llm_intents=llm_intents or [],
            llm_config=llm_config,
        ),
    )


class TestLLMSymbolTable:
    """Tests for LLM symbol table building."""

    def test_add_llm_model(self):
        """Test adding LLM model to symbol table."""
        symbols = SymbolTable()
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )
        symbols.add_llm_model(model, "test_module")

        assert "claude_sonnet" in symbols.llm_models
        assert symbols.llm_models["claude_sonnet"] == model

    def test_duplicate_llm_model_raises(self):
        """Test duplicate LLM model raises LinkError."""
        symbols = SymbolTable()
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )
        symbols.add_llm_model(model, "module_a")

        with pytest.raises(LinkError, match="Duplicate llm_model 'claude_sonnet'"):
            symbols.add_llm_model(model, "module_b")

    def test_add_llm_intent(self):
        """Test adding LLM intent to symbol table."""
        symbols = SymbolTable()
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
            model_ref="claude_sonnet",
        )
        symbols.add_llm_intent(intent, "test_module")

        assert "summarize" in symbols.llm_intents
        assert symbols.llm_intents["summarize"] == intent

    def test_duplicate_llm_intent_raises(self):
        """Test duplicate LLM intent raises LinkError."""
        symbols = SymbolTable()
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
        )
        symbols.add_llm_intent(intent, "module_a")

        with pytest.raises(LinkError, match="Duplicate llm_intent 'summarize'"):
            symbols.add_llm_intent(intent, "module_b")

    def test_set_llm_config(self):
        """Test setting LLM config."""
        symbols = SymbolTable()
        config = LLMConfigSpec(default_model="claude_sonnet")
        symbols.set_llm_config(config, "test_module")

        assert symbols.llm_config == config

    def test_duplicate_llm_config_raises(self):
        """Test duplicate LLM config raises LinkError."""
        symbols = SymbolTable()
        config = LLMConfigSpec(default_model="claude_sonnet")
        symbols.set_llm_config(config, "module_a")

        with pytest.raises(LinkError, match="Duplicate llm_config"):
            symbols.set_llm_config(config, "module_b")


class TestLLMBuildSymbolTable:
    """Tests for building symbol table with LLM constructs."""

    def test_build_with_llm_models(self):
        """Test building symbol table includes LLM models."""
        model = LLMModelSpec(
            name="gpt4o",
            provider=LLMProvider.OPENAI,
            model_id="gpt-4o",
        )
        module = make_module("test", llm_models=[model])

        symbols = build_symbol_table([module])

        assert "gpt4o" in symbols.llm_models

    def test_build_with_llm_intents(self):
        """Test building symbol table includes LLM intents."""
        intent = LLMIntentSpec(
            name="classify",
            prompt_template="Classify: {{ input.text }}",
        )
        module = make_module("test", llm_intents=[intent])

        symbols = build_symbol_table([module])

        assert "classify" in symbols.llm_intents

    def test_build_with_llm_config(self):
        """Test building symbol table includes LLM config."""
        config = LLMConfigSpec(default_model="claude")
        module = make_module("test", llm_config=config)

        symbols = build_symbol_table([module])

        assert symbols.llm_config == config


class TestLLMReferenceValidation:
    """Tests for LLM reference validation."""

    def test_valid_model_reference(self):
        """Test valid model reference passes validation."""
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
            model_ref="claude_sonnet",
        )
        module = make_module("test", llm_models=[model], llm_intents=[intent])

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert errors == []

    def test_invalid_model_reference(self):
        """Test invalid model reference produces error."""
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
            model_ref="nonexistent_model",
        )
        module = make_module("test", llm_intents=[intent])

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert any("nonexistent_model" in e for e in errors)

    def test_intent_without_model_or_default(self):
        """Test intent without model and no default produces error."""
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
            # No model_ref
        )
        # No llm_config with default_model
        module = make_module("test", llm_models=[model], llm_intents=[intent])

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert any("no model reference and no default_model" in e for e in errors)

    def test_intent_with_default_model(self):
        """Test intent without explicit model but with default passes."""
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
            # No explicit model_ref
        )
        config = LLMConfigSpec(default_model="claude_sonnet")
        module = make_module(
            "test",
            llm_models=[model],
            llm_intents=[intent],
            llm_config=config,
        )

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert errors == []

    def test_invalid_default_model_reference(self):
        """Test invalid default_model reference produces error."""
        config = LLMConfigSpec(default_model="nonexistent")
        module = make_module("test", llm_config=config)

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert any("default_model references unknown llm_model" in e for e in errors)

    def test_invalid_rate_limits_reference(self):
        """Test invalid rate_limits model reference produces error."""
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )
        config = LLMConfigSpec(
            rate_limits={
                "claude_sonnet": 60,  # Valid
                "nonexistent": 30,  # Invalid
            }
        )
        module = make_module("test", llm_models=[model], llm_config=config)

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert any("rate_limits references unknown llm_model 'nonexistent'" in e for e in errors)

    def test_intent_without_any_models(self):
        """Test intent defined without any models produces error."""
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
        )
        module = make_module("test", llm_intents=[intent])

        symbols = build_symbol_table([module])
        errors = validate_references(symbols)

        assert any("no llm_model(s) are available" in e for e in errors)
