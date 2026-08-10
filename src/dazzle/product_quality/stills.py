"""Still empty-hero floors for felt demo quality (#1626 P0-6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PLATFORM_STILL_PREFIX = "_platform_admin_"

# When still file exists under app screenshots — skip if absent (CI often
# has no gitignored .dazzle stills). Floors are empty-hero gates only — not
# human composite scores (#1626 antagonist re-score 2026-07-31).
HERO_MIN_BYTES: dict[str, dict[str, int]] = {
    "ops_dashboard": {
        "incident_review_ops_engineer_desktop_light.png": 90000,
        "command_center_ops_engineer_desktop_light.png": 80000,
    },
    "hr_records": {
        "staff_directory_hr_admin_desktop_light.png": 100000,
    },
    "contact_manager": {
        "contacts_user_desktop_light.png": 70000,
    },
    "invoice_ops": {
        "my_invoices_requester_desktop_light.png": 60000,
        "audit_review_auditor_desktop_light.png": 60000,
        "pay_desk_finance_desktop_light.png": 70000,
        "approval_desk_approver_desktop_light.png": 80000,
        "finance_ops_finance_desktop_light.png": 70000,
        # Post-5.8 Goal B document: composition desk stays line-dense with INV numbers.
        "line_items_desk_finance_desktop_light.png": 100000,
    },
    "fieldtest_hub": {
        "issue_triage_manager_desktop_light.png": 90000,
        "device_fleet_manager_desktop_light.png": 90000,
    },
    "simple_task": {
        # Above-fold recapture is ~900px; 80k was calibrated on taller composites.
        "team_overview_manager_desktop_light.png": 65000,
        "task_board_manager_desktop_light.png": 90000,
        "my_work_member_desktop_light.png": 60000,
        # Post-5.8 Goal B: Discussion desk must stay conversation-dense (not empty trail).
        "comments_desk_manager_desktop_light.png": 100000,
    },
    "support_tickets": {
        "manager_ops_manager_desktop_light.png": 80000,
        "ticket_queue_agent_desktop_light.png": 90000,
        "my_tickets_customer_desktop_light.png": 60000,
    },
    "project_tracker": {
        "project_board_manager_desktop_light.png": 120000,
        "dashboard_manager_desktop_light.png": 100000,
    },
    "design_studio": {
        "asset_catalog_designer_desktop_light.png": 100000,
        "brand_desk_designer_desktop_light.png": 100000,
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


def is_lfs_pointer(path: Path) -> bool:
    """True when *path* is a Git LFS pointer (not smudged content).

    CI checkouts without ``lfs: true`` leave ~100–200 byte pointers on disk.
    Treat those as *absent* for empty-hero floors so force-tracked screenshots
    under gitignored ``.dazzle/`` do not red the demo fleet bar.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < 80 or size > 300:
        return False
    try:
        head = path.read_bytes()[:80]
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def is_usable_still(path: Path) -> bool:
    """File exists and is real image bytes (not an LFS pointer stub)."""
    return path.is_file() and not is_lfs_pointer(path)


def score_stills(app_dir: Path, app_name: str) -> list[StillScore]:
    """Score known hero stills when present."""
    shots = _shot_dir(app_dir)
    floors = HERO_MIN_BYTES.get(app_name) or {}
    out: list[StillScore] = []
    if shots is None:
        return out

    # platform-only check (ignore LFS pointer stubs — same as absent)
    pngs = [p for p in shots.glob("*.png") if is_usable_still(p)]
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
        if not is_usable_still(path):
            continue  # absent / LFS pointer skipped (CI)
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
