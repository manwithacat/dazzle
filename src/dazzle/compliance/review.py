"""Generate review data for human-in-the-loop workflow."""

from __future__ import annotations

from typing import Any


def generate_review_data(auditspec: dict[str, Any]) -> dict[str, Any]:
    """Generate review tracking structure for tier 2/3 controls.

    Accepts either the new typed AuditSpec schema (control_id, tier as field,
    gap_description/action as direct fields) or the legacy dict schema
    (id, gaps list with nested tier/description/action).
    """
    reviews: list[dict[str, Any]] = []
    for control in auditspec.get("controls", []):
        # New schema: tier is a direct field on each control
        tier = control.get("tier")
        if tier is not None and tier >= 2:
            reviews.append(
                {
                    "control_id": control.get("control_id", control.get("id", "")),
                    "control_name": control.get("control_name", control.get("name", "")),
                    "tier": tier,
                    "status": "draft" if tier == 2 else "stub",
                    "description": control.get("gap_description", ""),
                    "action": control.get("action", ""),
                    "resolved": False,
                }
            )
        else:
            # Legacy schema: gaps is a list of dicts
            for gap in control.get("gaps", []):
                gap_tier = gap.get("tier", 1)
                if gap_tier >= 2:
                    reviews.append(
                        {
                            "control_id": control.get("id", control.get("control_id", "")),
                            "control_name": control.get("name", control.get("control_name", "")),
                            "tier": gap_tier,
                            "status": "draft" if gap_tier == 2 else "stub",
                            "description": gap.get("description", ""),
                            "action": gap.get("action", ""),
                            "resolved": False,
                        }
                    )

    return {"pending_reviews": reviews}
