"""
User profile for adaptive persona inference.

Tracks user behavior signals (tool usage, vocabulary) to build a profile
that the LLM reads as context, enabling it to naturally adjust register,
question strategy, and explanation depth for different user types:
  - Non-technical founders (business language, guided questions)
  - Frontend developers (UX patterns, surface/layout focus)
  - Backend developers (system architecture, precise terminology)
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("dazzle.mcp.user_profile")

# Default profile location — global (describes the user, not the project)
PROFILE_DIR = Path.home() / ".dazzle"
PROFILE_PATH = PROFILE_DIR / "user_profile.json"


# =============================================================================
# Profile Model
# =============================================================================


class UserProfile(BaseModel):
    """Persistent user profile with scored dimensions."""

    technical_depth: float = 0.5  # 0=non-technical founder, 1=senior engineer
    domain_clarity: float = 0.5  # 0=exploring/vague, 1=clear requirements
    ux_focus: float = 0.5  # 0=backend-oriented, 1=frontend/UX-oriented
    preferred_framing: str = "balanced"
    total_interactions: int = 0
    tool_affinities: dict[str, int] = Field(default_factory=dict)
    vocabulary_signals: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    confidence: float = 0.0


# =============================================================================
# Persistence
# =============================================================================


def _make_default_profile() -> UserProfile:
    """Create a fresh default profile with timestamps."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return UserProfile(created_at=now, updated_at=now)


def load_profile(path: Path | None = None) -> UserProfile:
    """Load profile from disk, or return a fresh default."""
    p = path or PROFILE_PATH
    if p.exists():
        try:
            data = json.loads(p.read_text())
            return UserProfile(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Could not load user profile: %s", e)
    return _make_default_profile()


def save_profile(profile: UserProfile, path: Path | None = None) -> None:
    """Persist profile to disk."""
    p = path or PROFILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    profile.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(profile.model_dump(), indent=2))


def reset_profile(path: Path | None = None) -> UserProfile:
    """Delete existing profile and return a fresh default."""
    p = path or PROFILE_PATH
    if p.exists():
        p.unlink()
    return _make_default_profile()


# =============================================================================
# Tool Affinity Signals
# =============================================================================

# Maps "tool_name" or "tool_name:operation" to dimension deltas.
# Positive = increase, negative = decrease.
TOOL_SIGNALS: dict[str, dict[str, float]] = {
    # Non-technical entry points → lower technical_depth
    "bootstrap": {"technical_depth": -0.06},
    "spec_analyze": {"technical_depth": -0.05},
    "spec_analyze:discover_entities": {"technical_depth": -0.08},
    "spec_analyze:generate_questions": {"technical_depth": -0.07},
    # Technical tools → higher technical_depth
    "dsl:validate": {"technical_depth": 0.08},
    "dsl:inspect_entity": {"technical_depth": 0.08},
    "dsl:inspect_surface": {"technical_depth": 0.07},
    "dsl:lint": {"technical_depth": 0.10},
    "dsl:analyze": {"technical_depth": 0.06},
    "graph": {"technical_depth": 0.07},
    "graph:query": {"technical_depth": 0.08},
    "graph:dependencies": {"technical_depth": 0.10},
    "graph:populate": {"technical_depth": 0.09},
    # Testing tools → technical
    "dsl_test": {"technical_depth": 0.05},
    "e2e_test": {"technical_depth": 0.05},
    "discovery": {"technical_depth": 0.05},
    # UX-oriented tools
    "dsl:export_frontend_spec": {"ux_focus": 0.10},
    "sitespec": {"ux_focus": 0.07},
    "sitespec:coherence": {"ux_focus": 0.10},
    "sitespec:scaffold": {"ux_focus": 0.08},
    "sitespec:get_copy": {"ux_focus": 0.06},
    "sitespec:scaffold_copy": {"ux_focus": 0.08},
    # Domain clarity tools
    "story:propose": {"domain_clarity": 0.07},
    "process:propose": {"domain_clarity": 0.06},
    "story:save": {"domain_clarity": 0.06},
    "process:save": {"domain_clarity": 0.06},
    "demo_data:propose": {"domain_clarity": 0.05},
}


def analyze_tool_invocations(
    invocations: list[dict[str, Any]],
    profile: UserProfile,
) -> UserProfile:
    """
    Apply tool-usage signals to profile dimensions.

    Args:
        invocations: List of invocation dicts from KG telemetry.
            Each has at least ``tool_name`` and optionally ``operation``.
        profile: The current profile (mutated in place and returned).
    """
    for inv in invocations:
        tool_name = inv.get("tool_name", "")
        operation = inv.get("operation", "")

        # Build affinity key
        affinity_key = f"{tool_name}:{operation}" if operation else tool_name
        profile.tool_affinities[affinity_key] = profile.tool_affinities.get(affinity_key, 0) + 1
        profile.total_interactions += 1

        # Look up signals: try specific "tool:operation" first, fall back to tool-only
        specific_key = f"{tool_name}:{operation}" if operation else None
        deltas = TOOL_SIGNALS.get(specific_key or "", {}) or TOOL_SIGNALS.get(tool_name, {})

        for dim, delta in deltas.items():
            current = getattr(profile, dim)
            new_val = max(0.0, min(1.0, current + delta))
            setattr(profile, dim, new_val)

    _recompute_derived(profile)
    return profile


# =============================================================================
# Vocabulary Signals
# =============================================================================

MAX_VOCAB_SIGNALS = 50

VOCAB_SIGNALS: dict[str, dict[str, float]] = {
    # Business vocabulary → domain_clarity up, technical_depth down
    "revenue": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "customer": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "onboarding": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "pricing": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "mvp": {"domain_clarity": 0.03, "technical_depth": -0.03},
    "stakeholder": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "user story": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "market": {"domain_clarity": 0.03, "technical_depth": -0.02},
    "conversion": {"domain_clarity": 0.04, "technical_depth": -0.02},
    "churn": {"domain_clarity": 0.04, "technical_depth": -0.02},
    # Technical vocabulary → technical_depth up
    "entity": {"technical_depth": 0.03},
    "state machine": {"technical_depth": 0.05},
    "schema": {"technical_depth": 0.04},
    "idempotent": {"technical_depth": 0.06},
    "webhook": {"technical_depth": 0.04},
    "foreign key": {"technical_depth": 0.05},
    "migration": {"technical_depth": 0.04},
    "api": {"technical_depth": 0.03},
    "endpoint": {"technical_depth": 0.04},
    "middleware": {"technical_depth": 0.05},
    # UX vocabulary → ux_focus up
    "component": {"ux_focus": 0.04},
    "responsive": {"ux_focus": 0.05},
    "layout": {"ux_focus": 0.04},
    "dark mode": {"ux_focus": 0.05},
    "accessibility": {"ux_focus": 0.05},
    "wireframe": {"ux_focus": 0.06},
    "navigation": {"ux_focus": 0.04},
    "user experience": {"ux_focus": 0.05},
    "mobile": {"ux_focus": 0.04},
    "design system": {"ux_focus": 0.06},
}

# Pre-compile patterns sorted longest-first so multi-word matches take priority
_VOCAB_PATTERNS: list[tuple[re.Pattern[str], dict[str, float]]] = [
    (re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE), deltas)
    for term, deltas in sorted(VOCAB_SIGNALS.items(), key=lambda x: -len(x[0]))
]


def analyze_message(message_text: str, profile: UserProfile) -> UserProfile:
    """
    Scan a message for vocabulary signals and update the profile.

    Args:
        message_text: Raw user message text.
        profile: The current profile (mutated in place and returned).
    """
    text_lower = message_text.lower()

    for pattern, deltas in _VOCAB_PATTERNS:
        if pattern.search(text_lower):
            # Record the signal term
            term = pattern.pattern.replace(r"\b", "").replace("\\", "")
            if len(profile.vocabulary_signals) >= MAX_VOCAB_SIGNALS:
                profile.vocabulary_signals.pop(0)
            profile.vocabulary_signals.append(term)

            profile.total_interactions += 1

            for dim, delta in deltas.items():
                current = getattr(profile, dim)
                new_val = max(0.0, min(1.0, current + delta))
                setattr(profile, dim, new_val)

    _recompute_derived(profile)
    return profile


# =============================================================================
# Derived Computations
# =============================================================================

FRAMING_GAP_THRESHOLD = 0.15


def _recompute_derived(profile: UserProfile) -> None:
    """Recompute confidence and preferred_framing from current state."""
    n = profile.total_interactions
    profile.confidence = 1.0 - math.exp(-n / 20.0)
    profile.preferred_framing = _derive_framing(profile)


def _derive_framing(profile: UserProfile) -> str:
    """Determine preferred framing from dimension scores."""
    td = profile.technical_depth
    dc = profile.domain_clarity
    ux = profile.ux_focus

    # Peak detection with gap threshold
    if ux > td + FRAMING_GAP_THRESHOLD and ux > dc + FRAMING_GAP_THRESHOLD:
        return "ux_patterns"
    if td > ux + FRAMING_GAP_THRESHOLD and td > 0.6:
        return "system_architecture"
    if dc > 0.6 and td < 0.4:
        return "business_outcomes"
    return "balanced"


# =============================================================================
# Context Generation
# =============================================================================


def profile_to_context(profile: UserProfile) -> dict[str, Any]:
    """
    Convert a profile into an LLM-consumable context dict.

    The ``guidance`` field is the key output — natural language the LLM
    incorporates directly into its response strategy.
    """
    guidance_parts: list[str] = []

    if profile.technical_depth < 0.35:
        guidance_parts.append(
            "Use business language, avoid jargon, explain DSL concepts when introducing them."
        )
    elif profile.technical_depth > 0.65:
        guidance_parts.append("Be concise, use precise terminology, skip basic explanations.")

    if profile.domain_clarity < 0.35:
        guidance_parts.append("Ask clarifying questions about requirements before generating DSL.")
    elif profile.domain_clarity > 0.65:
        guidance_parts.append("User has clear requirements — proceed directly with generation.")

    if profile.ux_focus > 0.65:
        guidance_parts.append(
            "Lead with surface/layout explanations, show visual structure before data model."
        )
    elif profile.ux_focus < 0.35:
        guidance_parts.append("Focus on data model and backend architecture first.")

    if not guidance_parts:
        guidance_parts.append("User profile is balanced — adapt to the specific question asked.")

    # Top tools by usage count
    sorted_tools = sorted(profile.tool_affinities.items(), key=lambda x: x[1], reverse=True)
    top_tools = sorted_tools[:5]

    return {
        "dimensions": {
            "technical_depth": round(profile.technical_depth, 3),
            "domain_clarity": round(profile.domain_clarity, 3),
            "ux_focus": round(profile.ux_focus, 3),
        },
        "preferred_framing": profile.preferred_framing,
        "confidence": round(profile.confidence, 3),
        "total_interactions": profile.total_interactions,
        "guidance": " ".join(guidance_parts),
        "top_tools": top_tools,
        "recent_vocabulary": profile.vocabulary_signals[-10:],
    }
