"""Still empty-hero floors for felt demo quality (#1626 P0-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PLATFORM_STILL_PREFIX = "_platform_admin_"

# When still file exists under app screenshots — skip if absent (CI often
# has no gitignored .dazzle stills).
HERO_MIN_BYTES: dict[str, dict[str, int]] = {
    "invoice_ops": {
        "approval_desk_approver_desktop_light.png": 80_000,
        "pay_desk_finance_desktop_light.png": 70_000,
    },
    "support_tickets": {
        "manager_ops_manager_desktop_light.png": 80_000,
    },
    "simple_task": {
        "task_board_manager_desktop_light.png": 90_000,
        "my_work_member_desktop_light.png": 60_000,
    },
}


@dataclass
class StillScore:
    name: str
    path: str | None
    size: int
    min_bytes: int
    residual: bool
    reason: str


def _shot_dir(app_dir: Path) -> Path | None:
    for p in (
        app_dir / ".dazzle" / "qa" / "screenshots",
        app_dir / "screenshots",
    ):
        if p.is_dir():
            return p
    return None


def score_stills(app_dir: Path, app_name: str) -> list[StillScore]:
    """Score known hero stills when present."""
    shots = _shot_dir(app_dir)
    floors = HERO_MIN_BYTES.get(app_name) or {}
    out: list[StillScore] = []
    if shots is None:
        return out

    # platform-only check
    pngs = list(shots.glob("*.png"))
    if pngs:
        product = [p for p in pngs if not p.name.startswith(PLATFORM_STILL_PREFIX)]
        if not product:
            out.append(
                StillScore(
                    name="*",
                    path=str(shots),
                    size=0,
                    min_bytes=0,
                    residual=True,
                    reason="stills_platform_only",
                )
            )

    for name, min_b in floors.items():
        path = shots / name
        if not path.is_file():
            continue  # absent stills skipped (CI)
        size = path.stat().st_size
        residual = size < min_b
        out.append(
            StillScore(
                name=name,
                path=str(path),
                size=size,
                min_bytes=min_b,
                residual=residual,
                reason=f"empty_hero:{name}={size}<{min_b}" if residual else "ok",
            )
        )
    return out
