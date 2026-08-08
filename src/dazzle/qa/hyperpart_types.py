"""Shared types for hyperpart opportunity / scenario scanners (no I/O)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class HyperpartOpportunity:
    """One place a hyperpart should be considered or is now default-emitted."""

    hyperpart: str  # avatar | queue | badge | money | …
    kind: str  # person_ref | work_queue | …
    entity: str
    field: str
    surface: str
    location: str  # human path, e.g. surface TaskList.field.assigned_to
    status: str
    # emit_covered | emit_partial | author_action | matrix_miss | planned_emitter | verify
    severity: str  # low | medium | high
    description: str
    ownership: str = "framework"  # framework default vs product authoring
    notes: str = ""
    hosts: str = ""  # comma-separated hosts known to render this field

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_friction(self) -> dict[str, Any]:
        # planned_emitter is framework work — category other so example-apps
        # auto_seed does not claim it as product missing.
        return {
            "category": "missing" if self.status in ("author_action", "matrix_miss") else "other",
            "severity": self.severity,
            "description": self.description,
            "url": self.location,
            "evidence": (
                f"hyperpart={self.hyperpart} kind={self.kind} "
                f"entity={self.entity}.{self.field} status={self.status} "
                f"hosts={self.hosts} {self.notes}"
            ),
            "blocks_pilot": False,
            "ownership": self.ownership,
        }
