"""Tests for handler progress instrumentation."""

import json
import time


class TestPipelineInstrumentation:
    """Verify pipeline.run emits structured context_json."""

    def test_pipeline_result_has_summary(self):
        """Pipeline JSON result should include a 'summary' key."""
        from dazzle.mcp.server.handlers.orchestration import aggregate_results

        step_results = [
            {"step": 1, "operation": "dsl(validate)", "status": "passed", "duration_ms": 100},
            {"step": 2, "operation": "dsl(lint)", "status": "passed", "duration_ms": 200},
        ]
        errors: list[str] = []
        start = time.monotonic() - 0.5  # simulate 500ms ago

        result_json = aggregate_results(step_results, errors, start, detail="metrics")
        result = json.loads(result_json)
        assert "summary" in result
        assert result["summary"]["total_steps"] == 2
        assert result["summary"]["passed"] == 2

    def test_run_step_context_json_in_activity_log(self):
        """run_step should include context_json when logging to activity store."""
        from unittest.mock import MagicMock

        from dazzle.mcp.server.handlers.orchestration import QualityStep, run_step

        # Create a mock activity store
        store = MagicMock()

        def fake_handler():
            return json.dumps({"status": "valid", "entities": 5})

        step = QualityStep(name="dsl(validate)", handler=fake_handler)
        result = run_step(step, activity_store=store)

        assert result["status"] == "passed"
        # Verify tool_end was called with context_json
        tool_end_call = store.log_event.call_args_list[-1]
        assert tool_end_call[0][0] == "tool_end"
        assert "context_json" in tool_end_call[1]
        ctx = json.loads(tool_end_call[1]["context_json"])
        assert ctx["operation"] == "dsl(validate)"
        assert ctx["status"] == "passed"


class TestProgressExtraction:
    """Verify extract_progress returns a usable object."""

    def test_extract_progress_returns_noop_for_none(self):
        from dazzle.mcp.server.handlers.common import extract_progress

        progress = extract_progress(None)
        # Should not raise
        progress.log_sync("test message")
        progress.advance_sync(1, 10, "step 1")

    def test_extract_progress_returns_noop_for_empty_args(self):
        from dazzle.mcp.server.handlers.common import extract_progress

        progress = extract_progress({})
        # Should not raise
        progress.log_sync("test message")
        progress.advance_sync(1, 10, "step 1")
