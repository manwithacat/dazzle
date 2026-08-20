#!/usr/bin/env python3
"""Read/activate /improve prioritisation policy (steady_state vs campaign).

Usage::

    python scripts/improve_policy.py --status
    python scripts/improve_policy.py --pick          # recommended force args
    python scripts/improve_policy.py --activate land-l25-smoke
    python scripts/improve_policy.py --clear-campaign
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO / "improve" / "improve-policy.yaml"
LOG_PATH = REPO / "dev_docs" / "improve-log.md"


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Tiny subset parser for our policy file when PyYAML is unavailable."""
    # Prefer full PyYAML; this is a best-effort fallback for active_campaign + ids.
    out: dict[str, Any] = {"version": 1, "campaigns": {}, "steady_state": {}}
    m = re.search(r"^active_campaign:\s*(\S+)\s*$", text, re.M)
    if m:
        raw = m.group(1).strip()
        out["active_campaign"] = None if raw in ("null", "~", "None") else raw.strip("\"'")
    # campaign block names
    for _cm in re.finditer(r"^  ([a-zA-Z0-9_-]+):\s*$", text, re.M):
        # only under campaigns: — crude: collect after "campaigns:"
        pass
    if "land-l25-smoke" in text:
        out.setdefault("campaigns", {})["land-l25-smoke"] = {
            "prefer": {
                "lane": "example-apps",
                "strategy": "agent_qa_smoke",
                "force_args": "example-apps agent_qa_smoke",
            },
            "yield_to": ["regression", "ci_repair", "codeql", "github_inbox", "self_audit_cadence"],
            "boost_probe": "qa_smoke",
        }
    # recurring
    every = re.search(r"every_n_cycles:\s*(\d+)", text)
    if every:
        out.setdefault("steady_state", {})["recurring"] = [
            {
                "id": "agent_qa_smoke",
                "every_n_cycles": int(every.group(1)),
                "lane": "example-apps",
                "strategy": "agent_qa_smoke",
                "force_args": "example-apps agent_qa_smoke",
            }
        ]
    return out


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "active_campaign": None, "steady_state": {}, "campaigns": {}}
    return _load_yaml(path)


def save_active_campaign(campaign_id: str | None, path: Path = POLICY_PATH) -> None:
    if not path.is_file():
        raise SystemExit(f"missing policy file: {path}")
    text = path.read_text(encoding="utf-8")
    val = "null" if not campaign_id else campaign_id
    if re.search(r"^active_campaign:\s*\S+\s*$", text, re.M):
        text = re.sub(
            r"^active_campaign:\s*\S+\s*$",
            f"active_campaign: {val}",
            text,
            count=1,
            flags=re.M,
        )
    else:
        text = f"active_campaign: {val}\n" + text
    path.write_text(text, encoding="utf-8")


def current_cycle_hint() -> int | None:
    """Best-effort current cycle from improve-log heading."""
    if not LOG_PATH.is_file():
        return None
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Look for "## Cycle 1304" or "cycle 1304"
    nums = [int(x) for x in re.findall(r"(?i)cycle\s+(\d{3,5})", text)]
    return max(nums) if nums else None


def _cycle_blocks(text: str) -> list[tuple[int, str]]:
    """Return (cycle_num, body) for each ``## Cycle N`` block in the log."""
    blocks = list(re.finditer(r"^## Cycle\s+(\d+)\b", text, re.M))
    out: list[tuple[int, str]] = []
    for i, m in enumerate(blocks):
        start = m.start()
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(text)
        out.append((int(m.group(1)), text[start:end]))
    return out


def last_strategy_cycle(strategy: str) -> int | None:
    """Most recent cycle that ran ``strategy``.

    Matches the explicit ``**strategy:**`` field (substring). When the rotation
    id is a lane name (e.g. ``framework-ux``), also matches ``**lane:**``.
    Does not scan Next/picked prose (avoids inflating last-run from mentions).
    """
    if not LOG_PATH.is_file() or not strategy:
        return None
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    needle = strategy.lower()
    best: int | None = None
    for num, chunk in _cycle_blocks(text):
        m = re.search(r"\*\*strategy:\*\*\s*([^\n]+)", chunk)
        if m and needle in m.group(1).lower():
            if best is None or num > best:
                best = num
            continue
        lane_m = re.search(r"\*\*lane:\*\*\s*([^\s\n]+)", chunk)
        if lane_m and lane_m.group(1).lower() == needle:
            if best is None or num > best:
                best = num
    return best


def recent_strategy_streak(strategy: str, *, window: int = 8) -> int:
    """How many of the most recent dig cycles used ``strategy`` consecutively from tip."""
    if not LOG_PATH.is_file() or not strategy:
        return 0
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    blocks = _cycle_blocks(text)
    if not blocks:
        return 0
    streak = 0
    for num, chunk in reversed(blocks[-window:]):
        del num  # cycle id unused; order is enough
        m = re.search(r"\*\*strategy:\*\*\s*([^\n]+)", chunk)
        strat_line = (m.group(1) if m else chunk[:400]).lower()
        if strategy.lower() in strat_line:
            streak += 1
        else:
            break
    return streak


# Cadence / Goal-B digs — do not count toward harness monoculture streak.
_CADENCE_OR_GOAL_B_MARKERS: frozenset[str] = frozenset(
    {
        "self-audit",
        "self_audit",
        "capability-sweep",
        "capability_sweep",
        "interesting_product",
        "housekeeping",
        "cimonitor",
        "codeql",
        "hyperpart_presentation",
    }
)

# Explicit open-hop / dual-open language (strong Goal A thrash signal).
_OPEN_HOP_STRATEGY_MARKERS: frozenset[str] = frozenset(
    {
        "story_walk",
        "journey_dogfood",
        "agent_acceptance_panel",
        "gallery_probes",
        "dual-open",
        "triple-open",
        "dual_open",
        "triple_open",
        "open discovery",
        "hop label",
        "chain-entity",
        "chain-via",
        "framework-ux",
        "edge_cases",
        "edge /",
    }
)


def consecutive_open_hop_streak(*, window: int = 16) -> int:
    """Count tipward digs that are Goal A harness farming under residual green.

    Post-5.8 doctrine: after K such cycles while residual_total=0, force
    ``interesting_product`` (Goal B depth + still proof). Cadence and Goal B
    cycles are transparent (do not break or count).
    """
    if not LOG_PATH.is_file():
        return 0
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    blocks = _cycle_blocks(text)
    if not blocks:
        return 0
    streak = 0
    for _num, chunk in reversed(blocks[-window:]):
        lower = chunk.lower()
        # Match only on lane/strategy lines (body always mentions github/codeql).
        lane_m = re.search(r"\*\*lane:\*\*\s*([^\n]+)", lower)
        strat_m = re.search(r"\*\*strategy:\*\*\s*([^\n]+)", lower)
        lane_s = (lane_m.group(1) if lane_m else "").strip()
        strat_s = (strat_m.group(1) if strat_m else "").strip()
        head = f"{lane_s} {strat_s}"
        if any(m in head for m in _CADENCE_OR_GOAL_B_MARKERS):
            continue
        summary_m = re.search(r"\*\*summary:\*\*\s*([^\n]+)", lower)
        blob = f"{strat_s} {(summary_m.group(1) if summary_m else '')} {lower[:600]}"
        if any(marker in blob for marker in _OPEN_HOP_STRATEGY_MARKERS):
            streak += 1
            continue
        # Unknown dig still counts as non-Goal-B thrash when residual is green.
        if strat_s or lane_s:
            streak += 1
            continue
        break
    return streak


def coat_residual_total() -> tuple[int, str | None]:
    """Goal C coat heat — flagged apps and the worst next distill target.

    Separate from product_residual_total so demo-safe A stays green while
    a filter wall is still visible to pick().
    """
    try:
        from scripts.goal_b_coat import coat_residual
    except Exception:  # noqa: BLE001
        try:
            import goal_b_coat as _coat  # type: ignore

            coat_residual = _coat.coat_residual
        except Exception:  # noqa: BLE001
            return 0, None
    try:
        return coat_residual()
    except Exception:  # noqa: BLE001
        return 0, None


def product_residual_total() -> int:
    """Felt+structural residual heat (0 when demo-safe residual era is green).

    Uses product_quality residual_total when importable; otherwise 0 so policy
    can still fire interesting_product on open-hop cap alone.
    """
    try:
        from dazzle.product_quality import score_project

        report = score_project(REPO / "examples")
        return int(report.residual_total or 0)
    except Exception:  # noqa: BLE001 — policy isolation
        return 0


def hm_coherence_queue_depth() -> int | None:
    """Return incoherent Hyperpart count from latest coherence sweep.

    ``None`` = no coherence.json (investigate is due). ``0`` = last sweep clean
    — under ``require_mutation`` campaigns, skip stamp-only hyperpart_coherence
    so rotation advances to framework-ux / story_walk / panels.
    """
    path = REPO / ".dazzle" / "hm-hyperpart-coherence" / "coherence.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if "n_incoherent" in data:
        try:
            return int(data["n_incoherent"])
        except (TypeError, ValueError):
            return None
    results = data.get("results") or []
    if isinstance(results, list):
        return sum(1 for r in results if isinstance(r, dict) and not r.get("coherent", True))
    return 0


def dual_lock_queue_depth() -> int | None:
    """Return dual-lock promotion queue depth (markdown table preferred).

    Prefer parsing the generated DUAL_LOCK_QUEUE.md (no subprocess). Fall back to
    the queue tool ``--json`` when the markdown is missing.
    """
    md = REPO / "packages" / "hatchi-maxchi" / "DUAL_LOCK_QUEUE.md"
    if md.is_file():
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if text:
            # Count data rows under the main queue table (stem | kind | pri | …).
            rows = 0
            in_table = False
            for line in text.splitlines():
                if line.startswith("| # | stem |"):
                    in_table = True
                    continue
                if in_table:
                    if not line.startswith("|"):
                        break
                    if re.match(r"^\|\s*-+", line):
                        continue
                    # Skip empty placeholder rows (only pipes/spaces)
                    cells = [c.strip() for c in line.strip("|").split("|")]
                    if cells and cells[0].isdigit():
                        # row with an index but empty stem → no candidate
                        if len(cells) > 1 and cells[1]:
                            rows += 1
            return rows

    tool = REPO / "packages" / "hatchi-maxchi" / "tools" / "dual_lock_queue.py"
    if not tool.is_file():
        return None
    import subprocess

    try:
        proc = subprocess.run(
            [sys.executable, str(tool), "--json"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("queue") or data.get("items")
        if isinstance(rows, list):
            return len(rows)
        if "depth" in data:
            try:
                return int(data["depth"])
            except (TypeError, ValueError):
                return None
    return None


def qa_smoke_residual() -> tuple[int, str | None]:
    bar = REPO / "scripts" / "qa_smoke_bar.py"
    if not bar.is_file():
        return 0, None
    import importlib.util

    spec = importlib.util.spec_from_file_location("qa_smoke_bar", bar)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qa_smoke_bar"] = mod  # required for dataclass on 3.14
    spec.loader.exec_module(mod)
    rows = mod.scan()
    residual = [r for r in rows if r.is_residual()]
    nxt = residual[0].app if residual else None
    return len(residual), nxt


def _is_hyperpart_coherence_entry(ent: dict[str, Any]) -> bool:
    force = str(ent.get("force_args") or "").lower()
    strat = str(ent.get("strategy") or "").lower()
    return "hyperpart_coherence" in force or strat == "hyperpart_coherence"


def _entry_eligible(
    ent: dict[str, Any],
    *,
    smoke_n: int,
    dual_depth: int | None,
    coherence_depth: int | None,
    panel_streak: int,
    max_consecutive_panels: int,
    require_mutation: bool,
) -> bool:
    """Filter rotation entries that would be stamp-only under current signals."""
    if ent.get("require_dual_lock_queue") and dual_depth is not None and dual_depth <= 0:
        return False
    if ent.get("require_smoke_residual") and smoke_n <= 0:
        return False
    # Aggressive: empty coherence queue + existing sweep → skip stamp-only hyperpart.
    # Missing coherence.json (None) keeps the entry (investigate due).
    if (
        require_mutation
        and _is_hyperpart_coherence_entry(ent)
        and coherence_depth is not None
        and coherence_depth <= 0
        and not ent.get("force_investigate")
    ):
        return False
    if (
        ent.get("is_panel")
        and max_consecutive_panels > 0
        and panel_streak >= max_consecutive_panels
    ):
        return False
    return True


def _pick_rotation(
    rotation: list[Any],
    *,
    cur: int,
    campaign_id: str,
    camp: dict[str, Any] | None = None,
    smoke_n: int = 0,
) -> dict[str, Any] | None:
    """Pick least-recently-used eligible strategy from campaign prefer_rotation."""
    camp = camp or {}
    dual_depth = dual_lock_queue_depth()
    coherence_depth = hm_coherence_queue_depth()
    max_panels = int(camp.get("max_consecutive_panels") or 0)
    panel_streak = recent_strategy_streak("agent_acceptance_panel") if max_panels else 0
    require_mutation = bool(camp.get("require_mutation"))

    raw = [r for r in rotation if isinstance(r, dict) and r.get("force_args")]
    if not raw:
        return None

    entries = [
        e
        for e in raw
        if _entry_eligible(
            e,
            smoke_n=smoke_n,
            dual_depth=dual_depth,
            coherence_depth=coherence_depth,
            panel_streak=panel_streak,
            max_consecutive_panels=max_panels,
            require_mutation=require_mutation,
        )
    ]
    # If filters emptied the list (e.g. all gated), fall back to non-gated only.
    if not entries:
        entries = [
            e
            for e in raw
            if not e.get("require_dual_lock_queue")
            and not e.get("require_smoke_residual")
            and not e.get("is_panel")
            and not (
                require_mutation
                and _is_hyperpart_coherence_entry(e)
                and coherence_depth is not None
                and coherence_depth <= 0
            )
        ] or raw

    best: dict[str, Any] | None = None
    best_last = 10**9
    for ent in entries:
        sid = str(ent.get("strategy") or ent.get("id") or "")
        force = str(ent.get("force_args") or "")
        last = last_strategy_cycle(sid) if sid else None
        if last is None and force:
            parts = force.split()
            if len(parts) >= 2:
                last = last_strategy_cycle(parts[-1])
            elif parts:
                last = last_strategy_cycle(parts[0])
        # Prefer never-run (None) then oldest last-run
        score = last if last is not None else -1
        if best is None or score < best_last:
            best = ent
            best_last = score
    if best is None:
        best = entries[cur % len(entries)]

    reason = f"campaign:{campaign_id} rotation={best.get('strategy') or best.get('force_args')}"
    if dual_depth is not None and best.get("require_dual_lock_queue"):
        reason += f" dual_queue={dual_depth}"
    if coherence_depth is not None:
        reason += f" coherence_queue={coherence_depth}"
    if (
        panel_streak
        and best.get("is_panel") is not True
        and max_panels
        and panel_streak >= max_panels
    ):
        reason += f" panel_streak_break={panel_streak}"
    if (
        require_mutation
        and coherence_depth is not None
        and coherence_depth <= 0
        and not _is_hyperpart_coherence_entry(best)
    ):
        reason += " skip_drained_hyperpart"
    return {
        "force_args": best.get("force_args"),
        "lane": best.get("lane"),
        "strategy": best.get("strategy"),
        "reason": reason,
        "dual_lock_queue_depth": dual_depth,
        "coherence_queue_depth": coherence_depth,
        "panel_streak": panel_streak,
    }


def pick(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return recommended lane/strategy force for this cycle (policy layer only)."""
    policy = policy or load_policy()
    active = policy.get("active_campaign")
    smoke_n, smoke_next = qa_smoke_residual()
    cur = current_cycle_hint() or 0
    residual = product_residual_total()
    coat_n, coat_next = coat_residual_total()
    open_hop = consecutive_open_hop_streak()
    # Post-5.8: after K open-hop digs under residual=0, force Goal B depth pack.
    max_open_hop = int((policy.get("steady_state") or {}).get("max_consecutive_open_hop") or 5)
    campaigns = policy.get("campaigns") or {}
    if active and active in campaigns:
        camp_for_cap = campaigns[active] or {}
        if camp_for_cap.get("max_consecutive_open_hop") is not None:
            max_open_hop = int(camp_for_cap["max_consecutive_open_hop"])

    decision: dict[str, Any] = {
        "active_campaign": active,
        "qa_smoke_residual": smoke_n,
        "qa_smoke_next": smoke_next,
        "product_residual_total": residual,
        "coat_residual_total": coat_n,
        "coat_next": coat_next,
        "open_hop_streak": open_hop,
        "max_consecutive_open_hop": max_open_hop,
        "current_cycle_hint": cur or None,
        "force_args": None,
        "lane": None,
        "strategy": None,
        "reason": "steady_state_default",
        "posture": None,
    }

    campaigns = policy.get("campaigns") or {}
    if active and active in campaigns:
        camp = campaigns[active] or {}
        decision["posture"] = camp.get("posture")
        prefer = camp.get("prefer") or {}
        boost = camp.get("boost_probe")

        # Smoke residual always wins when present (gross bugs).
        if smoke_n > 0:
            decision.update(
                {
                    "force_args": prefer.get("force_args")
                    if boost == "qa_smoke"
                    else "example-apps agent_qa_smoke",
                    "lane": "example-apps",
                    "strategy": "agent_qa_smoke",
                    "reason": f"campaign:{active} smoke_residual={smoke_n} next={smoke_next}",
                }
            )
            if boost == "qa_smoke" and prefer.get("force_args"):
                decision["force_args"] = prefer.get("force_args")
                decision["lane"] = prefer.get("lane") or "example-apps"
                decision["strategy"] = prefer.get("strategy") or "agent_qa_smoke"
            return decision

        # Goal C: residual green but a desk is a filter wall → distill, not add.
        if residual <= 0 and coat_n > 0:
            decision.update(
                {
                    "force_args": f"example-apps distill {coat_next}"
                    if coat_next
                    else "example-apps distill",
                    "lane": "example-apps",
                    "strategy": "distill",
                    "require_mutation": True,
                    "reason": (f"campaign:{active} coat_residual={coat_n} next={coat_next or '-'}"),
                }
            )
            return decision

        # Post-5.8 Goal B: residual green + open-hop monoculture → interesting depth.
        if (
            residual <= 0
            and open_hop >= max_open_hop
            and camp.get("interesting_product_when_green", True)
        ):
            decision.update(
                {
                    "force_args": "example-apps interesting_product",
                    "lane": "example-apps",
                    "strategy": "interesting_product",
                    "reason": (
                        f"campaign:{active} interesting_product residual=0 "
                        f"open_hop_streak={open_hop}>={max_open_hop}"
                    ),
                    "require_mutation": bool(camp.get("require_mutation")),
                }
            )
            _attach_interesting_portfolio(decision, camp)
            return decision

        # Aggressive / multi-strategy campaigns: rotate high-leverage digs.
        rotation = camp.get("prefer_rotation") or []
        if rotation:
            rot = _pick_rotation(
                rotation,
                cur=cur,
                campaign_id=str(active),
                camp=camp,
                smoke_n=smoke_n,
            )
            if rot:
                decision.update(rot)
                if camp.get("require_mutation"):
                    decision["require_mutation"] = True
                # Label harness walks when residual green (doctrine messaging).
                if residual <= 0 and rot.get("strategy") in {
                    "story_walk",
                    "journey_dogfood",
                    "agent_acceptance_panel",
                    "gallery_probes",
                }:
                    decision["harness_only"] = True
                    decision["reason"] = (
                        f"{decision.get('reason') or ''} residual=0_harness_ok"
                    ).strip()
                if rot.get("strategy") == "interesting_product":
                    _attach_interesting_portfolio(decision, camp)
                return decision

        # Legacy single-prefer campaigns (e.g. land-l25-smoke always digs smoke).
        if boost == "qa_smoke" or prefer.get("force_args"):
            decision.update(
                {
                    "force_args": prefer.get("force_args") or "example-apps agent_qa_smoke",
                    "lane": prefer.get("lane") or "example-apps",
                    "strategy": prefer.get("strategy") or "agent_qa_smoke",
                    "reason": f"campaign:{active} dig_exercise",
                }
            )
            return decision

    # Recurring L2.5 when residual clear of campaign
    suppress_smoke = False
    if active and active in campaigns:
        suppress_smoke = bool((campaigns.get(active) or {}).get("suppress_recurring_smoke"))

    recurring = (policy.get("steady_state") or {}).get("recurring") or []
    for rec in recurring:
        if not isinstance(rec, dict):
            continue
        every = int(rec.get("every_n_cycles") or 0)
        if every <= 0:
            continue
        sid = str(rec.get("id") or rec.get("strategy") or "")
        if suppress_smoke and sid in ("agent_qa_smoke", "agent_qa_smoke".replace("_", "-")):
            # Aggressive campaigns still honor non-empty smoke residual above.
            continue
        last = last_strategy_cycle(sid) or last_strategy_cycle(str(rec.get("strategy") or ""))
        due = last is None or (cur and (cur - last) >= every)
        if due or smoke_n > 0:
            decision.update(
                {
                    "force_args": rec.get("force_args") or "example-apps agent_qa_smoke",
                    "lane": rec.get("lane") or "example-apps",
                    "strategy": rec.get("strategy") or "agent_qa_smoke",
                    "reason": (
                        f"recurring:{sid} due (last={last} every={every})"
                        if due
                        else f"qa_smoke residual={smoke_n}"
                    ),
                }
            )
            return decision

    if smoke_n > 0:
        decision.update(
            {
                "force_args": "example-apps agent_qa_smoke",
                "lane": "example-apps",
                "strategy": "agent_qa_smoke",
                "reason": f"qa_smoke residual={smoke_n} next={smoke_next}",
            }
        )
    return decision


def _attach_interesting_portfolio(
    decision: dict[str, Any], camp: dict[str, Any] | None = None
) -> None:
    """Enrich interesting_product picks with portfolio recommend (best-effort)."""
    camp = camp or {}
    try:
        from scripts.interesting_product_portfolio import snapshot as portfolio_snapshot
    except Exception:  # noqa: BLE001 — policy isolation
        try:
            # When run as script, package path may differ
            import interesting_product_portfolio as ipp  # type: ignore

            portfolio_snapshot = ipp.snapshot
        except Exception:  # noqa: BLE001
            return
    try:
        max_depth = int(
            camp.get("max_consecutive_same_depth")
            or (load_policy().get("steady_state") or {}).get("max_consecutive_same_depth")
            or 3
        )
        max_recipe = int(
            camp.get("max_consecutive_same_recipe")
            or (load_policy().get("steady_state") or {}).get("max_consecutive_same_recipe")
            or 3
        )
        stack_t = int(
            camp.get("stack_target")
            or (load_policy().get("steady_state") or {}).get("stack_target")
            or 3
        )
        snap = portfolio_snapshot(
            max_same_depth=max_depth,
            max_same_recipe=max_recipe,
            stack_target=stack_t,
        )
    except Exception:  # noqa: BLE001
        return
    decision["portfolio_depth_streak"] = snap.depth_streak
    decision["portfolio_depth_streak_id"] = snap.depth_streak_id
    decision["portfolio_recipe_streak"] = snap.recipe_streak
    decision["portfolio_recipe_streak_id"] = snap.recipe_streak_id
    decision["portfolio_banned_depths"] = list(snap.banned_depths)
    decision["portfolio_banned_recipes"] = list(snap.banned_recipes)
    decision["portfolio_saturated_cells"] = list(snap.saturated_cells)
    if snap.recommend:
        decision["interesting_product_recommend"] = snap.recommend
        app = snap.recommend.get("app")
        depth = snap.recommend.get("depth_id")
        if app and depth:
            decision["force_args"] = f"example-apps interesting_product {app} {depth}"
            decision["reason"] = (
                f"{decision.get('reason') or 'interesting_product'} portfolio={app}/{depth}"
            ).strip()
    else:
        # Saturated matrix: stop is a legal Goal B cycle. Do not invent a coat.
        decision["interesting_product_saturated"] = True
        if decision.get("strategy") == "interesting_product":
            decision["require_mutation"] = False
            decision["force_args"] = "framework-ux"
            decision["lane"] = "framework-ux"
            decision["strategy"] = "framework-ux"
            decision["reason"] = (
                f"{decision.get('reason') or 'interesting_product'} goal_b_saturated_stop"
            ).strip()


def leftover_token_status_line() -> str:
    """Leftover-honest token cadence (oral #121/#127). Best-effort; never raises."""
    script = REPO / "scripts" / "improve_commit_contract.py"
    if not script.is_file():
        return ""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("improve_commit_contract", script)
        if spec is None or spec.loader is None:
            return ""
        mod = importlib.util.module_from_spec(spec)
        sys.modules["improve_commit_contract"] = mod  # dataclass on 3.14
        spec.loader.exec_module(mod)
        cad = mod.cadence_of(mod.git_recent_subjects())
        return mod.format_status(cad)
    except Exception:  # noqa: BLE001 — status is advisory
        return ""


def format_status(policy: dict[str, Any] | None = None) -> str:
    policy = policy or load_policy()
    d = pick(policy)
    camp = (policy.get("campaigns") or {}).get(policy.get("active_campaign") or "") or {}
    lines = [
        f"improve_policy active_campaign={policy.get('active_campaign') or '-'}",
        f"posture={d.get('posture') or camp.get('posture') or 'steady'}",
        f"pick force={d.get('force_args') or '-'} reason={d.get('reason')}",
        f"qa_smoke residual={d.get('qa_smoke_residual')} next={d.get('qa_smoke_next') or '-'}",
    ]
    if camp.get("suppress_recurring_smoke"):
        lines.append("suppress_recurring_smoke=1")
    if camp.get("require_mutation") or d.get("require_mutation"):
        lines.append("require_mutation=1")
    if d.get("dual_lock_queue_depth") is not None:
        lines.append(f"dual_lock_queue_depth={d.get('dual_lock_queue_depth')}")
    if d.get("coherence_queue_depth") is not None:
        lines.append(f"coherence_queue_depth={d.get('coherence_queue_depth')}")
    if d.get("panel_streak"):
        lines.append(f"panel_streak={d.get('panel_streak')}")
    if d.get("product_residual_total") is not None:
        lines.append(f"product_residual_total={d.get('product_residual_total')}")
    if d.get("coat_residual_total") is not None:
        lines.append(
            f"coat_residual_total={d.get('coat_residual_total')} next={d.get('coat_next') or '-'}"
        )
    if d.get("open_hop_streak") is not None:
        lines.append(
            f"open_hop_streak={d.get('open_hop_streak')}/{d.get('max_consecutive_open_hop') or 5}"
        )
    if d.get("harness_only"):
        lines.append("harness_only=1")
    leftover = leftover_token_status_line()
    if leftover:
        lines.append(leftover)
    # Portfolio lines when Goal B is in play or residual green (best-effort).
    if d.get("strategy") == "interesting_product" or (
        d.get("product_residual_total") is not None
        and int(d.get("product_residual_total") or 0) <= 0
    ):
        if (
            not d.get("interesting_product_recommend")
            and d.get("strategy") != "interesting_product"
        ):
            # Attach for operator visibility even when pick is elsewhere.
            probe: dict[str, Any] = {"strategy": "interesting_product", "reason": "status"}
            _attach_interesting_portfolio(probe, camp)
            for k, v in probe.items():
                if (
                    k.startswith("portfolio_")
                    or k == "interesting_product_recommend"
                    or k == "interesting_product_saturated"
                ):
                    d.setdefault(k, v)
        rec = d.get("interesting_product_recommend")
        if rec:
            lines.append(
                f"interesting_product_recommend app={rec.get('app')} "
                f"depth_id={rec.get('depth_id')} reason={rec.get('reason')}"
            )
        if d.get("interesting_product_saturated"):
            lines.append("interesting_product_saturated=1 require_mutation=0")
        if d.get("portfolio_depth_streak") is not None:
            lines.append(
                f"portfolio_depth_streak={d.get('portfolio_depth_streak')}"
                + (
                    f" id={d.get('portfolio_depth_streak_id')}"
                    if d.get("portfolio_depth_streak_id")
                    else ""
                )
            )
        if d.get("portfolio_recipe_streak"):
            lines.append(
                f"portfolio_recipe_streak={d.get('portfolio_recipe_streak')}"
                + (
                    f" id={d.get('portfolio_recipe_streak_id')}"
                    if d.get("portfolio_recipe_streak_id")
                    else ""
                )
            )
        banned_d = d.get("portfolio_banned_depths") or []
        banned_r = d.get("portfolio_banned_recipes") or []
        if banned_d:
            lines.append(f"portfolio_banned_depths={','.join(banned_d)}")
        if banned_r:
            lines.append(f"portfolio_banned_recipes={','.join(banned_r)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true")
    p.add_argument("--pick", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--activate", metavar="CAMPAIGN_ID")
    p.add_argument("--clear-campaign", action="store_true")
    args = p.parse_args(argv)

    if args.activate:
        pol = load_policy()
        known = set(pol.get("campaigns") or {}) | {"land-l25-smoke", "aggressive-change"}
        if args.activate not in known:
            print(f"unknown campaign: {args.activate}", file=sys.stderr)
            print(f"known: {sorted(known)}", file=sys.stderr)
            return 2
        save_active_campaign(args.activate)
        print(f"active_campaign={args.activate}")
        return 0
    if args.clear_campaign:
        save_active_campaign(None)
        print("active_campaign=null")
        return 0

    policy = load_policy()
    d = pick(policy)
    if args.json:
        print(json.dumps({"policy_active": policy.get("active_campaign"), **d}, indent=2))
    elif args.pick:
        print(d.get("force_args") or "")
    else:
        print(format_status(policy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
