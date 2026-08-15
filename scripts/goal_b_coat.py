#!/usr/bin/env python3
"""Goal B/C coat scanner — freeze ratchet + honest-grain residual.

Upgrade + novel recipe tag + floor pin produced cartesian ``display: conversation``
and document-rail coats. This module is the machine surface:

* **Freeze** — current counts must not grow (unit pins / growth residual).
* **Honest grain** — ``coat_flag`` / ``coat_residual_total`` so /improve can
  *pick distill* on desks that already overflowed. Freeze is “don’t worsen”;
  honest grain is “done.”

Usage::

    python scripts/goal_b_coat.py --status
    python scripts/goal_b_coat.py --json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

# Planner stop / coat_flag — a cell above these is saturated and distill-eligible.
HONEST_CONVERSATION_SITES = 8
HONEST_DOCUMENT_RAILS = 8
HONEST_FOCUS = 12
HONEST_METRICS = 8
HONEST_SIBLINGS = 2
HONEST_CARTESIAN = 0
# Two exclusive photo-entity grids (Device bench vs IssueReport defect) is
# media honest grain — a third photo_url AND is coat theatre (oral #20).
HONEST_MEDIA_ENTITIES = 2

# Freeze ratchet — measured 2026-08-14. Lower only when a distill lands.
FREEZE: dict[str, dict[str, int]] = {
    "support_tickets": {
        "conversation_sites": 8,
        "conversation_names": 5,
        "max_focus": 10,
        "metric_keys": 19,
    },
    "invoice_ops": {
        "conversation_sites": 7,
        "document_rails": 7,
        "max_focus": 11,
        "metric_keys": 47,
    },
    "simple_task": {
        "conversation_sites": 9,
        "conversation_names": 4,
        "max_focus": 5,
        "metric_keys": 19,
    },
}

_CONV_DISPLAY = re.compile(r"display:\s*conversation")
_FOCUS = re.compile(r"focus:\s*([^\n]+)")
_METRIC_KEY = re.compile(r"^      ([a-z_][a-z0-9_]*):\s*count\(", re.M)
_RAIL = re.compile(r"^  ([a-z_][a-z0-9_]*(?:rail|watch)[a-z0-9_]*):", re.M)
_REGION_NAME = re.compile(r"^  ([a-z_][a-z0-9_]*):\s*$")
_WS_HEAD = re.compile(r"^workspace\s+(\w+)", re.M)
_DISPLAY_LINE = re.compile(r"^\s+display:\s*(\w+)", re.M)
_SOURCE_LINE = re.compile(r"^\s+(?:source|show):\s*(\w+)", re.M)
_FILTER_LINE = re.compile(r"^\s+filter:\s*(.+)$", re.M)
_BALL = re.compile(r"\bball_in_court\s*=")
_CARTESIAN_OTHER = re.compile(
    r"\b(customer_tone|case_priority|sla_pressure|channel|escalation|sla_state)\s*="
)
_SIBLING_DISPLAYS = frozenset({"conversation", "queue", "list", "timeline"})


@dataclass(frozen=True)
class CoatMeasure:
    app: str
    conversation_sites: int
    conversation_names: int
    max_focus: int
    metric_keys: int
    document_rails: int
    coat_siblings: int = 0
    conv_siblings: int = 0
    slice_cartesian: int = 0
    sibling_key: str = ""
    coat_flag: int = 0
    over: dict[str, int] = field(default_factory=dict)


def showcase_apps(*, examples: Path = EXAMPLES) -> list[str]:
    if not examples.is_dir():
        return []
    return sorted(
        p.name
        for p in examples.iterdir()
        if p.is_dir() and (p / "dazzle.toml").is_file() and not p.name.startswith(".")
    )


def dsl_blob(app: str, *, examples: Path = EXAMPLES) -> str:
    root = examples / app
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(root.rglob("*.dsl")):
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(parts)


def _conversation_names(text: str) -> set[str]:
    names: set[str] = set()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _REGION_NAME.match(line)
        if not m:
            continue
        window = "\n".join(lines[i : i + 18])
        if _CONV_DISPLAY.search(window):
            names.add(m.group(1))
    return names


def _max_focus(text: str) -> int:
    lengths = []
    for raw in _FOCUS.findall(text):
        n = len([x.strip() for x in raw.split(",") if x.strip()])
        if n:
            lengths.append(n)
    return max(lengths) if lengths else 0


def _workspace_region_windows(text: str) -> list[tuple[str, str, str]]:
    """Yield (workspace, region_name, body) for 2-space regions under workspaces."""
    heads = list(_WS_HEAD.finditer(text))
    out: list[tuple[str, str, str]] = []
    for i, hm in enumerate(heads):
        ws = hm.group(1)
        chunk = text[hm.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        lines = chunk.splitlines()
        starts: list[tuple[int, str]] = []
        for li, line in enumerate(lines):
            rm = _REGION_NAME.match(line)
            if rm and rm.group(1) not in {"ux", "aggregate", "access", "transitions"}:
                starts.append((li, rm.group(1)))
        for j, (li, name) in enumerate(starts):
            end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
            body = "\n".join(lines[li:end])
            out.append((ws, name, body))
    return out


def _siblings_and_cartesian(text: str) -> tuple[int, int, str, int]:
    """Return (max_any_siblings, conv_siblings, best_key, cartesian_count)."""
    groups: dict[tuple[str, str, str], int] = {}
    conv_groups: dict[tuple[str, str, str], int] = {}
    cartesian = 0
    for ws, _name, body in _workspace_region_windows(text):
        dm = _DISPLAY_LINE.search(body)
        if not dm:
            continue
        display = dm.group(1)
        sm = _SOURCE_LINE.search(body)
        source = sm.group(1) if sm else ""
        if display in _SIBLING_DISPLAYS and source:
            key = (ws, display, source)
            groups[key] = groups.get(key, 0) + 1
            if display == "conversation":
                conv_groups[key] = conv_groups.get(key, 0) + 1
        if display == "conversation":
            fm = _FILTER_LINE.search(body)
            filt = fm.group(1) if fm else ""
            if _BALL.search(filt) and _CARTESIAN_OTHER.search(filt):
                cartesian += 1
    conv_sib = max(conv_groups.values()) if conv_groups else 0
    if not groups:
        return 0, conv_sib, "", cartesian
    best_key = max(groups, key=lambda k: groups[k])
    return groups[best_key], conv_sib, f"{best_key[0]}/{best_key[1]}/{best_key[2]}", cartesian


def _over(m: CoatMeasure) -> dict[str, int]:
    raw = {
        "conversation_sites": m.conversation_sites - HONEST_CONVERSATION_SITES,
        "document_rails": m.document_rails - HONEST_DOCUMENT_RAILS,
        "max_focus": m.max_focus - HONEST_FOCUS,
        "metric_keys": m.metric_keys - HONEST_METRICS,
        "coat_siblings": m.coat_siblings - HONEST_SIBLINGS,
        "conv_siblings": m.conv_siblings - HONEST_SIBLINGS,
        "slice_cartesian": m.slice_cartesian - HONEST_CARTESIAN,
    }
    return {k: v for k, v in raw.items() if v > 0}


def _flag(m: CoatMeasure) -> bool:
    """Distill-eligible signature — not every metric-rich desk.

    Metric-key overflow is diagnostic only. The adverse pattern is a
    conversation/rail sibling wall, cartesian enum×ball filters, or a
    focus list that is no longer a pair.
    """
    return (
        m.slice_cartesian > HONEST_CARTESIAN
        or m.conv_siblings > HONEST_SIBLINGS
        or m.document_rails > HONEST_DOCUMENT_RAILS
        or m.max_focus > HONEST_FOCUS
    )


def measure(app: str, *, examples: Path = EXAMPLES) -> CoatMeasure:
    text = dsl_blob(app, examples=examples)
    siblings, conv_sib, sib_key, cartesian = _siblings_and_cartesian(text)
    base = CoatMeasure(
        app=app,
        conversation_sites=len(_CONV_DISPLAY.findall(text)),
        conversation_names=len(_conversation_names(text)),
        max_focus=_max_focus(text),
        metric_keys=len(set(_METRIC_KEY.findall(text))),
        document_rails=len(_RAIL.findall(text)),
        coat_siblings=siblings,
        conv_siblings=conv_sib,
        slice_cartesian=cartesian,
        sibling_key=sib_key,
    )
    over = _over(base)
    return CoatMeasure(
        app=base.app,
        conversation_sites=base.conversation_sites,
        conversation_names=base.conversation_names,
        max_focus=base.max_focus,
        metric_keys=base.metric_keys,
        document_rails=base.document_rails,
        coat_siblings=base.coat_siblings,
        conv_siblings=base.conv_siblings,
        slice_cartesian=base.slice_cartesian,
        sibling_key=base.sibling_key,
        coat_flag=1 if _flag(base) else 0,
        over=over,
    )


def scan(*, examples: Path = EXAMPLES) -> list[CoatMeasure]:
    return [measure(a, examples=examples) for a in showcase_apps(examples=examples)]


def coat_residual(
    *,
    examples: Path = EXAMPLES,
    rows: list[CoatMeasure] | None = None,
) -> tuple[int, str | None]:
    """Return (coat_residual_total, next_app). next is worst flagged app."""
    rows = rows if rows is not None else scan(examples=examples)
    flagged = [r for r in rows if r.coat_flag]
    if not flagged:
        return 0, None
    flagged.sort(
        key=lambda r: (
            r.conv_siblings,
            r.slice_cartesian,
            r.document_rails,
            r.max_focus,
            r.coat_siblings,
        ),
        reverse=True,
    )
    return len(flagged), flagged[0].app


def photo_grid_entities(text: str) -> set[str]:
    """Entities that already have a photo_url grid (media honest grain)."""
    ents: set[str] = set()
    for _ws, _name, body in _workspace_region_windows(text):
        if not re.search(r"display:\s*grid", body):
            continue
        if not re.search(r"photo_url\s*!=", body):
            continue
        sm = _SOURCE_LINE.search(body)
        if sm:
            ents.add(sm.group(1))
    return ents


def note_kind_chrome_conversation(text: str) -> bool:
    """live_conversation trail labeled by note_kind — not a sibling filter slice.

    Oral #22: fieldtest conversation grain is chrome on the existing trail.
    A ``note_kind = repro`` region filter is coat theatre.
    """
    has_live = False
    for _ws, name, body in _workspace_region_windows(text):
        if name == "live_conversation" and re.search(r"display:\s*conversation", body):
            has_live = True
            break
    if not has_live:
        return False
    if not re.search(r"note_kind:\s*enum", text):
        return False
    for _ws, _name, body in _workspace_region_windows(text):
        fm = _FILTER_LINE.search(body)
        if fm and re.search(r"note_kind\s*=", fm.group(1)):
            return False
    return True


def stamp_pair_media(text: str) -> bool:
    """Exclusive in-review + approved pixel grids (Frame.io honest grain)."""
    has_review = False
    has_approved = False
    for _ws, name, body in _workspace_region_windows(text):
        if not re.search(r"display:\s*grid", body):
            continue
        if name == "review_pixels":
            has_review = True
        if name == "approved_pixels":
            has_approved = True
    return has_review and has_approved


def live_saturated_cells(
    apps: list[str],
    *,
    examples: Path = EXAMPLES,
    depths: tuple[str, ...] = (
        "conversation",
        "document",
        "media",
        "command_density",
        "org_structure",
        "empty_region_honesty",
    ),
) -> set[tuple[str, str]]:
    """Cells the planner must not upgrade."""
    sat: set[tuple[str, str]] = set()
    for app in apps:
        text = dsl_blob(app, examples=examples)
        m = measure(app, examples=examples)
        if m.max_focus > HONEST_FOCUS or m.conv_siblings > HONEST_SIBLINGS:
            for depth in depths:
                sat.add((app, depth))
            continue
        if (
            m.conversation_sites > HONEST_CONVERSATION_SITES
            or m.slice_cartesian > 0
            or note_kind_chrome_conversation(text)
        ):
            sat.add((app, "conversation"))
        if m.document_rails > HONEST_DOCUMENT_RAILS:
            sat.add((app, "document"))
        if len(photo_grid_entities(text)) >= HONEST_MEDIA_ENTITIES or stamp_pair_media(text):
            sat.add((app, "media"))
        # Goal C freeze: distilled cells stay planner-saturated so a later
        # interesting_product cycle cannot re-add rails/trails the freeze locked.
        caps = FREEZE.get(app) or {}
        if "document_rails" in caps:
            sat.add((app, "document"))
        if "conversation_sites" in caps or "conversation_names" in caps:
            sat.add((app, "conversation"))
    return sat


def freeze_breaches(
    *,
    examples: Path = EXAMPLES,
    freeze: dict[str, dict[str, int]] | None = None,
) -> list[str]:
    """Human-readable growth past the ratchet. Empty when frozen."""
    table = freeze if freeze is not None else FREEZE
    breaches: list[str] = []
    for app, caps in table.items():
        m = measure(app, examples=examples)
        live = {
            "conversation_sites": m.conversation_sites,
            "conversation_names": m.conversation_names,
            "max_focus": m.max_focus,
            "metric_keys": m.metric_keys,
            "document_rails": m.document_rails,
        }
        for key, cap in caps.items():
            got = int(live.get(key, 0))
            if got > cap:
                breaches.append(f"{app}.{key}={got}>{cap}")
    return breaches


def format_status(*, examples: Path = EXAMPLES) -> str:
    rows = scan(examples=examples)
    n, nxt = coat_residual(examples=examples, rows=rows)
    lines = [
        f"goal_b_coat residual_total={n} next={nxt or '-'} "
        f"force={'example-apps distill ' + nxt if nxt else '-'}"
    ]
    for m in rows:
        if not m.coat_flag and m.app not in FREEZE:
            continue
        over = ",".join(f"{k}+{v}" for k, v in m.over.items()) or "-"
        lines.append(
            f"  {m.app} flag={m.coat_flag} conv_sib={m.conv_siblings} "
            f"siblings={m.coat_siblings}({m.sibling_key or '-'}) "
            f"cartesian={m.slice_cartesian} focus={m.max_focus} "
            f"metrics={m.metric_keys} rails={m.document_rails} over={over}"
        )
    breaches = freeze_breaches(examples=examples)
    lines.append("freeze_breach=" + (",".join(breaches) if breaches else "0"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    rows = scan()
    n, nxt = coat_residual(rows=rows)
    breaches = freeze_breaches()
    if args.json:
        print(
            json.dumps(
                {
                    "honest": {
                        "conversation_sites": HONEST_CONVERSATION_SITES,
                        "document_rails": HONEST_DOCUMENT_RAILS,
                        "focus": HONEST_FOCUS,
                        "metrics": HONEST_METRICS,
                        "siblings": HONEST_SIBLINGS,
                        "cartesian": HONEST_CARTESIAN,
                    },
                    "freeze": FREEZE,
                    "residual_total": n,
                    "next": nxt,
                    "force": f"example-apps distill {nxt}" if nxt else None,
                    "measures": [asdict(r) for r in rows if r.coat_flag or r.app in FREEZE],
                    "breaches": breaches,
                },
                indent=2,
            )
        )
        return 0 if not breaches else 1
    print(format_status())
    return 0 if not breaches else 1


if __name__ == "__main__":
    raise SystemExit(main())
