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

from dazzle.agent.missions.trial import _trial_completion, build_trial_mission
from dazzle.agent.models import ActionType, AgentAction
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
        # Verdict with NO negative tokens — should record without rejection.
        result = tool.handler(verdict="Would not switch — tight UX quirks.")
        assert sink["verdict"][0]["text"] == "Would not switch — tight UX quirks."
        assert result.get("ended") is True

    def test_submit_verdict_rejects_negative_verdict_without_friction(self, scenario: dict) -> None:
        """Regression guard for the simple_task/agency_lead trial on
        2026-04-20: agent articulated 4+ failures in its verdict
        ('deeply broken', '404', 'missing', 'unresponsive') but called
        record_friction zero times, leaving the report with no
        actionable rows. The tool now rejects this shape and nudges."""
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        tool = next(t for t in m.tools if t.name == "submit_verdict")
        result = tool.handler(
            verdict=(
                "I cannot recommend this. The Task List is 404. Multiple UI "
                "elements are unresponsive. The core functionality appears "
                "deeply broken."
            )
        )
        assert result.get("rejected") is True
        assert result.get("friction_count") == 0
        assert "record_friction" in result.get("reason", "")
        # Verdict should NOT have been recorded on rejection.
        assert "verdict" not in sink

    def test_submit_verdict_allows_negative_verdict_when_friction_was_recorded(
        self, scenario: dict
    ) -> None:
        """When the agent has already recorded friction, a negative
        verdict is legitimate and should be accepted."""
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        record = next(t for t in m.tools if t.name == "record_friction")
        submit = next(t for t in m.tools if t.name == "submit_verdict")
        # Record one friction first.
        record.handler(
            category="bug",
            description="Task List 404s",
            url="/app/task",
            severity="high",
        )
        result = submit.handler(verdict="Task List is broken — 404 on every nav attempt.")
        assert result.get("ended") is True
        assert sink["verdict"][0]["text"].startswith("Task List is broken")

    def test_submit_verdict_allows_positive_verdict_without_friction(self, scenario: dict) -> None:
        """A positive/neutral verdict without any negative tokens
        passes through regardless of friction count. A trial that
        actually went smoothly produces no friction and a happy
        verdict, which is a valid outcome."""
        sink: dict = {"friction": []}
        m = build_trial_mission(scenario, base_url="http://host:1234", transcript_sink=sink)
        tool = next(t for t in m.tools if t.name == "submit_verdict")
        result = tool.handler(
            verdict="Smooth experience — I could complete my tasks without friction."
        )
        assert result.get("ended") is True
        assert sink["verdict"][0]["text"].startswith("Smooth experience")

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
# Completion criterion — #822: submit_verdict must terminate the loop
# ---------------------------------------------------------------------------


class TestTrialCompletion:
    """_trial_completion returns True iff submit_verdict is called.

    Regression guard for #822: the function previously checked
    ``action.tool_name`` which doesn't exist on AgentAction — the field
    is ``action.target``. As a result the loop never exited early and
    every trial reported outcome=max_steps even after the verdict was
    written.
    """

    def _make_action(self, action_type: ActionType, target: str | None = None) -> AgentAction:
        return AgentAction(type=action_type, target=target)

    def test_submit_verdict_tool_action_returns_true(self) -> None:
        action = self._make_action(ActionType.TOOL, "submit_verdict")
        assert _trial_completion(action, []) is True

    def test_done_action_returns_true(self) -> None:
        action = self._make_action(ActionType.DONE)
        assert _trial_completion(action, []) is True

    def test_record_friction_tool_does_not_terminate(self) -> None:
        action = self._make_action(ActionType.TOOL, "record_friction")
        assert _trial_completion(action, []) is False

    def test_navigate_action_does_not_terminate(self) -> None:
        action = self._make_action(ActionType.NAVIGATE, "/app/tickets")
        assert _trial_completion(action, []) is False

    def test_click_action_does_not_terminate(self) -> None:
        action = self._make_action(ActionType.CLICK, "#btn-save")
        assert _trial_completion(action, []) is False


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

    def test_lenient_threshold_catches_llm_variance(self) -> None:
        """#819: LLM-generated friction varies enough that 0.8 missed obvious
        duplicates. 0.65 catches paraphrased near-duplicates while leaving
        genuinely distinct findings separate (see
        ``test_dissimilar_descriptions_on_same_url_do_not_cluster``)."""
        friction = [
            {
                "category": "missing",
                "description": "The Systems page shows 'No items found' - there are no monitored systems visible.",
                "url": "/app/system",
                "severity": "high",
            },
            {
                "category": "missing",
                "description": "The Systems page shows 'No items found' with no monitored systems visible.",
                "url": "/app/system",
                "severity": "high",
            },
        ]
        report = build_trial_report(
            scenario_name="s", user_identity="Dan", friction=friction, verdict="v"
        )
        out = render_trial_report(report)
        assert "Friction observations (1 · 1 near-duplicates clustered)" in out


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


# ---------------------------------------------------------------------------
# Seed pre-flight / circuit breaker (#826)
# ---------------------------------------------------------------------------


class TestSeedPreflightAndCircuitBreaker:
    """When a blueprint has drifted, the trial harness should fail
    fast with actionable errors instead of firing hundreds of failing
    /__test__/seed POSTs. Covers #826."""

    def test_pre_flight_aborts_on_blueprint_errors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Blueprint with validation errors → seed aborts before any
        /__test__/seed POST; the first few errors are printed."""
        from dazzle.cli import qa as qa_cli

        # Fake a project dir with a blueprint file at the real path
        # the seed code looks for.
        blueprint_dir = tmp_path / "dsl" / "seeds" / "demo_data"
        blueprint_dir.mkdir(parents=True)
        (blueprint_dir / "blueprint.json").write_text('{"version": "1.0", "blueprint": {}}')

        # Stub load_blueprint + verify_blueprint to return a report
        # with errors. The test exercises the abort branch only — we
        # don't care about the exact Violation shape, just that the
        # report surfaces errors() as a non-empty list.
        class _FakeViolation:
            def __init__(self, entity: str, field: str, rule: str, message: str) -> None:
                self.entity = entity
                self.field = field
                self.rule = rule
                self.message = message

        class _FakeReport:
            def errors(self) -> list[_FakeViolation]:
                return [
                    _FakeViolation(
                        "Manuscript",
                        "id",
                        "strategy_type_mismatch",
                        "Strategy 'free_text_lorem' invalid for type 'uuid'.",
                    ),
                    _FakeViolation(
                        "Manuscript", "author_id", "unknown_entity", "Target 'Author' not found."
                    ),
                ]

        monkeypatch.setattr(
            "dazzle.core.demo_blueprint_persistence.load_blueprint",
            lambda _p: object(),
        )
        monkeypatch.setattr(
            "dazzle.demo_data.verify.verify_blueprint",
            lambda _bp, _spec: _FakeReport(),
        )

        # Stub AppSpec loader to return something truthy. The abort
        # happens before any field of the AppSpec is consulted.
        monkeypatch.setattr(
            "dazzle.cli.utils.load_project_appspec",
            lambda _p: object(),
        )

        # Stub demo_generate_impl and httpx.Client so that IF the
        # abort fails to fire we'd see a test failure elsewhere.
        def _boom(*_a: Any, **_k: Any) -> None:
            raise AssertionError("seed attempt should not reach demo_generate")

        monkeypatch.setattr("dazzle.mcp.server.handlers.demo_data.demo_generate_impl", _boom)

        qa_cli._seed_demo_data_for_trial(tmp_path, "http://localhost:9999", "test-secret")
        out = capsys.readouterr()
        err = out.err
        assert "Seed aborted" in err
        assert "2 validation error(s)" in err
        assert "Manuscript.id" in err
        assert "strategy_type_mismatch" in err

    def test_circuit_breaker_trips_after_consecutive_failures(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When /__test__/seed returns 400 repeatedly, seed loop
        aborts after 10 consecutive failures and prints a
        circuit-breaker message pointing at `dazzle demo verify`."""
        from dazzle.cli import qa as qa_cli

        # No blueprint — skip the pre-flight branch. We need
        # existing_data to force the data-dir path.
        data_dir = tmp_path / "demo_jsonl"
        data_dir.mkdir()
        # Seed 20 fixtures so the circuit breaker can trip at 10.
        (data_dir / "Manuscript.jsonl").write_text(
            "\n".join('{"id": "' + f"row-{i}" + '"}' for i in range(20)) + "\n"
        )

        # Stub AppSpec loader + entity topological sort + data-dir
        # discovery. The source-module patches propagate into
        # `from ... import X` statements inside the target function.
        class _FakeEntity:
            def __init__(self, name: str) -> None:
                self.name = name
                self.fields = []

        class _FakeDomain:
            entities = [_FakeEntity("Manuscript")]

        class _FakeAppSpec:
            domain = _FakeDomain()

        monkeypatch.setattr(
            "dazzle.cli.utils.load_project_appspec",
            lambda _p: _FakeAppSpec(),
        )
        monkeypatch.setattr(
            "dazzle.demo_data.loader.topological_sort_entities",
            lambda _entities: ["Manuscript"],
        )
        monkeypatch.setattr(
            "dazzle.cli.demo._find_data_dir",
            lambda _p: data_dir,
        )

        # Stub httpx.Client so every POST returns 400. Record how
        # many attempts happened before the circuit broke.
        post_count = {"n": 0}

        class _FakeResp:
            status_code = 400
            text = 'invalid input syntax for type uuid: "row-0"'

            def json(self) -> dict[str, Any]:
                return {"created": {}}

        class _FakeClient:
            def __init__(self, *_a: Any, **_k: Any) -> None:
                pass

            def __enter__(self) -> _FakeClient:
                return self

            def __exit__(self, *_a: Any) -> None:
                return None

            def post(self, *_a: Any, **_k: Any) -> _FakeResp:
                post_count["n"] += 1
                return _FakeResp()

        monkeypatch.setattr("httpx.Client", _FakeClient)

        qa_cli._seed_demo_data_for_trial(tmp_path, "http://localhost:9999", "test-secret")
        out = capsys.readouterr()
        # Should have stopped at 10 consecutive failures, not iterated
        # through all 20 fixtures.
        assert post_count["n"] == 10, f"expected circuit at 10, got {post_count['n']}"
        assert "Seed aborted" in out.err
        assert "10 consecutive failures" in out.err
        assert "dazzle demo verify" in out.err
