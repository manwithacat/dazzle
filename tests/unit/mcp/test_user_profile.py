"""Tests for user profile adaptive persona inference."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from dazzle.mcp.user_profile import (
    UserProfile,
    _derive_framing,
    analyze_message,
    analyze_tool_invocations,
    load_profile,
    profile_to_context,
    reset_profile,
    save_profile,
)

# =============================================================================
# TestUserProfileModel
# =============================================================================


class TestUserProfileModel:
    """Default values and serialization."""

    def test_default_neutral_scores(self) -> None:
        p = UserProfile()
        assert p.technical_depth == 0.5
        assert p.domain_clarity == 0.5
        assert p.ux_focus == 0.5
        assert p.preferred_framing == "balanced"
        assert p.total_interactions == 0
        assert p.confidence == 0.0

    def test_serialization_roundtrip(self) -> None:
        p = UserProfile(
            technical_depth=0.8,
            domain_clarity=0.3,
            ux_focus=0.6,
            preferred_framing="system_architecture",
            total_interactions=42,
            tool_affinities={"dsl:validate": 10},
            vocabulary_signals=["schema", "api"],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            confidence=0.87,
        )
        data = p.model_dump()
        p2 = UserProfile(**data)
        assert p2.technical_depth == 0.8
        assert p2.tool_affinities == {"dsl:validate": 10}
        assert p2.vocabulary_signals == ["schema", "api"]


# =============================================================================
# TestToolInvocationAnalysis
# =============================================================================


class TestToolInvocationAnalysis:
    """Tool usage signals shift profile dimensions correctly."""

    def test_backend_tools_increase_technical_depth(self) -> None:
        p = UserProfile()
        invocations = [
            {"tool_name": "dsl", "operation": "validate"},
            {"tool_name": "dsl", "operation": "lint"},
            {"tool_name": "graph", "operation": "query"},
        ]
        analyze_tool_invocations(invocations, p)
        assert p.technical_depth > 0.5

    def test_bootstrap_decreases_technical_depth(self) -> None:
        p = UserProfile()
        invocations = [
            {"tool_name": "bootstrap", "operation": ""},
            {"tool_name": "bootstrap", "operation": ""},
            {"tool_name": "bootstrap", "operation": ""},
        ]
        analyze_tool_invocations(invocations, p)
        assert p.technical_depth < 0.5

    def test_sitespec_increases_ux_focus(self) -> None:
        p = UserProfile()
        invocations = [
            {"tool_name": "sitespec", "operation": "coherence"},
            {"tool_name": "sitespec", "operation": "scaffold"},
            {"tool_name": "dsl", "operation": "export_frontend_spec"},
        ]
        analyze_tool_invocations(invocations, p)
        assert p.ux_focus > 0.5

    def test_confidence_grows_with_interactions(self) -> None:
        p = UserProfile()
        invocations = [{"tool_name": "dsl", "operation": "validate"}] * 20
        analyze_tool_invocations(invocations, p)
        assert p.confidence > 0.6  # ~0.63 at 20 interactions

    def test_scores_clamped_0_1(self) -> None:
        p = UserProfile(technical_depth=0.98)
        invocations = [{"tool_name": "dsl", "operation": "lint"}] * 10
        analyze_tool_invocations(invocations, p)
        assert p.technical_depth <= 1.0

        p2 = UserProfile(technical_depth=0.02)
        invocations2 = [{"tool_name": "bootstrap", "operation": ""}] * 10
        analyze_tool_invocations(invocations2, p2)
        assert p2.technical_depth >= 0.0

    def test_affinities_tracked(self) -> None:
        p = UserProfile()
        invocations = [
            {"tool_name": "dsl", "operation": "validate"},
            {"tool_name": "dsl", "operation": "validate"},
            {"tool_name": "graph", "operation": "query"},
        ]
        analyze_tool_invocations(invocations, p)
        assert p.tool_affinities["dsl:validate"] == 2
        assert p.tool_affinities["graph:query"] == 1

    def test_story_propose_increases_domain_clarity(self) -> None:
        p = UserProfile()
        invocations = [
            {"tool_name": "story", "operation": "propose"},
            {"tool_name": "process", "operation": "propose"},
        ]
        analyze_tool_invocations(invocations, p)
        assert p.domain_clarity > 0.5


# =============================================================================
# TestVocabularyAnalysis
# =============================================================================


class TestVocabularyAnalysis:
    """Vocabulary signals in messages shift profile dimensions."""

    def test_tech_terms_increase_technical_depth(self) -> None:
        p = UserProfile()
        analyze_message("I need to define the entity schema with a foreign key", p)
        assert p.technical_depth > 0.5

    def test_business_terms_increase_domain_clarity(self) -> None:
        p = UserProfile()
        analyze_message("We need better onboarding for our customer pricing", p)
        assert p.domain_clarity > 0.5

    def test_ux_terms_increase_ux_focus(self) -> None:
        p = UserProfile()
        analyze_message("The layout needs to be responsive with dark mode support", p)
        assert p.ux_focus > 0.5

    def test_signals_recorded(self) -> None:
        p = UserProfile()
        analyze_message("Update the schema and wireframe", p)
        assert len(p.vocabulary_signals) > 0
        # Should contain the matched terms
        signals_lower = [s.lower() for s in p.vocabulary_signals]
        assert "schema" in signals_lower or "wireframe" in signals_lower

    def test_signals_capped_at_50(self) -> None:
        p = UserProfile()
        # Pre-fill with 48 signals
        p.vocabulary_signals = [f"term{i}" for i in range(48)]
        # Add a message that matches multiple terms
        analyze_message("schema and wireframe and layout and component and responsive", p)
        assert len(p.vocabulary_signals) <= 50


# =============================================================================
# TestDeriveFraming
# =============================================================================


class TestDeriveFraming:
    """Preferred framing derived from dimension scores."""

    def test_ux_patterns(self) -> None:
        p = UserProfile(technical_depth=0.3, domain_clarity=0.3, ux_focus=0.7)
        assert _derive_framing(p) == "ux_patterns"

    def test_system_architecture(self) -> None:
        p = UserProfile(technical_depth=0.8, domain_clarity=0.4, ux_focus=0.4)
        assert _derive_framing(p) == "system_architecture"

    def test_business_outcomes(self) -> None:
        p = UserProfile(technical_depth=0.3, domain_clarity=0.7, ux_focus=0.4)
        assert _derive_framing(p) == "business_outcomes"

    def test_balanced(self) -> None:
        p = UserProfile(technical_depth=0.5, domain_clarity=0.5, ux_focus=0.5)
        assert _derive_framing(p) == "balanced"


# =============================================================================
# TestProfileToContext
# =============================================================================


class TestProfileToContext:
    """Context output for LLM consumption."""

    def test_has_dimensions(self) -> None:
        p = UserProfile(technical_depth=0.72, domain_clarity=0.45, ux_focus=0.31)
        ctx = profile_to_context(p)
        assert "dimensions" in ctx
        assert ctx["dimensions"]["technical_depth"] == 0.72

    def test_has_guidance_text(self) -> None:
        p = UserProfile(technical_depth=0.8, total_interactions=20)
        ctx = profile_to_context(p)
        assert "guidance" in ctx
        assert isinstance(ctx["guidance"], str)
        assert len(ctx["guidance"]) > 0

    def test_low_tech_guidance(self) -> None:
        p = UserProfile(technical_depth=0.2)
        ctx = profile_to_context(p)
        assert "business language" in ctx["guidance"].lower() or "jargon" in ctx["guidance"].lower()

    def test_has_sorted_top_tools(self) -> None:
        p = UserProfile(tool_affinities={"dsl:validate": 8, "graph:query": 4, "bootstrap": 1})
        ctx = profile_to_context(p)
        assert "top_tools" in ctx
        # Should be sorted descending by count
        assert ctx["top_tools"][0][0] == "dsl:validate"
        assert ctx["top_tools"][0][1] == 8

    def test_balanced_guidance_for_neutral_profile(self) -> None:
        p = UserProfile()
        ctx = profile_to_context(p)
        assert "balanced" in ctx["guidance"].lower() or "adapt" in ctx["guidance"].lower()


# =============================================================================
# TestPersistence
# =============================================================================


class TestPersistence:
    """File-based persistence."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        p = UserProfile(technical_depth=0.8, total_interactions=5)
        path = tmp_path / "profile.json"
        save_profile(p, path)
        loaded = load_profile(path)
        assert loaded.technical_depth == 0.8
        assert loaded.total_interactions == 5

    def test_load_missing_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        p = load_profile(path)
        assert p.technical_depth == 0.5
        assert p.total_interactions == 0

    def test_load_corrupt_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not valid json{{{")
        p = load_profile(path)
        assert p.technical_depth == 0.5


# =============================================================================
# TestResetProfile
# =============================================================================


class TestResetProfile:
    """Profile reset behavior."""

    def test_fresh_default(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.json"
        save_profile(UserProfile(technical_depth=0.9), path)
        p = reset_profile(path)
        assert p.technical_depth == 0.5
        assert p.total_interactions == 0

    def test_file_deleted(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.json"
        path.write_text("{}")
        reset_profile(path)
        assert not path.exists()


# =============================================================================
# TestHandler
# =============================================================================


class TestHandler:
    """MCP handler integration."""

    def test_get_operation(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.json"
        save_profile(UserProfile(technical_depth=0.75), path)

        from dazzle.mcp.server.handlers.user_profile import handle_user_profile

        with patch("dazzle.mcp.user_profile.PROFILE_PATH", path):
            result = json.loads(handle_user_profile({"operation": "get"}))
        assert result["dimensions"]["technical_depth"] == 0.75

    def test_reset_operation(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.json"
        save_profile(UserProfile(technical_depth=0.9), path)

        from dazzle.mcp.server.handlers.user_profile import handle_user_profile

        with patch("dazzle.mcp.user_profile.PROFILE_PATH", path):
            result = json.loads(handle_user_profile({"operation": "reset"}))
        assert result["status"] == "reset"
        assert result["profile"]["dimensions"]["technical_depth"] == 0.5

    def test_observe_message_operation(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.json"

        from dazzle.mcp.server.handlers.user_profile import handle_user_profile

        with patch("dazzle.mcp.user_profile.PROFILE_PATH", path):
            result = json.loads(
                handle_user_profile(
                    {
                        "operation": "observe_message",
                        "message_text": "I need a schema with foreign key",
                    }
                )
            )
        assert result["status"] == "updated"
        assert result["profile"]["dimensions"]["technical_depth"] > 0.5

    def test_observe_no_data(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.json"

        from dazzle.mcp.server.handlers.user_profile import handle_user_profile

        with (
            patch("dazzle.mcp.user_profile.PROFILE_PATH", path),
            patch(
                "dazzle.mcp.server.handlers.user_profile.get_knowledge_graph",
                side_effect=ImportError("no KG"),
            )
            if False
            else patch(
                "dazzle.mcp.server.state.get_knowledge_graph",
                return_value=None,
            ),
        ):
            result = json.loads(handle_user_profile({"operation": "observe"}))
        assert result["status"] == "no_data"

    def test_unknown_operation(self) -> None:
        from dazzle.mcp.server.handlers.user_profile import handle_user_profile

        result = json.loads(handle_user_profile({"operation": "bogus"}))
        assert "error" in result
