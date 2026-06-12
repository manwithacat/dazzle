"""#1375: a dead agent loop must surface as a nonzero trial exit.

``dazzle qa trial`` previously printed "Trial complete. 0 friction
observation(s)" and exited 0 when the LLM hard-failed at step 1
(observed live twice: Anthropic billing 400, then a claude-cli
error_max_turns). Autonomous consumers read the exit code, so that
booked infrastructure failures as clean PASSes.
"""

from dazzle.qa.trial_report import trial_abort_message


class TestTrialAbortMessage:
    def test_error_outcome_aborts(self) -> None:
        msg = trial_abort_message("error", "LLM error at step 1: credit balance too low")
        assert msg is not None
        assert "ABORTED" in msg
        assert "credit balance too low" in msg
        assert "before any step completed" in msg

    def test_error_after_progress_names_step_count(self) -> None:
        msg = trial_abort_message("error", "LLM error at step 4: boom", step_count=3)
        assert msg is not None
        assert "after 3 completed step(s)" in msg

    def test_error_without_detail_still_aborts(self) -> None:
        msg = trial_abort_message("error", None)
        assert msg is not None
        assert "unknown agent-loop error" in msg

    def test_completed_outcome_passes(self) -> None:
        assert trial_abort_message("completed", None) is None

    def test_budget_exceeded_is_not_an_abort(self) -> None:
        """The persona ran and produced signal — max-steps/budget exits
        are legitimate trial results, not infrastructure failures."""
        assert trial_abort_message("budget_exceeded", None, step_count=25) is None
