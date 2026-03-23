"""Generate review data for human-in-the-loop workflow."""

from __future__ import annotations

from typing import Any


def generate_review_data(auditspec: dict[str, Any]) -> dict[str, Any]:
    """Generate review tracking structure for tier 2/3 gaps."""
    reviews: list[dict[str, Any]] = []
    for control in auditspec.get("controls", []):
        for gap in control.get("gaps", []):
            tier = gap.get("tier", 1)
            if tier >= 2:
                reviews.append(
                    {
                        "control_id": control["id"],
                        "control_name": control.get("name", ""),
                        "tier": tier,
                        "status": "draft" if tier == 2 else "stub",
                        "description": gap.get("description", ""),
                        "action": gap.get("action", ""),
                        "resolved": False,
                    }
                )

    return {"pending_reviews": reviews}


# Backward-compatible alias
generate_review_yaml = generate_review_data
