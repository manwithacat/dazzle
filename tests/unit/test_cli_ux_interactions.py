"""Unit tests for ``dazzle ux verify --interactions`` plumbing.

The full ``run_interaction_walk`` function needs a live browser +
server subprocess — that lives under ``tests/e2e/`` with the
``e2e`` mark. Here we cover the pure pieces:

- ``_build_default_walk`` — walk assembly from layout JSON
- ``_render_human_report`` / ``_render_json_report`` — output format
- Exit-code constants are stable
"""

from __future__ import annotations

import json

from dazzle.cli.ux_interactions import (
    EXIT_PASS,
    EXIT_REGRESSION,
    EXIT_SETUP_FAILURE,
    _build_default_walk,
    _render_human_report,
    _render_json_report,
)
from dazzle.testing.ux.interactions import (
    CardAddInteraction,
    CardDragInteraction,
    CardRemoveReachableInteraction,
    InteractionResult,
)


class TestExitCodes:
    def test_constants_stable(self) -> None:
        # CI gating depends on these staying fixed.
        assert EXIT_PASS == 0
        assert EXIT_REGRESSION == 1
        assert EXIT_SETUP_FAILURE == 2


class TestBuildDefaultWalk:
    def test_full_walk_when_cards_and_catalog_present(self) -> None:
        walk = _build_default_walk(
            card_ids=["card-0", "card-1"],
            catalog_regions=["alert_severity", "ticket_board"],
        )
        assert len(walk) == 3
        # Order: remove_reachable → drag → add
        assert isinstance(walk[0], CardRemoveReachableInteraction)
        assert isinstance(walk[1], CardDragInteraction)
        assert isinstance(walk[2], CardAddInteraction)
        # Remove + drag target the first card; add targets the first
        # catalog region.
        assert walk[0].card_id == "card-0"
        assert walk[1].card_id == "card-0"
        assert walk[2].region == "alert_severity"

    def test_no_cards_skips_remove_and_drag(self) -> None:
        walk = _build_default_walk(card_ids=[], catalog_regions=["ticket_board"])
        assert len(walk) == 1
        assert isinstance(walk[0], CardAddInteraction)

    def test_no_catalog_skips_add(self) -> None:
        walk = _build_default_walk(card_ids=["card-0"], catalog_regions=[])
        assert len(walk) == 2
        assert isinstance(walk[0], CardRemoveReachableInteraction)
        assert isinstance(walk[1], CardDragInteraction)

    def test_empty_everything_returns_empty_walk(self) -> None:
        # Caller treats an empty walk as setup failure — make sure we
        # produce the empty list deterministically rather than crashing.
        assert _build_default_walk(card_ids=[], catalog_regions=[]) == []

    def test_non_editable_grid_skips_card_remove_reachable(self) -> None:
        # #1204: when the grid isn't editable, the Remove-card button is
        # intentionally absent — the walk skips the reachability check
        # rather than treating it as a regression. card_drag still runs
        # (the drag handle is present regardless of edit mode).
        walk = _build_default_walk(
            card_ids=["card-0"],
            catalog_regions=["ticket_board"],
            editable=False,
        )
        names = [type(w).__name__ for w in walk]
        assert "CardRemoveReachableInteraction" not in names
        assert "CardDragInteraction" in names
        assert "CardAddInteraction" in names

    def test_editable_grid_includes_card_remove_reachable(self) -> None:
        # The complementary positive case — editable=True keeps the
        # full walk shape that existed before #1204.
        walk = _build_default_walk(
            card_ids=["card-0"],
            catalog_regions=["ticket_board"],
            editable=True,
        )
        names = [type(w).__name__ for w in walk]
        assert "CardRemoveReachableInteraction" in names
        assert "CardDragInteraction" in names
        assert "CardAddInteraction" in names


class TestHumanReport:
    def test_all_pass(self) -> None:
        results = [
            InteractionResult(name="card_remove_reachable", passed=True),
            InteractionResult(name="card_drag", passed=True, evidence={"dy": 200.0}),
        ]
        report = _render_human_report(results)
        assert "[PASS] card_remove_reachable" in report
        assert "[PASS] card_drag" in report
        assert "dy=200.0" in report

    def test_failure_includes_reason_line(self) -> None:
        results = [
            InteractionResult(
                name="card_drag",
                passed=False,
                reason="card didn't move — dy=0",
                evidence={"dy": 0.0},
            ),
        ]
        report = _render_human_report(results)
        assert "[FAIL] card_drag" in report
        assert "reason: card didn't move — dy=0" in report

    def test_empty_results_message(self) -> None:
        report = _render_human_report([])
        assert "No interactions ran" in report


class TestJsonReport:
    def test_valid_json(self) -> None:
        results = [
            InteractionResult(name="card_drag", passed=True, evidence={"dx": 0.0, "dy": 220.0}),
        ]
        payload = json.loads(_render_json_report(results))
        assert payload["count"] == 1
        assert payload["passed"] is True
        assert payload["results"][0]["name"] == "card_drag"
        assert payload["results"][0]["evidence"]["dy"] == 220.0

    def test_mixed_passes_marks_overall_failed(self) -> None:
        results = [
            InteractionResult(name="a", passed=True),
            InteractionResult(name="b", passed=False, reason="boom"),
        ]
        payload = json.loads(_render_json_report(results))
        assert payload["passed"] is False
        assert payload["count"] == 2


class TestContextSelectorWalk:
    """#1304: `_build_context_selector_walk` discovers workspaces declaring a
    `context_selector` from the appspec and emits one self-navigating gesture
    each — generic, so projects without one get a clean no-op."""

    def test_support_tickets_yields_agent_console_gesture(self) -> None:
        from pathlib import Path

        from dazzle.cli.ux_interactions import _build_context_selector_walk
        from dazzle.testing.ux.interactions import ContextSelectInteraction

        root = Path(__file__).resolve().parents[2] / "examples" / "support_tickets"
        walk = _build_context_selector_walk(root)

        assert walk, "expected a context_select gesture for support_tickets' agent_console"
        assert all(isinstance(g, ContextSelectInteraction) for g in walk)
        assert "agent_console" in {g.workspace for g in walk}

    def test_project_without_context_selector_yields_empty(self) -> None:
        from pathlib import Path

        from dazzle.cli.ux_interactions import _build_context_selector_walk

        # simple_task has no context_selector → no gesture (clean N/A).
        root = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        assert _build_context_selector_walk(root) == []
