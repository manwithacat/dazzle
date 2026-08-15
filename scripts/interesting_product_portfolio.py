#!/usr/bin/env python3
"""Goal B portfolio planner — depth×app coverage, anti-wave, anti-recipe, stacking.

When residual=0, agents must not fleet-fill the same depth_id with the same
surface recipe. This module is the machine surface for that doctrine
(docs/reference/interesting-saas-context.md §6 + portfolio pick).

Usage::

    python scripts/interesting_product_portfolio.py --status
    python scripts/interesting_product_portfolio.py --recommend
    python scripts/interesting_product_portfolio.py --json

Sources (no human score required):

* Unit pins ``tests/unit/test_*_*_goal_b.py`` → covered (app, depth) cells
* Dig receipts under ``.dazzle/improve-digs/*interesting_product*.json`` →
  recent tipward depth/app/recipe sequence
* Optional git log (best-effort) for the same sequence when digs are sparse
* Peer packs under ``improve/peer_packs/*.toml`` → icon apps + peer constraints

Does **not** invent residual heat or interestingness scores. Selection pressure
only: diversify depth waves, ban clone recipes, prefer icon-app stacking.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DIGS = REPO / ".dazzle" / "improve-digs"
UNIT = REPO / "tests" / "unit"
EXAMPLES = REPO / "examples"
PEER_PACKS = REPO / "improve" / "peer_packs"

DEPTH_IDS: tuple[str, ...] = (
    "conversation",
    "document",
    "media",
    "command_density",
    "org_structure",
    "empty_region_honesty",
)

# Unit pin filename aliases → showcase dir name.
_APP_ALIASES: dict[str, str] = {
    "llm_classifier": "llm_ticket_classifier",
    "domain_join": "domain_join_co",
    "fieldtest": "fieldtest_hub",
    "acme": "acme_billing",
}

# Soft recipe tags derived from dig notes / commit subjects (closed set).
_RECIPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Specific empty_region families first — greedy honesty/empty_region
    # must not collapse identity chips or work-first reorder into prune.
    ("directory_work_first", re.compile(r"directory_work_first", re.I)),
    ("identity_chip_not_schema", re.compile(r"identity_chip_not_schema", re.I)),
    ("billing_escalations_seat", re.compile(r"billing_escalations_seat", re.I)),
    ("approved_stamp_wall", re.compile(r"approved_stamp_wall", re.I)),
    ("tree_people_seat", re.compile(r"tree_people_seat", re.I)),
    ("device_identity_wall", re.compile(r"device_identity_wall", re.I)),
    ("severity_evidence_density", re.compile(r"severity_evidence_density", re.I)),
    ("two_desk_media_saturate", re.compile(r"two_desk_media_saturate", re.I)),
    ("headshot_shelf", re.compile(r"headshot|photo_url|media_shelf", re.I)),
    ("dual_attention", re.compile(r"dual attention|command_density|multi-panel|multi panel", re.I)),
    ("team_org_desk", re.compile(r"\bTeam desk\b|org_structure|People desk|reporting", re.I)),
    (
        "composition_lines",
        re.compile(r"composition|line.?item|document packet|InvoiceDocument", re.I),
    ),
    (
        "message_chrome",
        re.compile(r"Message chrome|display:conversation|live_conversation|Message/Bubble", re.I),
    ),
    ("empty_region_prune", re.compile(r"empty_region|prune .*theater|honesty", re.I)),
)

# Coat families — synonym tags collapse here so "novel recipe" cannot evade
# anti-recipe. One family ship on (app, depth) saturates that cell.
_FAMILY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "conversation_filter_slice",
        re.compile(
            r"needs_reply|awaiting_customer|_channel_trail|_tone_trail|"
            r"escalation_trail|hot_speech|thankful_recovery|tone_escalation",
            re.I,
        ),
    ),
    (
        "document_rail_slice",
        re.compile(r"_rail_evidence|_watch\b|rail_evidence", re.I),
    ),
    (
        "stage_queue_slice",
        re.compile(r"stage_density|_stage_queue", re.I),
    ),
)
COAT_FAMILIES: frozenset[str] = frozenset(name for name, _ in _FAMILY_PATTERNS)

# Prefer stacking depth on these icon apps before thin fleet coat.
ICON_APPS: dict[str, tuple[str, ...]] = {
    "conversation": ("support_tickets", "simple_task", "fieldtest_hub"),
    "document": ("invoice_ops", "acme_billing", "fieldtest_hub"),
    "media": ("design_studio", "fieldtest_hub"),
    "command_density": ("ops_dashboard", "support_tickets", "invoice_ops"),
    "org_structure": ("hr_records", "domain_join_co", "support_tickets"),
    "empty_region_honesty": ("support_tickets", "project_tracker", "hr_records"),
}

DEFAULT_MAX_SAME_DEPTH = 3
DEFAULT_MAX_SAME_RECIPE = 3
DEFAULT_STACK_TARGET = 3  # prefer apps with 1..(target-1) depths already


@dataclass
class GoalBShip:
    app: str
    depth_id: str
    recipe: str | None = None
    family: str | None = None
    source: str = ""
    cycle: int | None = None


@dataclass
class PortfolioSnapshot:
    apps: list[str]
    depths: list[str]
    covered: list[list[str]]  # [app, depth]
    missing: list[list[str]]
    coverage_by_app: dict[str, int]
    coverage_by_depth: dict[str, int]
    recent_ships: list[dict[str, Any]]
    depth_streak: int
    depth_streak_id: str | None
    recipe_streak: int
    recipe_streak_id: str | None
    banned_depths: list[str]
    banned_recipes: list[str]
    saturated_cells: list[list[str]] = field(default_factory=list)
    recommend: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


def showcase_apps() -> list[str]:
    if not EXAMPLES.is_dir():
        return []
    return sorted(
        p.name
        for p in EXAMPLES.iterdir()
        if p.is_dir() and (p / "dazzle.toml").is_file() and not p.name.startswith(".")
    )


def _normalize_app(raw: str) -> str:
    raw = raw.strip().replace("-", "_")
    return _APP_ALIASES.get(raw, raw)


def _normalize_depth(raw: str) -> str | None:
    s = raw.strip().lower().replace("-", "_")
    if s in DEPTH_IDS:
        return s
    if s == "empty_region":
        return "empty_region_honesty"
    return None


def _recipe_from_text(text: str) -> str | None:
    for name, pat in _RECIPE_PATTERNS:
        if pat.search(text or ""):
            return name
    return None


def _family_from_blob(blob: str) -> str | None:
    if not blob:
        return None
    for name, pat in _FAMILY_PATTERNS:
        if pat.search(blob):
            return name
    return _recipe_from_text(blob)


def recipe_family(recipe: str | None, text: str = "") -> str | None:
    """Collapse a free recipe tag (or notes) onto a closed family.

    Coat synonyms (thankful_needs_reply_trail, receipt_settle_rail_evidence)
    must not count as novel. Honest first grains (message_chrome, dual_attention)
    stay on the original six families.

    Structured ``recipe`` wins over notes. Dig notes often mention a riding
    ship (``2094 approved_stamp_wall rides this push``) and must not collapse
    ``tree_people_seat`` onto that prior family.

    AUD-015: a *non-empty unknown* recipe stays ``None`` — do not scan notes
    (``two_desk_media_saturate`` + ``photo_url`` used to become headshot_shelf).
    """
    rec = (recipe or "").strip()
    if rec:
        tagged = _family_from_blob(rec)
        if tagged:
            return tagged
        return None
    return _family_from_blob((text or "").strip())


def covered_from_unit_pins(*, unit_dir: Path = UNIT) -> set[tuple[str, str]]:
    """Parse tests/unit/test_<app>_<depth>_goal_b.py → (app, depth)."""
    out: set[tuple[str, str]] = set()
    if not unit_dir.is_dir():
        return out
    # Prefer longest depth match so empty_region_honesty wins over empty.
    depth_sorted = sorted(DEPTH_IDS, key=len, reverse=True)
    for path in unit_dir.glob("test_*_goal_b.py"):
        stem = path.stem  # test_foo_bar_goal_b
        body = stem.removeprefix("test_").removesuffix("_goal_b")
        # Special multi-word depth / campaign pins
        if body.endswith("_campaign_media") or body.endswith("_media_home"):
            app_raw = body.rsplit("_media", 1)[0].replace("_campaign", "")
            app = _normalize_app(app_raw)
            out.add((app, "media"))
            continue
        if body == "media_thumb":
            # Framework pin — not an app cell.
            continue
        matched = False
        for depth in depth_sorted:
            suffix = f"_{depth}"
            if body.endswith(suffix):
                app = _normalize_app(body[: -len(suffix)])
                out.add((app, depth))
                matched = True
                break
        if matched:
            continue
        # empty_region without _honesty
        if body.endswith("_empty_region"):
            app = _normalize_app(body[: -len("_empty_region")])
            out.add((app, "empty_region_honesty"))
    return out


def ships_from_dig_receipts(*, digs_dir: Path = DIGS, limit: int = 40) -> list[GoalBShip]:
    if not digs_dir.is_dir():
        return []
    paths = sorted(digs_dir.glob("*interesting_product*.json"), reverse=True)[:limit]
    ships: list[GoalBShip] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        app = _normalize_app(str(data.get("app") or ""))
        notes = str(data.get("notes") or "")
        # Prefer structured fields (cycle 2047+ dig contract); fall back to notes prose.
        depth = _normalize_depth(str(data.get("depth_id") or "")) or None
        if not depth:
            m = re.search(r"depth_id\s*=\s*([a-z_]+)", notes, re.I)
            if m:
                depth = _normalize_depth(m.group(1))
        if not depth:
            for d in DEPTH_IDS:
                if d in notes.lower() or d.replace("_", " ") in notes.lower():
                    depth = d
                    break
        if not app or not depth:
            continue
        cycle = data.get("cycle")
        try:
            cycle_i = int(cycle) if cycle is not None else None
        except (TypeError, ValueError):
            cycle_i = None
        # Raw tag kept for logs; family collapse is what anti-recipe / saturate use.
        recipe_raw = str(data.get("recipe") or "").strip() or None
        recipe = recipe_raw or _recipe_from_text(notes)
        family = recipe_family(recipe_raw, notes) or recipe_family(recipe)
        ships.append(
            GoalBShip(
                app=app,
                depth_id=depth,
                recipe=recipe,
                family=family,
                source=path.name,
                cycle=cycle_i,
            )
        )
    # dig paths are reverse chrono by name (timestamp prefix); keep that order
    return ships


def ships_from_git(*, limit: int = 40) -> list[GoalBShip]:
    """Best-effort tip history: ``Goal B <depth>`` in subject."""
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(REPO),
                "log",
                f"-{limit}",
                "--format=%s",
                "--grep=Goal B",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    ships: list[GoalBShip] = []
    apps = showcase_apps()
    for line in proc.stdout.splitlines():
        depth = None
        for d in sorted(DEPTH_IDS, key=len, reverse=True):
            if d in line or d.replace("_", " ") in line.lower():
                depth = d
                break
            if d == "empty_region_honesty" and "empty_region" in line:
                depth = d
                break
        if not depth:
            continue
        app = None
        lower = line.lower()
        for a in sorted(apps, key=len, reverse=True):
            if a in lower or a.replace("_", " ") in lower:
                app = a
                break
        # short forms in subjects: acme, domain_join, fieldtest, llm
        if not app:
            for alias, canon in _APP_ALIASES.items():
                if alias in lower:
                    app = canon
                    break
        if not app:
            continue
        raw = _recipe_from_text(line)
        ships.append(
            GoalBShip(
                app=app,
                depth_id=depth,
                recipe=raw,
                family=recipe_family(raw, line),
                source="git",
            )
        )
    return ships


def load_peer_pack(app: str) -> dict[str, Any] | None:
    path = PEER_PACKS / f"{app}.toml"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    try:
        return tomllib.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _streak(values: list[str | None]) -> tuple[int, str | None]:
    if not values or not values[0]:
        return 0, None
    head = values[0]
    n = 0
    for v in values:
        if v == head:
            n += 1
        else:
            break
    return n, head


def cells_saturated_by_ships(recent: list[GoalBShip]) -> set[tuple[str, str]]:
    """One coat-family ship on (app, depth) saturates that cell."""
    sat: set[tuple[str, str]] = set()
    for ship in recent:
        fam = ship.family or recipe_family(ship.recipe)
        if fam in COAT_FAMILIES and ship.app and ship.depth_id:
            sat.add((ship.app, ship.depth_id))
    return sat


def recommend_pick(
    *,
    covered: set[tuple[str, str]],
    apps: list[str],
    recent: list[GoalBShip],
    max_same_depth: int = DEFAULT_MAX_SAME_DEPTH,
    max_same_recipe: int = DEFAULT_MAX_SAME_RECIPE,
    stack_target: int = DEFAULT_STACK_TARGET,
    saturated: set[tuple[str, str]] | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[str], list[str]]:
    """Return (recommend_dict|None, banned_depths, banned_recipes, notes)."""
    notes: list[str] = []
    depth_values = [s.depth_id for s in recent]
    recipe_values = [s.family or s.recipe for s in recent]
    depth_streak, depth_id = _streak(depth_values)
    recipe_streak, recipe_id = _streak(recipe_values)

    banned_depths: list[str] = []
    banned_recipes: list[str] = []
    if depth_streak >= max_same_depth and depth_id:
        banned_depths.append(depth_id)
        notes.append(f"ban depth_id={depth_id} (streak {depth_streak}>={max_same_depth})")
    if recipe_streak >= max_same_recipe and recipe_id:
        banned_recipes.append(recipe_id)
        notes.append(f"ban recipe={recipe_id} (streak {recipe_streak}>={max_same_recipe})")

    sat = set(saturated or ()) | cells_saturated_by_ships(recent)
    if sat:
        notes.append(
            "saturated="
            + ",".join(f"{a}/{d}" for a, d in sorted(sat)[:12])
            + ("…" if len(sat) > 12 else "")
        )

    by_app: dict[str, int] = Counter(a for a, _ in covered if a in apps)
    missing: list[tuple[str, str]] = []
    for app in apps:
        for depth in DEPTH_IDS:
            if (app, depth) not in covered:
                missing.append((app, depth))

    natural_recipe = {
        "media": "headshot_shelf",
        "command_density": "dual_attention",
        "org_structure": "team_org_desk",
        "document": "composition_lines",
        "conversation": "message_chrome",
        "empty_region_honesty": "empty_region_prune",
    }

    # Only banned-depth cells left (or matrix full) → allow depth with novel recipe,
    # or recommend a peer-pack upgrade / framework primitive.
    only_banned_left = bool(missing) and all(d in banned_depths for _, d in missing)
    matrix_full = not missing

    # Pair thrash: tipward (app, depth) counts — breaks conversation↔document
    # alternation that never hits max_same_depth but re-paints the same cell.
    pair_counts: Counter[tuple[str, str]] = Counter(
        (s.app, s.depth_id) for s in recent[:12] if s.app and s.depth_id
    )

    def score(app: str, depth: str, *, allow_banned_depth: bool) -> tuple[int, str]:
        """Higher is better. Reasons for logging."""
        why: list[str] = []
        s = 0
        if (app, depth) in sat:
            return (-10_000, "saturated_cell")
        if depth in banned_depths and not allow_banned_depth:
            return (-10_000, "banned_depth")
        if depth in banned_depths and allow_banned_depth:
            s -= 20
            why.append("different_family_or_stop")
        natural = natural_recipe.get(depth)
        if natural and natural in banned_recipes:
            s -= 40
            why.append(f"recipe_pressure:{natural}")
        icons = ICON_APPS.get(depth) or ()
        if app in icons:
            s += 30
            why.append("icon_app")
            s += max(0, 10 - icons.index(app) * 3)
        n = by_app.get(app, 0)
        if 1 <= n < stack_target:
            s += 40 + (stack_target - n) * 5
            why.append(f"stack n={n}")
        elif n == 0:
            s += 5
            why.append("greenfield")
        else:
            # Prefer incomplete apps when filling last cells
            s += max(0, (len(DEPTH_IDS) - n) * 8)
            why.append(f"fill n={n}")
        depth_count = sum(1 for _, d in covered if d == depth)
        s += max(0, 12 - depth_count)
        why.append(f"depth_fleet={depth_count}")
        if recent and recent[0].app == app:
            s -= 15
            why.append("not_last_app")
        if recent and recent[0].depth_id == depth and not allow_banned_depth:
            s -= 25
            why.append("not_last_depth")
        # Matrix-full upgrades: penalize cells already dominating tip history so
        # icon_app+peer_pack cannot lock invoice_ops/document forever (cycle 2047).
        pair_n = pair_counts.get((app, depth), 0)
        if pair_n:
            s -= 40 * pair_n
            why.append(f"pair_thrash n={pair_n}")
        if load_peer_pack(app):
            s += 8
            why.append("peer_pack")
        return s, "+".join(why) if why else "default"

    candidates = missing
    allow_banned = False
    if matrix_full:
        notes.append(
            "coverage matrix full — upgrade only unsaturated cells; "
            "else stop / framework-ux (not another coat synonym)"
        )
        candidates = []
        for depth, icons in ICON_APPS.items():
            for app in icons:
                if app in apps and (app, depth) not in sat:
                    candidates.append((app, depth))
        allow_banned = True
        if not candidates:
            notes.append("all icon cells saturated — stop (no Goal B coat this cycle)")
            return None, banned_depths, banned_recipes, notes
    elif only_banned_left:
        notes.append(
            "only banned-depth cells remain — fill with a different family or stop "
            "(do not invent a synonym recipe tag)"
        )
        allow_banned = True
        candidates = [(a, d) for a, d in candidates if (a, d) not in sat]
        if not candidates:
            notes.append("banned-depth remainder is saturated — stop")
            return None, banned_depths, banned_recipes, notes
    else:
        candidates = [(a, d) for a, d in candidates if (a, d) not in sat]

    best: tuple[int, str, str, str] | None = None
    for app, depth in candidates:
        sc, why = score(app, depth, allow_banned_depth=allow_banned)
        if best is None or sc > best[0]:
            best = (sc, app, depth, why)

    if best is None or best[0] < -1000:
        notes.append("no viable portfolio cell — stop / framework-ux / scenario_underused")
        return None, banned_depths, banned_recipes, notes

    _sc, app, depth, why = best
    pack = load_peer_pack(app) or {}
    must_novel = bool(
        depth in banned_depths or natural_recipe.get(depth) in banned_recipes or matrix_full
    )
    mode = (
        "upgrade" if matrix_full else ("fill_novel" if must_novel and only_banned_left else "fill")
    )
    rec = {
        "app": app,
        "depth_id": depth,
        "score": _sc,
        "reason": why,
        "mode": mode,
        "must_novel_recipe": must_novel,
        "banned_recipe_for_depth": natural_recipe.get(depth)
        if natural_recipe.get(depth) in banned_recipes
        else None,
        "peer": pack.get("peer"),
        "above_fold": pack.get("above_fold") or pack.get("constraints"),
        "icon_for_depth": app in (ICON_APPS.get(depth) or ()),
        "stack_count": by_app.get(app, 0),
        "stack_target": stack_target,
        "guidance": (
            "Honor portfolio pick unless dig finds red CI / residual heat. "
            "must_novel_recipe means a different closed family or stop — "
            "never a new synonym tag on the same coat."
        ),
    }
    return rec, banned_depths, banned_recipes, notes


def snapshot(
    *,
    max_same_depth: int = DEFAULT_MAX_SAME_DEPTH,
    max_same_recipe: int = DEFAULT_MAX_SAME_RECIPE,
    stack_target: int = DEFAULT_STACK_TARGET,
    unit_dir: Path = UNIT,
    digs_dir: Path = DIGS,
) -> PortfolioSnapshot:
    apps = showcase_apps()
    covered = covered_from_unit_pins(unit_dir=unit_dir)
    # Keep only known showcase apps
    covered = {(a, d) for a, d in covered if a in apps}
    dig_ships = ships_from_dig_receipts(digs_dir=digs_dir)
    recent = dig_ships if dig_ships else ships_from_git()
    live_sat: set[tuple[str, str]] = set()
    try:
        from scripts.goal_b_coat import live_saturated_cells
    except Exception:  # noqa: BLE001 — script path when run as __main__
        try:
            import goal_b_coat as _coat  # type: ignore

            live_saturated_cells = _coat.live_saturated_cells
        except Exception:  # noqa: BLE001
            live_saturated_cells = None  # type: ignore[assignment]
    if live_saturated_cells is not None:
        try:
            live_sat = live_saturated_cells(apps)
        except Exception:  # noqa: BLE001
            live_sat = set()
    rec, banned_d, banned_r, notes = recommend_pick(
        covered=covered,
        apps=apps,
        recent=recent,
        max_same_depth=max_same_depth,
        max_same_recipe=max_same_recipe,
        stack_target=stack_target,
        saturated=live_sat,
    )
    depth_streak, depth_id = _streak([s.depth_id for s in recent])
    recipe_streak, recipe_id = _streak([s.family or s.recipe for s in recent])
    missing = [[a, d] for a in apps for d in DEPTH_IDS if (a, d) not in covered]
    by_app: dict[str, int] = defaultdict(int)
    by_depth: dict[str, int] = defaultdict(int)
    for a, d in covered:
        by_app[a] += 1
        by_depth[d] += 1
    return PortfolioSnapshot(
        apps=apps,
        depths=list(DEPTH_IDS),
        covered=sorted([list(x) for x in covered]),
        missing=missing,
        coverage_by_app=dict(sorted(by_app.items())),
        coverage_by_depth=dict(sorted(by_depth.items())),
        recent_ships=[asdict(s) for s in recent[:12]],
        depth_streak=depth_streak,
        depth_streak_id=depth_id,
        recipe_streak=recipe_streak,
        recipe_streak_id=recipe_id,
        banned_depths=banned_d,
        banned_recipes=banned_r,
        saturated_cells=sorted([list(x) for x in (live_sat | cells_saturated_by_ships(recent))]),
        recommend=rec,
        notes=notes,
    )


def format_status(snap: PortfolioSnapshot | None = None) -> str:
    snap = snap or snapshot()
    lines = [
        "interesting_product_portfolio",
        f"covered_cells={len(snap.covered)} missing_cells={len(snap.missing)} "
        f"apps={len(snap.apps)} depths={len(snap.depths)}",
        f"depth_streak={snap.depth_streak}"
        + (f" id={snap.depth_streak_id}" if snap.depth_streak_id else ""),
        f"recipe_streak={snap.recipe_streak}"
        + (f" id={snap.recipe_streak_id}" if snap.recipe_streak_id else ""),
    ]
    if snap.banned_depths:
        lines.append(f"banned_depths={','.join(snap.banned_depths)}")
    if snap.banned_recipes:
        lines.append(f"banned_recipes={','.join(snap.banned_recipes)}")
    if snap.saturated_cells:
        sat_bits = ",".join(f"{a}/{d}" for a, d in snap.saturated_cells[:12])
        extra = "…" if len(snap.saturated_cells) > 12 else ""
        lines.append(f"saturated={sat_bits}{extra}")
    if snap.coverage_by_depth:
        depth_bits = " ".join(f"{k}={v}" for k, v in snap.coverage_by_depth.items())
        lines.append(f"by_depth {depth_bits}")
    if snap.recommend:
        r = snap.recommend
        lines.append(
            f"recommend app={r.get('app')} depth_id={r.get('depth_id')} "
            f"score={r.get('score')} reason={r.get('reason')}"
        )
        if r.get("peer"):
            lines.append(f"peer={r.get('peer')}")
        if r.get("icon_for_depth"):
            lines.append("icon_app=1")
        lines.append(f"stack={r.get('stack_count')}/{r.get('stack_target')}")
    else:
        lines.append("recommend=-")
    for n in snap.notes:
        lines.append(f"note: {n}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true")
    p.add_argument("--recommend", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-same-depth", type=int, default=DEFAULT_MAX_SAME_DEPTH)
    p.add_argument("--max-same-recipe", type=int, default=DEFAULT_MAX_SAME_RECIPE)
    p.add_argument("--stack-target", type=int, default=DEFAULT_STACK_TARGET)
    args = p.parse_args(argv)

    snap = snapshot(
        max_same_depth=args.max_same_depth,
        max_same_recipe=args.max_same_recipe,
        stack_target=args.stack_target,
    )
    if args.json:
        print(json.dumps(asdict(snap), indent=2, default=str))
        return 0
    if args.recommend:
        if snap.recommend:
            print(
                f"{snap.recommend['app']} {snap.recommend['depth_id']} "
                f"# {snap.recommend.get('reason')}"
            )
        else:
            print("-")
            return 1
        return 0
    # default --status
    print(format_status(snap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
