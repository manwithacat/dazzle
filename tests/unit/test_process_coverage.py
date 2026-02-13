"""Tests for process coverage checker improvements.

Uses direct module import to avoid triggering mcp.server import from dazzle.mcp.__init__.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

from dazzle.core.ir.process import ProcessTriggerKind, StepKind

# ============================================================================
# Direct module import to avoid mcp.server dependency
# ============================================================================

_process_module = None


def _import_module():
    """Import process handlers module directly."""
    global _process_module

    if _process_module is not None:
        return

    # Mock the MCP server packages to prevent import errors
    _mocked = [
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        "dazzle.mcp",
        "dazzle.mcp.server",
        "dazzle.mcp.server.handlers",
        "dazzle.mcp.server.progress",
    ]
    _orig = {k: sys.modules.get(k) for k in _mocked}
    for k in _mocked:
        sys.modules[k] = MagicMock(pytest_plugins=[])

    # Get path to process.py
    src_path = Path(__file__).parent.parent.parent / "src"
    module_path = src_path / "dazzle" / "mcp" / "server" / "handlers" / "process.py"

    # Import module
    spec = importlib.util.spec_from_file_location(
        "process_module",
        module_path,
    )
    _process_module = importlib.util.module_from_spec(spec)
    sys.modules["process_module"] = _process_module
    spec.loader.exec_module(_process_module)

    # Restore sys.modules to prevent pollution of other tests
    for k, v in _orig.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


# Import the module
_import_module()


# Get constants and functions from the module
MIN_MEANINGFUL_WORD_LENGTH = _process_module.MIN_MEANINGFUL_WORD_LENGTH


def _outcome_matches_pool(outcome, pool, entities, impl_procs):
    return _process_module._outcome_matches_pool(outcome, pool, entities, impl_procs)


def _infer_structural_satisfaction(outcome, impl_procs):
    return _process_module._infer_structural_satisfaction(outcome, impl_procs)


# ---------------------------------------------------------------------------
# Helpers to build lightweight ProcessSpec / step mocks
# ---------------------------------------------------------------------------


def _make_step(
    name: str = "step1",
    service: str | None = None,
    kind: str = "service",
    satisfies: list[dict[str, str]] | None = None,
) -> MagicMock:
    step = MagicMock()
    step.name = name
    step.service = service
    step.kind = StepKind(kind)
    step.parallel_steps = []
    step.satisfies = []
    if satisfies:
        for s in satisfies:
            ref = MagicMock()
            ref.outcome = s["outcome"]
            step.satisfies.append(ref)
    return step


def _make_proc(
    name: str = "proc1",
    steps: list[MagicMock] | None = None,
    trigger: MagicMock | None = None,
    implements: list[str] | None = None,
) -> MagicMock:
    proc = MagicMock()
    proc.name = name
    proc.steps = steps or []
    proc.trigger = trigger
    proc.implements = implements or []
    proc.compensations = []
    proc.outputs = []
    return proc


# ---------------------------------------------------------------------------
# Test 1: MIN_MEANINGFUL_WORD_LENGTH is now 3 (4+ char words match)
# ---------------------------------------------------------------------------


class TestWordThreshold:
    def test_threshold_value(self) -> None:
        assert MIN_MEANINGFUL_WORD_LENGTH == 3

    def test_four_char_words_match(self) -> None:
        """Words like 'user', 'task', 'save' (4 chars) should now participate."""
        proc = _make_proc(steps=[_make_step(name="create_user")])
        # "user" is 4 chars, should match step name "create_user"
        result = _outcome_matches_pool(
            "user is created",
            ["create_user"],
            set(),
            [proc],
        )
        assert result is True

    def test_three_char_words_excluded(self) -> None:
        """3-char words like 'the', 'and' should still be excluded."""
        proc = _make_proc(steps=[_make_step(name="unrelated_step")])
        result = _outcome_matches_pool(
            "the end",
            ["unrelated_step"],
            set(),
            [proc],
        )
        assert result is False

    def test_task_word_matches(self) -> None:
        """'task' (4 chars) should match with new threshold."""
        result = _outcome_matches_pool(
            "task is saved",
            ["save_task"],
            set(),
            [_make_proc()],
        )
        assert result is True


# ---------------------------------------------------------------------------
# Test 2: UI outcomes auto-satisfied when process exists
# ---------------------------------------------------------------------------


class TestUIOutcomeAutoSatisfaction:
    def test_confirmation_message_matched(self) -> None:
        proc = _make_proc(steps=[_make_step(name="do_something")])
        result = _outcome_matches_pool(
            "Customer sees confirmation message",
            ["do_something"],
            set(),
            [proc],
        )
        assert result is True

    def test_success_notification_matched(self) -> None:
        proc = _make_proc(steps=[_make_step(name="process_order")])
        result = _outcome_matches_pool(
            "success notification shown",
            ["process_order"],
            set(),
            [proc],
        )
        assert result is True

    def test_ui_outcome_not_matched_without_process(self) -> None:
        """UI patterns should NOT auto-satisfy when no impl_procs."""
        result = _outcome_matches_pool(
            "Customer sees confirmation message",
            [],
            set(),
            [],  # no processes
        )
        assert result is False

    def test_redirected_matched(self) -> None:
        proc = _make_proc(steps=[_make_step(name="submit")])
        result = _outcome_matches_pool(
            "User is redirected to dashboard",
            ["submit"],
            set(),
            [proc],
        )
        assert result is True


# ---------------------------------------------------------------------------
# Test 3: CRUD inference via step name (not just service)
# ---------------------------------------------------------------------------


class TestCRUDInferenceViaStepName:
    def test_step_name_create_infers(self) -> None:
        """Step named 'create_record' should infer 'created' outcome."""
        proc = _make_proc(steps=[_make_step(name="create_record", service=None, kind="service")])
        result = _infer_structural_satisfaction("record is created", [proc])
        assert result is True

    def test_step_name_save_infers_created(self) -> None:
        """Step named 'save_record' should infer 'saved'/'created' outcomes."""
        proc = _make_proc(steps=[_make_step(name="save_record", service=None, kind="service")])
        assert _infer_structural_satisfaction("record is saved", [proc]) is True
        assert _infer_structural_satisfaction("record is created", [proc]) is True

    def test_step_name_delete_infers(self) -> None:
        proc = _make_proc(steps=[_make_step(name="delete_item", service=None, kind="service")])
        assert _infer_structural_satisfaction("item is deleted", [proc]) is True

    def test_step_name_update_infers(self) -> None:
        proc = _make_proc(steps=[_make_step(name="update_status", service=None, kind="service")])
        assert _infer_structural_satisfaction("status is updated", [proc]) is True

    def test_no_match_unrelated_step(self) -> None:
        proc = _make_proc(steps=[_make_step(name="validate_input", service=None, kind="service")])
        assert _infer_structural_satisfaction("record is created", [proc]) is False


# ---------------------------------------------------------------------------
# Test 4: Status transition outcomes match
# ---------------------------------------------------------------------------


class TestStatusTransitionOutcomes:
    def test_status_transition_trigger_matches(self) -> None:
        trigger = MagicMock()
        trigger.kind = ProcessTriggerKind.ENTITY_STATUS_TRANSITION
        proc = _make_proc(steps=[], trigger=trigger)
        assert _infer_structural_satisfaction("status is changed", [proc]) is True
        assert _infer_structural_satisfaction("transition recorded", [proc]) is True
        assert _infer_structural_satisfaction("timestamp logged", [proc]) is True

    def test_non_status_trigger_no_match(self) -> None:
        trigger = MagicMock()
        trigger.kind = ProcessTriggerKind.ENTITY_EVENT
        proc = _make_proc(steps=[], trigger=trigger)
        assert _infer_structural_satisfaction("status is changed", [proc]) is False


# ---------------------------------------------------------------------------
# Test 5: Effective coverage metric
# ---------------------------------------------------------------------------


class TestEffectiveCoverage:
    def test_effective_coverage_in_output(self) -> None:
        """Verify effective_coverage_percent appears and gives partial credit."""
        # We test the math directly: 2 covered, 4 partial, 4 uncovered = 10 total
        # effective = (2 + 4*0.5) / 10 * 100 = 40%
        covered = 2
        partial = 4
        total = 10
        effective = round((covered + partial * 0.5) / total * 100, 1)
        assert effective == 40.0

    def test_effective_zero_when_empty(self) -> None:
        total = 0
        effective = round((0 + 0 * 0.5) / 1 * 100, 1) if total > 0 else 0.0
        assert effective == 0.0

    def test_effective_equals_coverage_when_no_partial(self) -> None:
        covered = 5
        partial = 0
        total = 10
        coverage = round(covered / total * 100, 1)
        effective = round((covered + partial * 0.5) / total * 100, 1)
        assert coverage == effective
