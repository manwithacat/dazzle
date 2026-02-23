"""Tests for AI cost tracking and gateway (#376).

Tests the new LLM IR fields (budget_alert_usd, default_provider, vision,
description), DSL parsing of those fields, and AIJob auto-generation.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from textwrap import dedent

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.llm import AI_JOB_FIELDS
from dazzle.core.linker import _build_ai_job_entity, build_appspec


def _parse(dsl: str) -> ir.ModuleFragment:
    """Parse DSL text and return the fragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
    return fragment


def _parse_module(dsl: str) -> ir.ModuleIR:
    """Parse DSL text and return a full ModuleIR."""
    module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dz"))
    return ir.ModuleIR(
        name=module_name or "test_app",
        file=Path("test.dz"),
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )


# =============================================================================
# IR Tests
# =============================================================================


class TestAIJobFields:
    """Tests for AI_JOB_FIELDS constant."""

    def test_field_count(self) -> None:
        assert len(AI_JOB_FIELDS) == 14

    def test_has_id_pk(self) -> None:
        name, type_str, modifiers, _ = AI_JOB_FIELDS[0]
        assert name == "id"
        assert type_str == "uuid"
        assert "pk" in modifiers

    def test_has_cost_usd(self) -> None:
        cost_field = next(f for f in AI_JOB_FIELDS if f[0] == "cost_usd")
        assert cost_field[1] == "decimal(12,6)"

    def test_has_status_enum(self) -> None:
        status_field = next(f for f in AI_JOB_FIELDS if f[0] == "status")
        assert "enum[" in status_field[1]
        assert "pending" in status_field[1]
        assert "completed" in status_field[1]


# =============================================================================
# AIJob Entity Builder Tests
# =============================================================================


class TestBuildAIJobEntity:
    """Tests for _build_ai_job_entity()."""

    def test_entity_name(self) -> None:
        entity = _build_ai_job_entity()
        assert entity.name == "AIJob"
        assert entity.title == "AI Job"

    def test_entity_metadata(self) -> None:
        entity = _build_ai_job_entity()
        assert entity.domain == "platform"
        assert "system" in entity.patterns

    def test_field_count(self) -> None:
        entity = _build_ai_job_entity()
        assert len(entity.fields) == 14

    def test_id_field(self) -> None:
        entity = _build_ai_job_entity()
        id_field = entity.fields[0]
        assert id_field.name == "id"
        assert id_field.is_primary_key

    def test_cost_usd_field(self) -> None:
        entity = _build_ai_job_entity()
        cost_field = next(f for f in entity.fields if f.name == "cost_usd")
        assert cost_field.type.kind.value == "decimal"
        assert cost_field.type.precision == 12
        assert cost_field.type.scale == 6

    def test_status_field(self) -> None:
        entity = _build_ai_job_entity()
        status_field = next(f for f in entity.fields if f.name == "status")
        assert status_field.type.kind.value == "enum"
        assert "pending" in status_field.type.enum_values
        assert "completed" in status_field.type.enum_values
        assert "failed" in status_field.type.enum_values
        assert status_field.default == "pending"


# =============================================================================
# Parser Tests
# =============================================================================


class TestParseLLMConfigNewFields:
    """Tests for parsing new llm_config fields."""

    def test_budget_alert_usd(self) -> None:
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_config:
              default_model: claude_sonnet
              budget_alert_usd: 50.00
        """)
        fragment = _parse(dsl)
        config = fragment.llm_config
        assert config is not None
        assert config.budget_alert_usd == Decimal("50.00")

    def test_default_provider(self) -> None:
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_config:
              default_provider: anthropic
              default_model: claude_sonnet
        """)
        fragment = _parse(dsl)
        config = fragment.llm_config
        assert config is not None
        assert config.default_provider == ir.LLMProvider.ANTHROPIC

    def test_all_new_config_fields(self) -> None:
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_config:
              default_provider: openai
              default_model: gpt4o
              budget_alert_usd: 100.00
              artifact_store: s3
        """)
        fragment = _parse(dsl)
        config = fragment.llm_config
        assert config is not None
        assert config.default_provider == ir.LLMProvider.OPENAI
        assert config.default_model == "gpt4o"
        assert config.budget_alert_usd == Decimal("100.00")
        assert config.artifact_store == ir.ArtifactStore.S3


class TestParseLLMIntentNewFields:
    """Tests for parsing new llm_intent fields."""

    def test_vision_flag(self) -> None:
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_intent verify_doc "Verify Document":
              model: claude_sonnet
              prompt: "Verify this document"
              vision: true
        """)
        fragment = _parse(dsl)
        intent = fragment.llm_intents[0]
        assert intent.vision is True

    def test_description_field(self) -> None:
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_intent classify_doc "Classify Document":
              model: claude_haiku
              prompt: "Classify this"
              description: "Classify uploaded document type for KYC pipeline"
        """)
        fragment = _parse(dsl)
        intent = fragment.llm_intents[0]
        assert intent.description == "Classify uploaded document type for KYC pipeline"

    def test_intent_without_prompt(self) -> None:
        """Intent without prompt is now valid (routing-only)."""
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_intent classify_doc "Classify Document":
              model: claude_haiku
              description: "Classify uploaded document type"
              vision: true
        """)
        fragment = _parse(dsl)
        intent = fragment.llm_intents[0]
        assert intent.prompt_template == ""
        assert intent.vision is True
        assert intent.description == "Classify uploaded document type"

    def test_max_tokens_on_intent(self) -> None:
        """max_tokens on intent is accepted (convenience, not stored)."""
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_intent summarize "Summarize":
              model: claude_sonnet
              prompt: "Summarize this"
              max_tokens: 500
        """)
        fragment = _parse(dsl)
        intent = fragment.llm_intents[0]
        assert intent.name == "summarize"

    def test_full_ai_gateway_style(self) -> None:
        """Test the full ai_gateway-style DSL from issue #376."""
        dsl = dedent("""\
            module kyc_app
            app kyc "KYC Platform"

            llm_model claude_haiku "Claude Haiku":
              provider: anthropic
              model_id: "claude-haiku-4-5-20251001"
              tier: fast
              max_tokens: 500
              cost_per_1k_input: 0.00025
              cost_per_1k_output: 0.00125

            llm_model claude_sonnet "Claude Sonnet":
              provider: anthropic
              model_id: "claude-sonnet-4-20250514"
              tier: balanced
              max_tokens: 4096
              cost_per_1k_input: 0.003
              cost_per_1k_output: 0.015

            llm_config:
              default_provider: anthropic
              default_model: claude_sonnet
              budget_alert_usd: 50.00

            llm_intent classify_document "Classify Document":
              model: claude_haiku
              description: "Classify uploaded document type"
              max_tokens: 500
              prompt: "Classify this document"

            llm_intent verify_identity "Verify Identity":
              model: claude_sonnet
              description: "KYC document verification with vision"
              vision: true
              prompt: "Verify this identity document"
              max_tokens: 2000

            llm_intent assess_risk "Assess Risk":
              model: claude_sonnet
              description: "Risk assessment narrative generation"
              prompt: "Assess risk for this entity"
              max_tokens: 1500
        """)
        fragment = _parse(dsl)

        # Config
        assert fragment.llm_config is not None
        assert fragment.llm_config.default_provider == ir.LLMProvider.ANTHROPIC
        assert fragment.llm_config.budget_alert_usd == Decimal("50.00")

        # Models
        assert len(fragment.llm_models) == 2
        haiku = next(m for m in fragment.llm_models if m.name == "claude_haiku")
        assert haiku.tier == ir.ModelTier.FAST
        assert haiku.cost_per_1k_input == Decimal("0.00025")

        # Intents
        assert len(fragment.llm_intents) == 3
        verify = next(i for i in fragment.llm_intents if i.name == "verify_identity")
        assert verify.vision is True
        assert verify.description == "KYC document verification with vision"

        classify = next(i for i in fragment.llm_intents if i.name == "classify_document")
        assert classify.vision is False
        assert classify.model_ref == "claude_haiku"


# =============================================================================
# Linker Tests — AIJob Auto-Generation
# =============================================================================


class TestAIJobAutoGeneration:
    """Tests for AIJob entity auto-generation in the linker."""

    def test_ai_job_generated_with_llm_config(self) -> None:
        """AIJob entity is auto-generated when llm_config is present."""
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_model claude_sonnet "Claude Sonnet":
              provider: anthropic
              model_id: "claude-sonnet-4-20250514"

            llm_config:
              default_model: claude_sonnet

            entity Task "Task":
              id: uuid pk
              title: str(200) required
        """)
        module = _parse_module(dsl)
        appspec = build_appspec([module], "test_app")

        ai_job = appspec.get_entity("AIJob")
        assert ai_job is not None
        assert ai_job.name == "AIJob"
        assert ai_job.domain == "platform"

        # Verify key fields
        field_names = [f.name for f in ai_job.fields]
        assert "id" in field_names
        assert "intent" in field_names
        assert "cost_usd" in field_names
        assert "tokens_in" in field_names
        assert "tokens_out" in field_names
        assert "status" in field_names
        assert "entity_type" in field_names
        assert "user_id" in field_names

    def test_no_ai_job_without_llm_config(self) -> None:
        """AIJob entity is NOT generated when llm_config is absent."""
        dsl = dedent("""\
            module test_app
            app test "Test"

            entity Task "Task":
              id: uuid pk
              title: str(200) required
        """)
        module = _parse_module(dsl)
        appspec = build_appspec([module], "test_app")

        assert appspec.get_entity("AIJob") is None

    def test_user_defined_ai_job_not_overwritten(self) -> None:
        """User-defined AIJob entity takes precedence over auto-generated."""
        dsl = dedent("""\
            module test_app
            app test "Test"

            llm_model claude_sonnet "Claude Sonnet":
              provider: anthropic
              model_id: "claude-sonnet-4-20250514"

            llm_config:
              default_model: claude_sonnet

            entity AIJob "Custom AI Job":
              id: uuid pk
              custom_field: str(200) required
        """)
        module = _parse_module(dsl)
        appspec = build_appspec([module], "test_app")

        ai_job = appspec.get_entity("AIJob")
        assert ai_job is not None
        assert ai_job.title == "Custom AI Job"
        # Should have the user's custom field, not auto-generated fields
        field_names = [f.name for f in ai_job.fields]
        assert "custom_field" in field_names
