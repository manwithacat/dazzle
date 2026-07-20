"""Pack dry-run and claim residuals for agent seed (#1638 PR4).

A *pack* is a letter (A/B/C) grouping human/dogfood job claims. Pack dry-run
filters the job claim registry to that pack, dry-runs each bound walk, and
returns residuals (failed claim checks or walk dry-run preflight errors).

Residuals convert to ``dazzle agent seed improve`` PENDING gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.testing.walk.claims import (
    ClaimGuide,
    ClaimIssue,
    ClaimsCheckResult,
    JobClaimRegistry,
    check_registry,
    discover_registry_path,
    load_registry,
)
from dazzle.testing.walk.discovery import discover_walk_paths
from dazzle.testing.walk.loader import load_walk
from dazzle.testing.walk.models import SceneWalkSpec, WalkActionType
from dazzle.testing.walk.results import WalkRunResult
from dazzle.testing.walk.runner import run_walk_sync
from dazzle.testing.walk.validate import validate_walk

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

_PLAYWRIGHT_TYPES = frozenset({WalkActionType.PLAYWRIGHT_CLICK, WalkActionType.PLAYWRIGHT_WAIT})


def walk_needs_playwright(walk: SceneWalkSpec) -> bool:
    """True when any scene uses playwright_* (R4.3 auto-enable)."""
    return any(a.type in _PLAYWRIGHT_TYPES for s in walk.scenes for a in s.actions)


def _pack_key(value: str | int | None) -> str | None:
    if value is None:
        return None
    return str(value).strip().upper()


def guides_for_pack(registry: JobClaimRegistry, pack: str) -> list[ClaimGuide]:
    """Guides whose ``pack`` matches *pack* (case-insensitive)."""
    want = _pack_key(pack)
    return [g for g in registry.guides if _pack_key(g.pack) == want]


@dataclass
class PackDryRunResult:
    """Outcome of ``pack dry-run`` for one pack letter."""

    pack: str
    registry_path: str
    guides: list[str] = field(default_factory=list)
    walk_ids: list[str] = field(default_factory=list)
    claim_issues: list[ClaimIssue] = field(default_factory=list)
    walk_results: list[WalkRunResult] = field(default_factory=list)
    residuals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.claim_issues) and all(
            r.ok for r in self.walk_results
        )


def pack_dry_run(
    project_root: Path,
    pack: str,
    *,
    appspec: AppSpec | None = None,
    registry: JobClaimRegistry | None = None,
    execute: bool = False,
    base_url: str | None = None,
    use_playwright: bool | None = None,
) -> PackDryRunResult:
    """Dry-run (or live-run) all walks for claims in *pack*.

    Args:
        execute: When True, run walks live (needs server). Default dry-run only.
        use_playwright: Force Playwright on/off. ``None`` = auto when walk
            contains ``playwright_*`` actions (CyFuture R4.3).
    """
    root = project_root.resolve()
    if registry is None:
        path = discover_registry_path(root)
        if path is None:
            raise FileNotFoundError("No job claim registry found (fixtures/job_claims.yaml, …)")
        registry = load_registry(path)

    guides = guides_for_pack(registry, pack)
    result = PackDryRunResult(
        pack=_pack_key(pack) or pack,
        registry_path=registry.source_path or "",
        guides=[g.id for g in guides],
        walk_ids=sorted({g.walk for g in guides if g.walk}),
    )

    # Claim check only for this pack's guides (filter full registry issues)
    full = check_registry(
        registry,
        project_root=root,
        appspec=appspec,
        run_walks=False,
    )
    guide_set = set(result.guides)
    result.claim_issues = [i for i in full.issues if i.guide_id in guide_set]

    for walk_id in result.walk_ids:
        result.walk_results.append(
            _run_pack_walk(
                walk_id,
                root=root,
                appspec=appspec,
                execute=execute,
                base_url=base_url,
                registry=registry,
                use_playwright=use_playwright,
            )
        )

    result.residuals = residuals_from_pack(result)
    return result


def _run_pack_walk(
    walk_id: str,
    *,
    root: Path,
    appspec: AppSpec | None,
    execute: bool,
    base_url: str | None,
    registry: JobClaimRegistry,
    use_playwright: bool | None = None,
) -> WalkRunResult:
    """Load + dry-run/execute one walk for a pack; always returns a WalkRunResult."""
    paths = [p for p in discover_walk_paths(root) if p.stem == walk_id]
    if not paths:
        return WalkRunResult(walk_id=walk_id, persona="?", ok=False, error="walk file missing")
    walk = load_walk(paths[0])
    v_err = [i for i in validate_walk(walk, appspec=appspec) if i.level == "error"]
    if v_err:
        return WalkRunResult(
            walk_id=walk_id,
            persona=walk.persona,
            ok=False,
            error="; ".join(i.message for i in v_err),
        )
    pw = walk_needs_playwright(walk) if use_playwright is None else use_playwright
    return run_walk_sync(
        walk,
        base_url=base_url or registry.base_url_default or "http://127.0.0.1:8000",
        project_root=root,
        dry_run=not execute,
        use_playwright=pw and execute,
    )


def residuals_from_pack(result: PackDryRunResult) -> list[dict[str, Any]]:
    """Convert pack dry-run failures into agent seed gap dicts."""
    gaps: list[dict[str, Any]] = []
    for issue in result.claim_issues:
        if issue.level != "error":
            continue
        gaps.append(
            {
                "kind": "walk_claim",
                "description": f"[{issue.guide_id}] {issue.message}",
                "status": "PENDING",
                "attempts": 0,
                "notes": f"claims check #{issue.code} pack={result.pack}",
            }
        )
    for wr in result.walk_results:
        if wr.ok:
            continue
        gaps.append(
            {
                "kind": "walk_claim",
                "description": (f"walk {wr.walk_id} failed: {wr.error or 'see actions'}"),
                "status": "PENDING",
                "attempts": 0,
                "notes": f"pack dry-run pack={result.pack}",
            }
        )
    return gaps


def claims_residuals(
    project_root: Path,
    *,
    appspec: AppSpec | None = None,
) -> list[dict[str, Any]]:
    """All claim-check errors as PENDING gaps (for ``agent seed improve``)."""
    root = project_root.resolve()
    path = discover_registry_path(root)
    if path is None:
        return []
    registry = load_registry(path)
    checked = check_registry(
        registry,
        project_root=root,
        appspec=appspec,
        run_walks=False,
    )
    gaps: list[dict[str, Any]] = []
    for issue in checked.errors:
        gaps.append(
            {
                "kind": "walk_claim",
                "description": f"[{issue.guide_id}] {issue.message}",
                "status": "PENDING",
                "attempts": 0,
                "notes": f"dazzle docs claims check #{issue.code}",
            }
        )
    return gaps


def claims_check_result_as_gaps(result: ClaimsCheckResult) -> list[dict[str, Any]]:
    """Map an existing ClaimsCheckResult to seed gaps."""
    return [
        {
            "kind": "walk_claim",
            "description": f"[{i.guide_id}] {i.message}",
            "status": "PENDING",
            "attempts": 0,
            "notes": f"claims check #{i.code}",
        }
        for i in result.errors
    ]
