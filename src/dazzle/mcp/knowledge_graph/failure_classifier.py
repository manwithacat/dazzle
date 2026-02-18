"""
Classify test failures into actionable categories.

Pure function — no side effects, no imports beyond stdlib.
"""

from __future__ import annotations


def classify_failure(
    test_id: str,
    category: str,
    error_message: str | None,
    failed_step: dict[str, str] | None = None,
) -> str:
    """Classify a test failure into a failure type.

    Args:
        test_id: Test identifier (e.g. "CRUD_Task_create").
        category: Test category (e.g. "crud", "state_machine").
        error_message: Error message from the test runner.
        failed_step: Optional dict with action/target/message of the failed step.

    Returns:
        One of: "rbac_denied", "validation_error", "dsl_surface_gap",
        "state_machine", "timeout", "framework_bug", "unknown".
    """
    haystack = (error_message or "").lower()
    step_msg = (failed_step.get("message", "") if failed_step else "").lower()
    combined = f"{haystack} {step_msg}"

    # RBAC / permission errors
    if any(kw in combined for kw in ("401", "403", "forbidden", "permission")):
        return "rbac_denied"

    # Validation errors
    if any(kw in combined for kw in ("required", "validation", "422")):
        return "validation_error"

    # Missing surface / route
    if any(kw in combined for kw in ("404", "not found", "no surface")):
        return "dsl_surface_gap"

    # State machine issues
    if "transition" in combined or test_id.startswith("SM_"):
        return "state_machine"

    # Timeouts
    if any(kw in combined for kw in ("timeout", "timed out")):
        return "timeout"

    # Framework / server errors
    if any(kw in combined for kw in ("500", "internal server error", "connection refused")):
        return "framework_bug"

    return "unknown"
