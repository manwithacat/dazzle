"""Load DocumentSpec YAML and slice AuditSpec for per-document agent context."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_document_spec(path: Path) -> dict:
    """Load a DocumentSpec YAML file. Returns the document_pack dict."""
    raw = yaml.safe_load(path.read_text())
    return raw["document_pack"]


def slice_auditspec(
    auditspec: dict,
    controls: list[str] | str = "all",
    status_filter: list[str] | None = None,
    extract: list[str] | None = None,
    tier_filter: list[int] | None = None,
) -> dict:
    """Slice an AuditSpec to a subset of controls."""
    filtered = auditspec["controls"]

    if controls != "all":
        filtered = [c for c in filtered if c["id"] in controls]

    if status_filter:
        filtered = [c for c in filtered if c["status"] in status_filter]

    if extract:
        filtered = [
            c for c in filtered if any(e["construct"] in extract for e in c.get("evidence", []))
        ]

    if tier_filter:
        filtered = [
            c for c in filtered if any(g.get("tier") in tier_filter for g in c.get("gaps", []))
        ]

    summary = {
        "total_controls": len(filtered),
        "evidenced": sum(1 for c in filtered if c["status"] == "evidenced"),
        "partial": sum(1 for c in filtered if c["status"] == "partial"),
        "gaps": sum(1 for c in filtered if c["status"] == "gap"),
    }

    return {**auditspec, "controls": filtered, "summary": summary}
