#!/usr/bin/env python3
"""Story ↔ scene-walk residual probe (agent-first QA heat).

A story is not done when it is bound in DSL. For showcase apps we require
deterministic scene walks covering **landing** stories (accepted, job-shaped
user_click / desk paths) so /improve can dig when structural residual is
already 0 but agents never interact with the built app.

Usage::

    python scripts/story_walk_bar.py
    python scripts/story_walk_bar.py --status
    python scripts/story_walk_bar.py --next
    python scripts/story_walk_bar.py --app support_tickets --json
    python scripts/story_walk_bar.py --strict
    python scripts/story_walk_bar.py --write-stubs   # draft missing walk YAML

Exit 1 under --strict (or default fleet mode) when residual remains.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

# Same showcase ladder as demo_fleet_bar / #1626
SHOWCASE = (
    "simple_task",
    "support_tickets",
    "invoice_ops",
    "contact_manager",
    "ops_dashboard",
    "project_tracker",
    "design_studio",
    "hr_records",
    "fieldtest_hub",
)

# At least this many landing stories should have a walk (or all if fewer).
MIN_COVERED_LANDINGS = 2

_WS_IN_GIVEN = re.compile(
    r"\bon the\s+[`']?([a-z][a-z0-9_]*)[`']?\s+workspace\b",
    re.IGNORECASE,
)


@dataclass
class LandingStory:
    story_id: str
    persona: str
    title: str
    executed_by: str | None
    home_workspace: str | None
    then_cues: list[str] = field(default_factory=list)


@dataclass
class AppStoryWalkBar:
    app: str
    landing_stories: int = 0
    covered: int = 0
    walk_count: int = 0
    missing_ids: list[str] = field(default_factory=list)
    covered_ids: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    tier: str = "ok"  # critical | thin | deepen | ok
    score: int = 0  # higher = more residual priority

    @property
    def ok(self) -> bool:
        return self.tier == "ok" and not self.issues

    @property
    def is_residual(self) -> bool:
        return self.tier in {"critical", "thin", "deepen"} or bool(self.issues)


def _persona_default_ws(appspec: object, persona_id: str) -> str | None:
    personas = getattr(appspec, "personas", None) or []
    for p in personas:
        pid = getattr(p, "id", None) or getattr(p, "name", None)
        if str(pid) == persona_id:
            return getattr(p, "default_workspace", None) or getattr(p, "home_workspace", None)
    return None


def _workspace_from_given(story: object) -> str | None:
    for cond in getattr(story, "given", None) or []:
        expr = getattr(cond, "expression", None) or str(cond)
        m = _WS_IN_GIVEN.search(expr)
        if m:
            return m.group(1)
    return None


def _is_landing_story(story: object) -> bool:
    """Job-landing stories agents should walk (not every form_submitted CRUD)."""
    from dazzle.core.ir.stories import StoryStatus, StoryTrigger

    status = getattr(story, "status", None)
    if status is not None and str(status) != StoryStatus.ACCEPTED and status != "accepted":
        return False
    if getattr(story, "narrative_only", False):
        return False
    persona = getattr(story, "persona", None)
    if not persona:
        return False
    trigger = getattr(story, "trigger", None)
    trig = str(trigger) if trigger is not None else ""
    executed = getattr(story, "executed_by", None) or ""
    if trig in (StoryTrigger.USER_CLICK, "user_click", StoryTrigger.USER_CLICK.value):
        return True
    # Desk/list/queue surfaces often bind form paths but are still landings
    exec_l = str(executed).lower()
    if executed and any(k in exec_l for k in ("_list", "queue", "desk", "dashboard", "board")):
        return True
    return False


def _then_cues(story: object, *, limit: int = 4) -> list[str]:
    cues: list[str] = []
    title = getattr(story, "title", None) or ""
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", title):
        if token.lower() not in {"the", "and", "for", "with", "from", "their"}:
            cues.append(token)
        if len(cues) >= limit:
            break
    for cond in getattr(story, "then", None) or []:
        expr = getattr(cond, "expression", None) or ""
        for token in re.findall(r"[A-Za-z][A-Za-z]{3,}", expr):
            if token[0].isupper() and token not in cues:
                cues.append(token)
            if len(cues) >= limit:
                return cues
    return cues or ["Home"]


def collect_landing_stories(app_dir: Path) -> list[LandingStory]:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.ir.stories import StoryStatus

    try:
        appspec = load_project_appspec(app_dir)
    except Exception:
        return []
    out: list[LandingStory] = []
    for story in getattr(appspec, "stories", None) or []:
        if not _is_landing_story(story):
            continue
        status = getattr(story, "status", None)
        if status is not None and status != StoryStatus.ACCEPTED and str(status) != "accepted":
            continue
        sid = getattr(story, "story_id", None) or getattr(story, "id", None)
        if not sid:
            continue
        persona = str(getattr(story, "persona", "") or "")
        ws = _workspace_from_given(story) or _persona_default_ws(appspec, persona)
        out.append(
            LandingStory(
                story_id=str(sid),
                persona=persona,
                title=str(getattr(story, "title", "") or sid),
                executed_by=getattr(story, "executed_by", None),
                home_workspace=ws,
                then_cues=_then_cues(story),
            )
        )
    return out


def _walk_story_coverage(app_dir: Path) -> tuple[set[str], int, list[str]]:
    """Return (story_ids covered by walks, walk_count, load issues)."""
    from dazzle.testing.walk.discovery import discover_walk_paths
    from dazzle.testing.walk.loader import WalkLoadError, load_walk

    covered: set[str] = set()
    issues: list[str] = []
    paths = discover_walk_paths(app_dir)
    for path in paths:
        try:
            walk = load_walk(path)
        except WalkLoadError as exc:
            issues.append(f"walk_load_failed:{path.stem}:{exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            issues.append(f"walk_load_failed:{path.stem}:{type(exc).__name__}")
            continue
        for sid in walk.story_ids():
            covered.add(sid)
    return covered, len(paths), issues


def score_app(app: str, *, app_dir: Path | None = None) -> AppStoryWalkBar:
    row = AppStoryWalkBar(app=app)
    root = app_dir or (EXAMPLES / app)
    if not root.is_dir():
        row.tier = "critical"
        row.score = 200
        row.issues.append("missing_app")
        return row

    landings = collect_landing_stories(root)
    row.landing_stories = len(landings)
    covered_set, walk_count, load_issues = _walk_story_coverage(root)
    row.walk_count = walk_count
    row.issues.extend(load_issues)

    landing_ids = [L.story_id for L in landings]
    row.covered_ids = [s for s in landing_ids if s in covered_set]
    row.missing_ids = [s for s in landing_ids if s not in covered_set]
    row.covered = len(row.covered_ids)

    score = 0
    reasons: list[str] = []

    if row.landing_stories == 0:
        # No landing stories → no story-walk residual (journey probe owns "no stories")
        row.tier = "ok"
        row.score = 0
        return row

    need = min(MIN_COVERED_LANDINGS, row.landing_stories)
    if row.walk_count == 0:
        score += 100
        reasons.append("no_walks")
        row.issues.append("no_walks")
    if row.covered < need:
        score += 50 + 10 * (need - row.covered)
        reasons.append(f"covered_lt_{need}({row.covered}/{row.landing_stories})")
        for sid in row.missing_ids[:5]:
            row.issues.append(f"missing_walk:{sid}")
    elif row.covered < row.landing_stories and row.landing_stories >= 3:
        # Partial coverage of a large landing set — deepen, not critical
        score += 15
        reasons.append(f"partial_cover({row.covered}/{row.landing_stories})")
        for sid in row.missing_ids[:3]:
            row.issues.append(f"missing_walk:{sid}")

    # Persona coverage: each persona with a landing should appear in some walk
    personas_needed = {L.persona for L in landings if L.persona}
    personas_with_walk: set[str] = set()
    if walk_count:
        from dazzle.testing.walk.discovery import discover_walk_paths
        from dazzle.testing.walk.loader import load_walk

        for path in discover_walk_paths(root):
            try:
                w = load_walk(path)
            except Exception:  # noqa: BLE001
                continue
            personas_with_walk.add(w.persona)
    missing_personas = sorted(personas_needed - personas_with_walk)
    if missing_personas and row.walk_count > 0:
        score += 20
        reasons.append(f"persona_no_walk:{','.join(missing_personas[:4])}")
        for p in missing_personas[:3]:
            row.issues.append(f"persona_no_walk:{p}")

    row.score = score
    if score >= 80 or "no_walks" in reasons:
        row.tier = "critical"
    elif score >= 40:
        row.tier = "thin"
    elif score > 0:
        row.tier = "deepen"
    else:
        row.tier = "ok"
        # clear missing_walk issues if we met min cover and no other issues
        if row.covered >= need and not load_issues and not missing_personas:
            row.issues = [i for i in row.issues if not i.startswith("missing_walk:")]
    return row


def scan(apps: tuple[str, ...] | None = None) -> list[AppStoryWalkBar]:
    names = apps or SHOWCASE
    rows = [score_app(a) for a in names if (EXAMPLES / a).is_dir()]
    rows.sort(key=lambda r: (-r.score, r.app))
    return rows


def format_status(rows: list[AppStoryWalkBar]) -> str:
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else "-"
    crit = sum(1 for r in residual if r.tier == "critical")
    thin = sum(1 for r in residual if r.tier == "thin")
    deepen = sum(1 for r in residual if r.tier == "deepen")
    return (
        f"story_walk apps={len(rows)} residual={len(residual)} "
        f"critical={crit} thin={thin} deepen={deepen} next={nxt}"
    )


def format_table(rows: list[AppStoryWalkBar]) -> str:
    lines = [
        f"{'app':<22} {'tier':<10} land cov walks missing",
        "-" * 72,
    ]
    for r in rows:
        miss = ",".join(r.missing_ids[:3]) if r.missing_ids else "-"
        if len(r.missing_ids) > 3:
            miss += f"+{len(r.missing_ids) - 3}"
        lines.append(
            f"{r.app:<22} {r.tier:<10} {r.landing_stories:>4} {r.covered:>3} "
            f"{r.walk_count:>5} {miss}"
        )
    residual = [r for r in rows if r.is_residual]
    lines.append("")
    lines.append(format_status(rows))
    if residual:
        lines.append(f"next_dig={residual[0].app} issues={residual[0].issues[:4]}")
    return "\n".join(lines)


def stub_walk_yaml(landing: LandingStory) -> str:
    """Draft core-only scene walk for a landing story."""
    ws = landing.home_workspace or "home"
    entry = f"/app/workspaces/{ws}"
    cues = landing.then_cues[:4] or [landing.story_id]
    texts = "\n".join(f"          - {c}" for c in cues)
    return (
        f"# Auto-stub story walk — promote after dry-run + live green\n"
        f"# Story: {landing.story_id} {landing.title}\n"
        f"\n"
        f"persona: {landing.persona}\n"
        f"home_workspace: {ws}\n"
        f"\n"
        f"scenes:\n"
        f"  - id: land_{landing.story_id.lower().replace('-', '_')}\n"
        f"    story: {landing.story_id}\n"
        f"    entry: {entry}\n"
        f"    actions:\n"
        f"      - type: navigate\n"
        f"      - type: assert_not_login\n"
        f"      - type: assert_http_ok\n"
        f"      - type: assert_any_text\n"
        f"        texts:\n"
        f"{texts}\n"
        f'    expects: "{landing.title[:80]}"\n'
    )


def write_stubs(app: str, *, force: bool = False) -> list[Path]:
    """Write missing walk YAML stubs for uncovered landing stories (one per missing)."""
    root = EXAMPLES / app
    landings = collect_landing_stories(root)
    covered, _, _ = _walk_story_coverage(root)
    out_dir = root / "fixtures" / "scene_walks"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for L in landings:
        if L.story_id in covered and not force:
            continue
        slug = L.story_id.lower().replace("-", "_")
        path = out_dir / f"{L.persona}_{slug}.yaml"
        if path.exists() and not force:
            continue
        path.write_text(stub_walk_yaml(L), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--app", help="Single showcase app")
    ap.add_argument(
        "--write-stubs",
        action="store_true",
        help="Write draft scene_walk YAML for uncovered landing stories",
    )
    ap.add_argument("--force-stubs", action="store_true", help="Overwrite existing stubs")
    args = ap.parse_args(argv)

    if args.app:
        rows = [score_app(args.app)]
    else:
        rows = scan()

    if args.write_stubs:
        targets = [args.app] if args.app else [r.app for r in rows if r.is_residual]
        written: list[str] = []
        for name in targets:
            for p in write_stubs(name, force=args.force_stubs):
                written.append(str(p.relative_to(REPO)))
        print(
            json.dumps({"written": written}, indent=2)
            if args.json
            else "\n".join(written) or "(none)"
        )
        rows = [score_app(a) for a in targets] if targets else rows

    residual = [r for r in rows if r.is_residual]
    if args.next:
        print(residual[0].app if residual else "")
        return 0 if not residual else 1

    if args.status:
        print(format_status(rows))
    elif args.json:
        print(
            json.dumps(
                {
                    "status": format_status(rows),
                    "apps": [asdict(r) for r in rows],
                    "next": residual[0].app if residual else None,
                    "residual": len(residual),
                },
                indent=2,
            )
        )
    else:
        print(format_table(rows))

    if args.strict or (not args.status and not args.app and residual):
        # default fleet table: exit 1 when residual (like journey maturity)
        if residual:
            return 1
    if args.strict and residual:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
