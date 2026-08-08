"""Load hyperpart → DSL authoring shape catalogue (agent-facing).

Pairs with ``packages/hatchi-maxchi/docs/agent/hyperpart_dsl_shapes.toml``.
Every HM hyperpart must have a rational shape: live path, planned emitter,
or explicit chrome_only/refuse — no undocumented invent.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

REPO = Path(__file__).resolve().parents[3]
CATALOGUE_PATH = (
    REPO / "packages" / "hatchi-maxchi" / "docs" / "agent" / "hyperpart_dsl_shapes.toml"
)


@dataclass(frozen=True)
class PartShape:
    id: str
    class_: str
    layer: str
    dsl: str
    status: str  # live | planned | chrome_only | refuse
    job: str
    agent_surface: str

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class": self.class_,
            "layer": self.layer,
            "dsl": self.dsl,
            "status": self.status,
            "job": self.job,
            "agent_surface": self.agent_surface,
        }


@lru_cache(maxsize=1)
def load_shapes(path: Path | None = None) -> tuple[PartShape, ...]:
    p = path or CATALOGUE_PATH
    if not p.is_file():
        return ()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    rows: list[PartShape] = []
    for raw in list(data.get("part") or []):
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "").strip()
        if not pid:
            continue
        rows.append(
            PartShape(
                id=pid,
                class_=str(raw.get("class") or "").strip(),
                layer=str(raw.get("layer") or "").strip(),
                dsl=str(raw.get("dsl") or "").strip(),
                status=str(raw.get("status") or "planned").strip(),
                job=str(raw.get("job") or "").strip(),
                agent_surface=str(raw.get("agent_surface") or "").strip(),
            )
        )
    return tuple(rows)


def shapes_snapshot() -> dict[str, Any]:
    rows = load_shapes()
    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    planned_ids: list[str] = []
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_class[r.class_] = by_class.get(r.class_, 0) + 1
        if r.status == "planned":
            planned_ids.append(r.id)
    return {
        "schema_version": 1,
        "path": str(CATALOGUE_PATH.relative_to(REPO)) if CATALOGUE_PATH.is_file() else None,
        "count": len(rows),
        "by_status": by_status,
        "by_class": by_class,
        "planned_ids": planned_ids,
        "planned": len(planned_ids),
        "live": by_status.get("live", 0),
        "chrome_only": by_status.get("chrome_only", 0),
        "next_planned": planned_ids[0] if planned_ids else None,
        "doctrine": (
            "docs/superpowers/specs/2026-08-07-hyperpart-emitter-scenario-cognition-design.md"
        ),
    }


def agent_shape_table() -> list[dict[str, str]]:
    """Compact rows for agent pick surfaces / MCP."""
    return [
        {
            "id": r.id,
            "dsl": r.dsl,
            "status": r.status,
            "agent_surface": r.agent_surface,
            "job": r.job,
        }
        for r in load_shapes()
    ]
