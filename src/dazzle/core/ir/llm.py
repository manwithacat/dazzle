"""
LLM (Large Language Model) IR types for DAZZLE.

This module contains IR types for declarative LLM orchestration,
enabling model definitions, job intents, and configuration.

Part of Issue #33: LLM Jobs as First-Class Events.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    LOCAL = "local"


class ModelTier(StrEnum):
    """Model performance/cost tier classification."""

    FAST = "fast"  # Lower latency, lower cost
    BALANCED = "balanced"  # Good balance of speed/quality
    QUALITY = "quality"  # Best quality, higher cost


class RetryBackoff(StrEnum):
    """Retry backoff strategy."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class PIIAction(StrEnum):
    """Action to take when PII is detected."""

    WARN = "warn"  # Log warning but proceed
    REDACT = "redact"  # Redact PII before sending
    REJECT = "reject"  # Reject the request


class ArtifactStore(StrEnum):
    """Storage backend for LLM artifacts (prompts, completions)."""

    LOCAL = "local"  # Local filesystem
    S3 = "s3"  # AWS S3
    GCS = "gcs"  # Google Cloud Storage


# =============================================================================
# Policy Specs
# =============================================================================


class RetryPolicySpec(BaseModel):
    """
    Retry policy for LLM job failures.

    Attributes:
        max_attempts: Maximum number of retry attempts (1-10)
        backoff: Backoff strategy between retries
        initial_delay_ms: Initial delay in milliseconds before first retry
        max_delay_ms: Maximum delay between retries
    """

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff: RetryBackoff = RetryBackoff.EXPONENTIAL
    initial_delay_ms: int = Field(default=1000, ge=100, le=60000)
    max_delay_ms: int = Field(default=30000, ge=1000, le=300000)

    model_config = ConfigDict(frozen=True)


class PIIPolicySpec(BaseModel):
    """
    PII (Personally Identifiable Information) handling policy.

    Attributes:
        scan: Whether to scan for PII in prompts
        action: Action to take when PII is detected
        patterns: Additional regex patterns to scan for
    """

    scan: bool = False
    action: PIIAction = PIIAction.WARN
    patterns: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class LoggingPolicySpec(BaseModel):
    """
    Logging policy for LLM operations.

    Attributes:
        log_prompts: Whether to log prompts to artifacts
        log_completions: Whether to log completions to artifacts
        redact_pii: Whether to redact PII in logs
    """

    log_prompts: bool = True
    log_completions: bool = True
    redact_pii: bool = True

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Model Specs
# =============================================================================


class LLMModelSpec(BaseModel):
    """
    LLM model configuration.

    Defines a model that can be used by LLM intents.

    Attributes:
        name: Unique identifier for this model config
        title: Human-readable title
        provider: LLM provider (anthropic, openai, etc.)
        model_id: Provider-specific model identifier
        tier: Performance/cost tier classification
        max_tokens: Maximum tokens for completion
        cost_per_1k_input: Cost per 1000 input tokens (optional)
        cost_per_1k_output: Cost per 1000 output tokens (optional)
    """

    name: str
    title: str | None = None
    provider: LLMProvider
    model_id: str
    tier: ModelTier = ModelTier.BALANCED
    max_tokens: int = Field(default=4096, gt=0, le=200000)
    cost_per_1k_input: Decimal | None = Field(default=None, ge=Decimal("0"))
    cost_per_1k_output: Decimal | None = Field(default=None, ge=Decimal("0"))

    model_config = ConfigDict(frozen=True)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        """Ensure model_id is non-empty."""
        if not v.strip():
            raise ValueError("model_id cannot be empty")
        return v


# =============================================================================
# Config Specs
# =============================================================================


class LLMConfigSpec(BaseModel):
    """
    Module-level LLM configuration.

    Provides defaults and global settings for LLM operations.

    Attributes:
        default_model: Default model to use when not specified
        default_provider: Default LLM provider when not specified per-model
        budget_alert_usd: USD threshold for budget alert notifications
        artifact_store: Storage backend for prompts/completions
        logging: Logging policy configuration
        rate_limits: Rate limits per model (requests per minute)
    """

    default_model: str | None = None
    default_provider: LLMProvider | None = None
    budget_alert_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    artifact_store: ArtifactStore = ArtifactStore.LOCAL
    logging: LoggingPolicySpec = Field(default_factory=LoggingPolicySpec)
    rate_limits: dict[str, int] | None = None

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Intent Specs
# =============================================================================


class LLMIntentSpec(BaseModel):
    """
    LLM intent (job) specification.

    Defines a declarative LLM job that can be requested.

    Attributes:
        name: Unique identifier for this intent
        title: Human-readable title
        description: Longer description of what this intent does
        model_ref: Reference to llm_model (or uses default)
        prompt_template: Jinja2 template for the prompt (optional for routing-only intents)
        output_schema: Entity name for structured output (optional)
        timeout_seconds: Maximum time for job completion
        vision: Whether this intent uses vision/image input
        retry: Retry policy for failures
        pii: PII handling policy
    """

    name: str
    title: str | None = None
    description: str | None = None
    model_ref: str | None = None
    prompt_template: str = ""
    output_schema: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    vision: bool = False
    retry: RetryPolicySpec | None = None
    pii: PIIPolicySpec | None = None

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Artifact Specs
# =============================================================================


class ArtifactKind(StrEnum):
    """Type of LLM artifact."""

    PROMPT = "prompt"
    COMPLETION = "completion"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class ArtifactRefSpec(BaseModel):
    """
    Reference to an externalized LLM artifact.

    Artifacts store prompts and completions externally to avoid
    bloating event payloads and enable analysis.

    Attributes:
        artifact_id: Unique identifier for the artifact
        content_hash: SHA-256 hash of content for integrity
        storage_uri: URI to the stored artifact
        kind: Type of artifact (prompt, completion, etc.)
        byte_size: Size of artifact in bytes
    """

    artifact_id: str
    content_hash: str
    storage_uri: str
    kind: ArtifactKind
    byte_size: int = Field(ge=0)

    model_config = ConfigDict(frozen=True)


# =============================================================================
# AIJob System Entity Builder
# =============================================================================

# Field definitions for the auto-generated AIJob entity.
# Each tuple: (name, type_kind, modifiers, default)
AI_JOB_FIELDS: list[tuple[str, str, list[str], str | None]] = [
    ("id", "uuid", ["pk"], None),
    ("intent", "str(200)", ["required"], None),
    ("model", "str(200)", ["required"], None),
    ("provider", "str(100)", ["required"], None),
    ("tokens_in", "int", [], "0"),
    ("tokens_out", "int", [], "0"),
    ("cost_usd", "decimal(12,6)", [], None),
    ("duration_ms", "int", [], None),
    ("status", "enum[pending,running,completed,failed]", ["required"], "pending"),
    ("entity_type", "str(200)", [], None),
    ("entity_id", "str(200)", [], None),
    ("user_id", "str(200)", [], None),
    ("error_message", "text", [], None),
    ("created_at", "datetime", ["required"], "now"),
]
