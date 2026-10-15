"""Slice AuditSpec for per-document agent context."""

from typing import Any


def slice_auditspec(
    auditspec: dict[str, Any],
    controls: list[str] | str = "all",
    status_filter: list[str] | None = None,
    extract: list[str] | None = None,
    tier_filter: list[int] | None = None,
) -> dict[str, Any]:
    """Slice an AuditSpec to a subset of controls.

    Accepts either the new typed AuditSpec schema (control_id, tier as field)
    or the legacy dict schema (id, gaps list).
    """
    all_controls = auditspec["controls"]
    filtered = list(all_controls)

    if controls != "all":
        # Support both new schema (control_id) and legacy (id)
        filtered = [c for c in filtered if c.get("control_id", c.get("id")) in controls]

    if status_filter:
        filtered = [c for c in filtered if c["status"] in status_filter]

    if extract:
        filtered = [
            c for c in filtered if any(e["construct"] in extract for e in c.get("evidence", []))
        ]

    if tier_filter:
        filtered = [
            c
            for c in filtered
            if c.get("tier") in tier_filter
            or any(g.get("tier") in tier_filter for g in c.get("gaps", []))
        ]

    summary: dict[str, Any] = {
        "total_controls": len(filtered),
        "evidenced": sum(1 for c in filtered if c["status"] == "evidenced"),
        "partial": sum(1 for c in filtered if c["status"] == "partial"),
        "gaps": sum(1 for c in filtered if c["status"] == "gap"),
        "excluded": sum(1 for c in filtered if c.get("status") == "excluded"),
    }

    return {**auditspec, "controls": filtered, "summary": summary}
