"""
Unit tests for LLM IR types.

Tests the IR types defined in src/dazzle/core/ir/llm.py for Issue #33.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from dazzle.core.ir import (
    ArtifactKind,
    ArtifactRefSpec,
    ArtifactStore,
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
    LoggingPolicySpec,
    ModelTier,
    PIIAction,
    PIIPolicySpec,
    RetryBackoff,
    RetryPolicySpec,
)

# =============================================================================
# RetryPolicySpec Tests
# =============================================================================


class TestRetryPolicySpec:
    """Tests for RetryPolicySpec."""

    def test_default_values(self):
        """Test default values are set correctly."""
        policy = RetryPolicySpec()

        assert policy.max_attempts == 3
        assert policy.backoff == RetryBackoff.EXPONENTIAL
        assert policy.initial_delay_ms == 1000
        assert policy.max_delay_ms == 30000

    def test_custom_values(self):
        """Test custom values are accepted."""
        policy = RetryPolicySpec(
            max_attempts=5,
            backoff=RetryBackoff.LINEAR,
            initial_delay_ms=500,
            max_delay_ms=60000,
        )

        assert policy.max_attempts == 5
        assert policy.backoff == RetryBackoff.LINEAR
        assert policy.initial_delay_ms == 500
        assert policy.max_delay_ms == 60000

    def test_max_attempts_validation(self):
        """Test max_attempts bounds validation."""
        # Too low
        with pytest.raises(ValueError):
            RetryPolicySpec(max_attempts=0)

        # Too high
        with pytest.raises(ValueError):
            RetryPolicySpec(max_attempts=11)

        # Valid bounds
        assert RetryPolicySpec(max_attempts=1).max_attempts == 1
        assert RetryPolicySpec(max_attempts=10).max_attempts == 10

    def test_is_frozen(self):
        """Test that the model is frozen (immutable)."""
        policy = RetryPolicySpec()
        with pytest.raises(ValidationError):
            policy.max_attempts = 5


# =============================================================================
# PIIPolicySpec Tests
# =============================================================================


class TestPIIPolicySpec:
    """Tests for PIIPolicySpec."""

    def test_default_values(self):
        """Test default values."""
        policy = PIIPolicySpec()

        assert policy.scan is False
        assert policy.action == PIIAction.WARN
        assert policy.patterns == []

    def test_custom_values(self):
        """Test custom values."""
        policy = PIIPolicySpec(
            scan=True,
            action=PIIAction.REDACT,
            patterns=[r"\d{3}-\d{2}-\d{4}"],  # SSN pattern
        )

        assert policy.scan is True
        assert policy.action == PIIAction.REDACT
        assert len(policy.patterns) == 1


# =============================================================================
# LoggingPolicySpec Tests
# =============================================================================


class TestLoggingPolicySpec:
    """Tests for LoggingPolicySpec."""

    def test_default_values(self):
        """Test default values (all logging enabled by default)."""
        policy = LoggingPolicySpec()

        assert policy.log_prompts is True
        assert policy.log_completions is True
        assert policy.redact_pii is True

    def test_custom_values(self):
        """Test disabling logging options."""
        policy = LoggingPolicySpec(
            log_prompts=False,
            log_completions=False,
            redact_pii=False,
        )

        assert policy.log_prompts is False
        assert policy.log_completions is False
        assert policy.redact_pii is False


# =============================================================================
# LLMModelSpec Tests
# =============================================================================


class TestLLMModelSpec:
    """Tests for LLMModelSpec."""

    def test_minimal_model(self):
        """Test minimal model definition."""
        model = LLMModelSpec(
            name="claude_sonnet",
            provider=LLMProvider.ANTHROPIC,
            model_id="claude-3-5-sonnet-20241022",
        )

        assert model.name == "claude_sonnet"
        assert model.title is None
        assert model.provider == LLMProvider.ANTHROPIC
        assert model.model_id == "claude-3-5-sonnet-20241022"
        assert model.tier == ModelTier.BALANCED
        assert model.max_tokens == 4096
        assert model.cost_per_1k_input is None
        assert model.cost_per_1k_output is None

    def test_full_model(self):
        """Test full model definition with all fields."""
        model = LLMModelSpec(
            name="gpt4o",
            title="GPT-4o (Latest)",
            provider=LLMProvider.OPENAI,
            model_id="gpt-4o",
            tier=ModelTier.QUALITY,
            max_tokens=8192,
            cost_per_1k_input=Decimal("0.005"),
            cost_per_1k_output=Decimal("0.015"),
        )

        assert model.name == "gpt4o"
        assert model.title == "GPT-4o (Latest)"
        assert model.provider == LLMProvider.OPENAI
        assert model.tier == ModelTier.QUALITY
        assert model.max_tokens == 8192
        assert model.cost_per_1k_input == Decimal("0.005")
        assert model.cost_per_1k_output == Decimal("0.015")

    def test_all_providers(self):
        """Test all provider enum values work."""
        providers = [
            LLMProvider.ANTHROPIC,
            LLMProvider.OPENAI,
            LLMProvider.GOOGLE,
            LLMProvider.LOCAL,
        ]

        for provider in providers:
            model = LLMModelSpec(
                name=f"test_{provider.value}",
                provider=provider,
                model_id="test-model",
            )
            assert model.provider == provider

    def test_all_tiers(self):
        """Test all tier enum values work."""
        tiers = [ModelTier.FAST, ModelTier.BALANCED, ModelTier.QUALITY]

        for tier in tiers:
            model = LLMModelSpec(
                name=f"test_{tier.value}",
                provider=LLMProvider.ANTHROPIC,
                model_id="test-model",
                tier=tier,
            )
            assert model.tier == tier

    def test_max_tokens_validation(self):
        """Test max_tokens must be positive."""
        with pytest.raises(ValueError):
            LLMModelSpec(
                name="test",
                provider=LLMProvider.ANTHROPIC,
                model_id="test",
                max_tokens=0,
            )

    def test_empty_model_id_validation(self):
        """Test model_id cannot be empty."""
        with pytest.raises(ValueError):
            LLMModelSpec(
                name="test",
                provider=LLMProvider.ANTHROPIC,
                model_id="",
            )

        with pytest.raises(ValueError):
            LLMModelSpec(
                name="test",
                provider=LLMProvider.ANTHROPIC,
                model_id="   ",
            )


# =============================================================================
# LLMConfigSpec Tests
# =============================================================================


class TestLLMConfigSpec:
    """Tests for LLMConfigSpec."""

    def test_default_values(self):
        """Test default configuration."""
        config = LLMConfigSpec()

        assert config.default_model is None
        assert config.artifact_store == ArtifactStore.LOCAL
        assert config.logging is not None
        assert config.logging.log_prompts is True
        assert config.rate_limits is None

    def test_custom_config(self):
        """Test custom configuration."""
        config = LLMConfigSpec(
            default_model="claude_sonnet",
            artifact_store=ArtifactStore.S3,
            logging=LoggingPolicySpec(log_prompts=False),
            rate_limits={"claude_sonnet": 60, "gpt4o": 30},
        )

        assert config.default_model == "claude_sonnet"
        assert config.artifact_store == ArtifactStore.S3
        assert config.logging.log_prompts is False
        assert config.rate_limits == {"claude_sonnet": 60, "gpt4o": 30}


# =============================================================================
# LLMIntentSpec Tests
# =============================================================================


class TestLLMIntentSpec:
    """Tests for LLMIntentSpec."""

    def test_minimal_intent(self):
        """Test minimal intent definition."""
        intent = LLMIntentSpec(
            name="summarize",
            prompt_template="Summarize: {{ input.text }}",
        )

        assert intent.name == "summarize"
        assert intent.title is None
        assert intent.model_ref is None
        assert intent.prompt_template == "Summarize: {{ input.text }}"
        assert intent.output_schema is None
        assert intent.timeout_seconds == 30
        assert intent.retry is None
        assert intent.pii is None

    def test_full_intent(self):
        """Test full intent definition."""
        intent = LLMIntentSpec(
            name="extract_entities",
            title="Extract Named Entities",
            model_ref="claude_sonnet",
            prompt_template="Extract entities from: {{ input.text }}",
            output_schema="EntityList",
            timeout_seconds=60,
            retry=RetryPolicySpec(max_attempts=5),
            pii=PIIPolicySpec(scan=True, action=PIIAction.REDACT),
        )

        assert intent.name == "extract_entities"
        assert intent.title == "Extract Named Entities"
        assert intent.model_ref == "claude_sonnet"
        assert intent.output_schema == "EntityList"
        assert intent.timeout_seconds == 60
        assert intent.retry is not None
        assert intent.retry.max_attempts == 5
        assert intent.pii is not None
        assert intent.pii.scan is True

    def test_empty_prompt_validation(self):
        """Test prompt_template cannot be empty."""
        with pytest.raises(ValueError):
            LLMIntentSpec(
                name="test",
                prompt_template="",
            )

        with pytest.raises(ValueError):
            LLMIntentSpec(
                name="test",
                prompt_template="   ",
            )

    def test_timeout_validation(self):
        """Test timeout_seconds bounds."""
        # Too low
        with pytest.raises(ValueError):
            LLMIntentSpec(
                name="test",
                prompt_template="test",
                timeout_seconds=0,
            )

        # Too high
        with pytest.raises(ValueError):
            LLMIntentSpec(
                name="test",
                prompt_template="test",
                timeout_seconds=301,
            )

        # Valid bounds
        assert (
            LLMIntentSpec(
                name="test",
                prompt_template="test",
                timeout_seconds=1,
            ).timeout_seconds
            == 1
        )

        assert (
            LLMIntentSpec(
                name="test",
                prompt_template="test",
                timeout_seconds=300,
            ).timeout_seconds
            == 300
        )


# =============================================================================
# ArtifactRefSpec Tests
# =============================================================================


class TestArtifactRefSpec:
    """Tests for ArtifactRefSpec."""

    def test_artifact_ref(self):
        """Test artifact reference creation."""
        ref = ArtifactRefSpec(
            artifact_id="art_123456",
            content_hash="sha256:abc123...",
            storage_uri="s3://bucket/prompts/art_123456",
            kind=ArtifactKind.PROMPT,
            byte_size=1024,
        )

        assert ref.artifact_id == "art_123456"
        assert ref.content_hash == "sha256:abc123..."
        assert ref.storage_uri == "s3://bucket/prompts/art_123456"
        assert ref.kind == ArtifactKind.PROMPT
        assert ref.byte_size == 1024

    def test_all_artifact_kinds(self):
        """Test all artifact kind values."""
        kinds = [
            ArtifactKind.PROMPT,
            ArtifactKind.COMPLETION,
            ArtifactKind.TOOL_CALL,
            ArtifactKind.TOOL_RESULT,
        ]

        for kind in kinds:
            ref = ArtifactRefSpec(
                artifact_id="test",
                content_hash="test",
                storage_uri="test",
                kind=kind,
                byte_size=0,
            )
            assert ref.kind == kind


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests for enum values and string representation."""

    def test_llm_provider_values(self):
        """Test LLMProvider enum values."""
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.GOOGLE.value == "google"
        assert LLMProvider.LOCAL.value == "local"

    def test_model_tier_values(self):
        """Test ModelTier enum values."""
        assert ModelTier.FAST.value == "fast"
        assert ModelTier.BALANCED.value == "balanced"
        assert ModelTier.QUALITY.value == "quality"

    def test_retry_backoff_values(self):
        """Test RetryBackoff enum values."""
        assert RetryBackoff.LINEAR.value == "linear"
        assert RetryBackoff.EXPONENTIAL.value == "exponential"

    def test_pii_action_values(self):
        """Test PIIAction enum values."""
        assert PIIAction.WARN.value == "warn"
        assert PIIAction.REDACT.value == "redact"
        assert PIIAction.REJECT.value == "reject"

    def test_artifact_store_values(self):
        """Test ArtifactStore enum values."""
        assert ArtifactStore.LOCAL.value == "local"
        assert ArtifactStore.S3.value == "s3"
        assert ArtifactStore.GCS.value == "gcs"

    def test_artifact_kind_values(self):
        """Test ArtifactKind enum values."""
        assert ArtifactKind.PROMPT.value == "prompt"
        assert ArtifactKind.COMPLETION.value == "completion"
        assert ArtifactKind.TOOL_CALL.value == "tool_call"
        assert ArtifactKind.TOOL_RESULT.value == "tool_result"
