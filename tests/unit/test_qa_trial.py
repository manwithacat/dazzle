"""Tests for the qualitative trial harness — mission builder and
markdown report renderer.

These tests don't exercise the live agent loop (that needs a live
server and an LLM). They pin the pure-function plumbing: scenario
parsing, tool behaviour under direct invocation, and report
rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dazzle.agent.missions.trial import build_trial_mission
from dazzle.qa.trial_report import (
    _first_line,
    _title_from_description,
    build_trial_report,
    render_trial_report,
)
from dazzle.qa.trial_verdict_fallback import _format_friction_for_synthesis

# ---------------------------------------------------------------------------
# Mission builder
# ---------------------------------------------------------------------------


class TestBuildTrialMission:
    @pytest.fixture
    def scenario(self) -> dict:
        return {
            "name": "sample",
            "login_persona": "manager",
            "user_identity": "You are Sam.\nYou run a thing.",
            "business_context": "20 requests/week.",
            "tasks": ["Find X", "Close Y"],
            "stop_when": "Stop when ready.",
            "max_steps": 20,
        }

    def test_mission_name_incorporates_scenario(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        assert m.name == "trial:sample"

    def test_start_url_points_at_app(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        assert m.start_url == "http://host:1234/app"

    def test_system_prompt_includes_identity_and_tasks(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        assert "You are Sam" in m.system_prompt
        assert "20 requests/week" in m.system_prompt
        assert "Find X" in m.system_prompt
        assert "Close Y" in m.system_prompt
        assert "Stop when ready" in m.system_prompt

    def test_tools_include_record_friction_and_submit_verdict(self, scenario: dict) -> None:
        """submit_verdict (not done) — named unique to avoid colliding
        with the builtin done page action, which was eating our tool
        call during trial runs 1 and 2 and leaving the verdict empty."""
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        names = {t.name for t in m.tools}
        assert names == {"record_friction", "submit_verdict"}
        assert "done" not in names, (
            "'done' collides with the builtin page action — see trial-2 post-mortem"
        )

    def test_record_friction_writes_to_sink(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        tool = next(t for t in m.tools if t.name == "record_friction")
        tool.handler(
            category="bug",
            description="Something broke",
            url="/app/tickets",
            evidence="Got a 500.",
            severity="high",
        )
        assert len(sink["friction"]) == 1
        entry = sink["friction"][0]
        assert entry["category"] == "bug"
        assert entry["severity"] == "high"
        assert entry["url"] == "/app/tickets"

    def test_record_friction_sanitises_unknown_category(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        tool = next(t for t in m.tools if t.name == "record_friction")
        tool.handler(category="not-a-category", description="hmm")
        assert sink["friction"][0]["category"] == "other"

    def test_submit_verdict_records_verdict_in_sink(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        tool = next(t for t in m.tools if t.name == "submit_verdict")
        tool.handler(verdict="Would not switch — missing filters.")
        assert sink["verdict"][0]["text"] == "Would not switch — missing filters."

    def test_max_steps_override_wins(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(
            scenario, base_url="http://host:1234", transcript_sink=sink, max_steps=5
        )
        assert m.max_steps == 5

    def test_max_steps_falls_back_to_scenario(self, scenario: dict) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        assert m.max_steps == 20

    def test_system_prompt_mentions_step_budget_and_wrap_up(self, scenario: dict) -> None:
        """After the post-trial-1/2/3 tweaks: the prompt tells the agent
        its total step count AND the specific step number to start
        wrapping up at (60% of budget — lowered from 75% after trials
        1-3 all ran out of budget before calling submit_verdict)."""
        sink: dict = {"friction": []}
        m = build_trial_mission(
            scenario, base_url="http://host:1234", transcript_sink=sink, max_steps=20
        )
        # Total budget surfaces in the prompt
        assert "20 steps total" in m.system_prompt
        # Wrap-up trigger point surfaces (60% of 20 = 12)
        assert "step 12" in m.system_prompt

    def test_system_prompt_forbids_duplicate_friction(self, scenario: dict) -> None:
        """The agent kept re-recording the same /dashboard 404 four
        times in trial-1. The prompt now tells it not to."""
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        assert "same friction twice" in m.system_prompt.lower()


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


class TestReportRendering:
    def test_first_line_strips_and_finds_first_nonempty(self) -> None:
        assert _first_line("\n\n  Sarah, founder  \nrest") == "Sarah, founder"
        assert _first_line("") == ""

    def test_title_from_description_uses_first_sentence(self) -> None:
        assert (
            _title_from_description("I tried to close a ticket. It 500d.")
            == "I tried to close a ticket"
        )

    def test_title_from_description_truncates_long(self) -> None:
        long = "a" * 200
        out = _title_from_description(long, max_chars=50)
        assert out.endswith("…")
        assert len(out) == 50

    def test_empty_friction_renders_tombstone(self) -> None:
        report = build_trial_report(
            scenario_name="s",
            user_identity="Sarah",
            friction=[],
            verdict="Good stuff.",
        )
        out = render_trial_report(report)
        assert "no friction recorded" in out
        assert "## Verdict" in out
        assert "Good stuff." in out

    def test_verdict_missing_surfaces_tombstone(self) -> None:
        report = build_trial_report(
            scenario_name="s", user_identity="Sarah", friction=[], verdict=""
        )
        out = render_trial_report(report)
        assert "no verdict recorded" in out

    def test_friction_is_grouped_by_category(self) -> None:
        friction = [
            {"category": "praise", "description": "Nice colors."},
            {"category": "bug", "description": "500 on save.", "severity": "high"},
            {"category": "bug", "description": "Sort didn't apply.", "severity": "medium"},
            {"category": "confusion", "description": "Couldn't find close.", "severity": "low"},
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Sarah", friction=friction, verdict="ok"
        )
        out = render_trial_report(report)
        # bugs render before confusion before praise (per _CATEGORY_ORDER)
        bug_pos = out.index("### bug")
        confusion_pos = out.index("### confusion")
        praise_pos = out.index("### praise")
        assert bug_pos < confusion_pos < praise_pos

    def test_bug_high_severity_sorts_before_bug_medium(self) -> None:
        friction = [
            {"category": "bug", "description": "medium one", "severity": "medium"},
            {"category": "bug", "description": "high one", "severity": "high"},
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Sarah", friction=friction, verdict="ok"
        )
        out = render_trial_report(report)
        assert out.index("high one") < out.index("medium one")

    def test_evidence_is_wrapped_in_code_fence(self) -> None:
        friction = [
            {
                "category": "bug",
                "description": "broke",
                "evidence": "<div>HTTP 500</div>",
                "severity": "high",
            }
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Sarah", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "```" in out
        assert "<div>HTTP 500</div>" in out

    def test_url_surfaces_in_metadata_line(self) -> None:
        friction = [
            {"category": "bug", "description": "x", "url": "/app/tickets/123"},
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Sarah", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "/app/tickets/123" in out


class TestFreshDbReset:
    """The ``--fresh-db`` flag (#810) calls ``_reset_db_for_trial``
    which chdirs into the project, runs ``db_reset_impl`` via
    ``_run_with_connection``, then restores cwd. These tests pin the
    plumbing without requiring a live database — ``_run_with_connection``
    is patched to return a canned result."""

    def test_reset_restores_cwd_on_success(self, tmp_path, monkeypatch) -> None:
        from dazzle.cli import qa as qa_mod

        before = Path.cwd()
        calls: dict[str, Any] = {}

        class FakeAppSpec:
            class domain:  # noqa: N801 — mimicking real attr nesting
                entities: list[Any] = []

        def fake_load(root: Path) -> Any:
            calls["load_root"] = root
            return FakeAppSpec()

        def fake_run_with_conn(*args: Any, **kwargs: Any) -> Any:
            return {"truncated": 2, "total_rows": 7, "tables": []}

        monkeypatch.setattr("dazzle.cli.utils.load_project_appspec", fake_load)
        monkeypatch.setattr("dazzle.cli.db._run_with_connection", lambda *a, **k: None)
        monkeypatch.setattr("asyncio.run", fake_run_with_conn)

        project = tmp_path / "project"
        project.mkdir()
        qa_mod._reset_db_for_trial(project)

        assert Path.cwd() == before

    def test_reset_restores_cwd_on_error(self, tmp_path, monkeypatch) -> None:
        from dazzle.cli import qa as qa_mod

        before = Path.cwd()

        def boom(root: Path) -> Any:
            raise RuntimeError("load failed")

        monkeypatch.setattr("dazzle.cli.utils.load_project_appspec", boom)

        project = tmp_path / "project"
        project.mkdir()
        with pytest.raises(RuntimeError, match="load failed"):
            qa_mod._reset_db_for_trial(project)

        assert Path.cwd() == before


class TestFrictionClustering:
    """Near-duplicate friction clustering (#812).

    Trial agents re-record the same finding multiple times despite the
    'don't record duplicates' system prompt. Clustering post-processes
    the report so one canonical entry represents a group of
    near-duplicates, annotated with the cluster size.
    """

    def test_identical_entries_collapse_to_one(self) -> None:
        friction = [
            {
                "category": "bug",
                "description": "Alert list 403s.",
                "url": "/app/alert",
                "severity": "high",
            }
        ] * 4
        report = build_trial_report(
            scenario_name="s", user_identity="Dan", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "Friction observations (1 · 3 near-duplicates clustered)" in out
        assert "*reported:* ×4" in out

    def test_different_urls_do_not_cluster(self) -> None:
        friction = [
            {"category": "bug", "description": "403.", "url": "/app/alert"},
            {"category": "bug", "description": "403.", "url": "/app/user"},
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Dan", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        # Two distinct entries, no clustering annotation.
        assert "near-duplicates clustered" not in out
        assert "Friction observations (2)" in out

    def test_different_categories_do_not_cluster(self) -> None:
        friction = [
            {"category": "bug", "description": "Same words.", "url": "/x"},
            {"category": "praise", "description": "Same words.", "url": "/x"},
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Dan", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "Friction observations (2)" in out

    def test_near_duplicate_descriptions_cluster(self) -> None:
        friction = [
            {
                "category": "praise",
                "description": "The Issue Board is exactly what I need as a manager.",
                "url": "/app/issue",
            },
            {
                "category": "praise",
                "description": "Issue Board is exactly what I need as a manager.",
                "url": "/app/issue",
            },
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Dan", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "Friction observations (1 · 1 near-duplicates clustered)" in out

    def test_dissimilar_descriptions_on_same_url_do_not_cluster(self) -> None:
        friction = [
            {"category": "bug", "description": "Filter broken.", "url": "/x"},
            {"category": "bug", "description": "Button misaligned.", "url": "/x"},
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Dan", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "Friction observations (2)" in out


# ---------------------------------------------------------------------------
# Verdict fallback formatter (the LLM call itself is integration-only)
# ---------------------------------------------------------------------------


class TestVerdictFallbackFormatter:
    def test_empty_friction_tombstones(self) -> None:
        assert _format_friction_for_synthesis([]) == "(no friction recorded)"

    def test_formats_per_entry_with_category_severity_url(self) -> None:
        out = _format_friction_for_synthesis(
            [
                {
                    "category": "bug",
                    "severity": "high",
                    "description": "Filter broke.",
                    "url": "/app/ticket",
                }
            ]
        )
        assert "[bug/high]" in out
        assert "/app/ticket" in out
        assert "Filter broke." in out

    def test_omits_url_when_missing(self) -> None:
        out = _format_friction_for_synthesis([{"category": "praise", "description": "Nice."}])
        # Default severity "medium" applied
        assert "[praise/medium]" in out
        assert "@ " not in out
