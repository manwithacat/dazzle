# === AUTO-GENERATED HEADER ================================================
# Service ID: calculate_overdue_penalty
# Kind: domain_logic
# Description: Calculate penalty for overdue tasks
# Input:
#   - task_id: uuid (required)
# Output:
#   - penalty_amount: decimal
#   - reason: str
# Guarantees:
#   - Returns 0 if task is not overdue.
# ==========================================================================

from typing import TypedDict


class CalculateOverduePenaltyResult(TypedDict):
    penalty_amount: float
    reason: str


def calculate_overdue_penalty(task_id: str) -> CalculateOverduePenaltyResult:
    """
    IMPLEMENTATION SECTION - Edit below this line.
    The header above will be regenerated; this body will NOT be overwritten.

    This is a domain service that demonstrates the stub pattern.
    Complex business logic lives here, not in the DSL.
    """
    # In a real implementation, you would:
    # 1. Fetch the task from the repository
    # 2. Check if it's overdue
    # 3. Calculate the penalty based on business rules

    # For demo purposes, we'll just return a sample calculation
    # Assume task is 3 days overdue with $5/day penalty
    days_overdue = 3
    penalty_per_day = 5.00

    if days_overdue <= 0:
        return {
            "penalty_amount": 0.0,
            "reason": "Task is not overdue",
        }

    penalty = days_overdue * penalty_per_day
    return {
        "penalty_amount": penalty,
        "reason": f"Task is {days_overdue} days overdue at ${penalty_per_day}/day",
    }


# Example usage (for testing):
if __name__ == "__main__":
    result = calculate_overdue_penalty("task-123")
    print(f"Penalty: ${result['penalty_amount']:.2f}")
    print(f"Reason: {result['reason']}")
