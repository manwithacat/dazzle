"""Tests for build_subagent_prompt.

These tests verify that the prompt template:
  - interpolates all required parameters correctly
  - dispatches between missing_contracts and edge_cases strategies
  - rejects unknown strategies with ValueError
  - includes the existing_components list verbatim
  - produces different budget/ceiling lines when budget_calls changes
  - uses the helper_command + state_dir + findings_path pair consistently
  - produces a prompt that would let a subagent understand what to do
    without external context

The test for "would a subagent understand" is necessarily indirect: we
check for the presence of specific spans (section headings, placeholder
commands, schema hints) that the spike's subagent actually consumed.
"""

from __future__ import annotations

import pytest

from dazzle.agent.missions.ux_explore_subagent import build_subagent_prompt


def _sample_params(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "strategy": "missing_contracts",
        "app_name": "contact_manager",
        "persona_id": "user",
        "persona_label": "Business User",
        "site_url": "http://localhost:3653",
        "helper_command": "python -m dazzle.agent.playwright_helper",
        "state_dir": "/tmp/ux_run_abc/state",
        "findings_path": "/tmp/ux_run_abc/findings.json",
        "existing_components": ["data-table", "card", "form-chrome"],
        "start_route": "/app/workspaces/contacts",
    }
    base.update(overrides)
    return base


class TestParameterSubstitution:
    def test_all_core_parameters_appear(self) -> None:
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert "contact_manager" in prompt
        assert "user" in prompt
        assert "Business User" in prompt
        assert "http://localhost:3653" in prompt
        assert "python -m dazzle.agent.playwright_helper" in prompt
        assert "/tmp/ux_run_abc/state" in prompt
        assert "/tmp/ux_run_abc/findings.json" in prompt
        assert "/app/workspaces/contacts" in prompt

    def test_existing_components_bulleted(self) -> None:
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert "- data-table" in prompt
        assert "- card" in prompt
        assert "- form-chrome" in prompt

    def test_empty_existing_components_shows_none_marker(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(existing_components=[])  # type: ignore[arg-type]
        )
        assert "(none)" in prompt

    def test_budget_parameters_propagate_to_text(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(budget_calls=12, min_findings=2)  # type: ignore[arg-type]
        )
        assert "12 or fewer" in prompt
        assert "2+ meaningful findings" in prompt
        # Hard ceiling = budget * 1.5
        assert "18 Bash helper calls" in prompt

    def test_budget_ceiling_ceiling_uses_int_conversion(self) -> None:
        # 20 * 1.5 = 30 — confirms int() conversion is exact on whole multiples
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert "30 Bash helper calls" in prompt


class TestStrategyDispatch:
    def test_missing_contracts_is_supported(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="missing_contracts")  # type: ignore[arg-type]
        )
        assert "UX component patterns" in prompt
        assert "ux-architect contract" in prompt
        # Missing-contracts-specific guidance language
        assert "recurring interaction pattern" in prompt

    def test_edge_cases_is_supported(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="edge_cases")  # type: ignore[arg-type]
        )
        # Edge-cases-specific guidance language
        assert "probing for UX friction" in prompt
        assert "Empty states" in prompt
        assert "Error states" in prompt
        assert "Boundary conditions" in prompt
        assert "Dead-end navigation" in prompt
        assert "Affordance mismatches" in prompt

    def test_edge_cases_directs_findings_as_observations(self) -> None:
        """edge_cases output skews toward observations, not proposals."""
        prompt = build_subagent_prompt(
            **_sample_params(strategy="edge_cases")  # type: ignore[arg-type]
        )
        assert "as an **observation**" in prompt
        # But proposals are still accepted for stumble-across discoveries
        assert "Proposals are still accepted" in prompt

    def test_missing_contracts_does_not_leak_edge_cases_guidance(self) -> None:
        """The two strategy sections are mutually exclusive."""
        prompt = build_subagent_prompt(
            **_sample_params(strategy="missing_contracts")  # type: ignore[arg-type]
        )
        assert "probing for UX friction" not in prompt
        assert "Dead-end navigation" not in prompt

    def test_edge_cases_does_not_leak_missing_contracts_guidance(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="edge_cases")  # type: ignore[arg-type]
        )
        assert "recurring interaction pattern" not in prompt

    def test_unknown_strategy_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown strategy"):
            build_subagent_prompt(
                **_sample_params(strategy="lol_random")  # type: ignore[arg-type]
            )

    def test_persona_journey_supported(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(  # type: ignore[arg-type]
                strategy="persona_journey",
                persona_goals=["Onboard new clients", "Close deals fast"],
            )
        )
        assert "walking user's declared goals" in prompt
        assert "Onboard new clients" in prompt
        assert "Close deals fast" in prompt

    def test_persona_journey_without_goals_marks_missing(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="persona_journey")  # type: ignore[arg-type]
        )
        assert "no goals declared in the DSL" in prompt

    def test_cross_persona_consistency_supported(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="cross_persona_consistency")  # type: ignore[arg-type]
        )
        assert "renders consistently" in prompt
        assert "visibility/permission rules" in prompt
        assert "scope rule" in prompt

    def test_regression_hunt_supported(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="regression_hunt")  # type: ignore[arg-type]
        )
        assert "major workspace region" in prompt
        assert "framework upgrade" in prompt

    def test_create_flow_audit_supported(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(strategy="create_flow_audit")  # type: ignore[arg-type]
        )
        assert "auditing the app's create flows" in prompt
        assert "Valid create" in prompt
        assert "Invalid create" in prompt


class TestAppDescriptor:
    def test_default_descriptor_uses_app_name(self) -> None:
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert "Dazzle app `contact_manager`" in prompt

    def test_custom_app_descriptor_used_in_opening(self) -> None:
        prompt = build_subagent_prompt(
            **_sample_params(  # type: ignore[arg-type]
                app_descriptor="AegisMark production app",
            )
        )
        assert "AegisMark production app" in prompt
        # Old framework-specific wording is gone
        assert "Dazzle example app" not in prompt


class TestPromptStructure:
    def test_contains_all_required_sections(self) -> None:
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert "# Mission:" in prompt
        assert "## How to drive the browser" in prompt
        assert "## Starting point" in prompt
        assert "## Mission-specific guidance" in prompt
        assert "## Existing component contracts" in prompt
        assert "## What to record" in prompt
        assert "## Budget" in prompt
        assert "## Report back" in prompt

    def test_findings_file_schema_is_embedded(self) -> None:
        """The subagent needs the JSON schema inline — it reads the file,
        modifies it, writes it back. Verify the schema spans are present."""
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert '"component_name"' in prompt
        assert '"description"' in prompt
        assert '"observed_on_page"' in prompt
        assert '"selector_hint"' in prompt
        assert '"severity"' in prompt
        assert "minor | notable | concerning" in prompt

    def test_helper_commands_use_correct_flag_order(self) -> None:
        """The helper CLI parser accepts --state-dir BEFORE the subcommand.
        The prompt must reflect that so the subagent's Bash calls work."""
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        # Specifically check that --state-dir appears before the action verb
        assert "--state-dir /tmp/ux_run_abc/state observe" in prompt
        assert "--state-dir /tmp/ux_run_abc/state navigate" in prompt
        assert "--state-dir /tmp/ux_run_abc/state click" in prompt

    def test_persona_id_appears_in_schema_defaults(self) -> None:
        """Proposals + observations are tagged with persona_id; the schema
        examples should show the active persona so the subagent copies it."""
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert '"persona_id": "user"' in prompt

    def test_prompt_ends_with_begin_marker(self) -> None:
        prompt = build_subagent_prompt(**_sample_params())  # type: ignore[arg-type]
        assert prompt.rstrip().endswith("Begin.")
