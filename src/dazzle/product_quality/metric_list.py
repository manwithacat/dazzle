"""Metric vs sibling-list residual — F10 / #1632 / metric_current_user_lie.

When a persona home workspace has ``display: metrics`` aggregates that bind
``current_user``, and a sibling list/queue/kanban/timeline region for the same
persona has seed hits, product_quality flags residual. Agents must not trust
KPI tiles over lists (aggregate materialization can disagree at runtime).

Static analysis only — does not execute the running app. Residual means
"trust order is lists/stills first; metrics last" when the footgun pattern
is present with seeded desks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from dazzle.product_quality.persona_homes import (
    _CURRENT_CONTEXT_RE,
    _CURRENT_USER_RE,
    _PLATFORM_WORKSPACES,
    _STATUS_RE,
    STABLE_PERSONA_USER_IDS,
    _collect_personas_and_workspaces,
    _count_seed_hits,
    _load_jsonl,
    _read_dsl,
    _seed_dir,
)

_DISPLAY_RE = re.compile(r"display:\s*(\w+)")
_SOURCE_RE = re.compile(r"source:\s*(\w+)")
_FILTER_RE = re.compile(r"filter:\s*(.+)")
_REGION_HEADER_RE = re.compile(r"^  (\w+):\s*$")
_AGG_CURRENT_USER_RE = re.compile(r"\bcurrent_user\b")
_COUNT_BIND_RE = re.compile(
    r"(assigned_to|assigned_to_id|created_by|submitted_by|reported_by_id|"
    r"owner|assigned_tester_id|tester_id|requester)\s*=\s*current_user",
    re.I,
)

_LIST_DISPLAYS = frozenset(
    {
        "list",
        "queue",
        "table",
        "kanban",
        "timeline",
        "cards",
        "grid",
        "board",
    }
)
_SKIP_REGION_NAMES = frozenset(
    {
        "access",
        "purpose",
        "stage",
        "as",
        "layout",
        "context_selector",
        "tones",
        "entries",
    }
)


@dataclass
class MetricListPair:
    persona: str
    workspace: str
    metric_region: str
    list_region: str
    list_seed_hits: int
    residual: bool
    reason: str


@dataclass
class MetricListHome:
    persona: str
    default_workspace: str | None
    pairs: list[MetricListPair] = field(default_factory=list)

    @property
    def residual(self) -> bool:
        return any(p.residual for p in self.pairs)

    @property
    def residual_reasons(self) -> list[str]:
        return [f"{p.metric_region}/{p.list_region}:{p.reason}" for p in self.pairs if p.residual]


def _parse_regions_rich(body: str) -> list[dict[str, str]]:
    """Parse workspace regions with source, filter, display, and aggregate text."""
    out: list[dict[str, str]] = []
    lines = body.splitlines(keepends=True)
    i = 0
    n = len(lines)
    while i < n:
        m = _REGION_HEADER_RE.match(lines[i].rstrip("\n"))
        if not m:
            i += 1
            continue
        region = m.group(1)
        i += 1
        block_lines: list[str] = []
        while i < n:
            ln = lines[i]
            if ln.strip() == "":
                j = i + 1
                while j < n and lines[j].strip() == "":
                    j += 1
                if j < n and lines[j].startswith("    "):
                    block_lines.append(ln)
                    i += 1
                    continue
                break
            if ln.startswith("    "):
                block_lines.append(ln)
                i += 1
                continue
            break
        if region in _SKIP_REGION_NAMES:
            continue
        block = "".join(block_lines)
        sm = _SOURCE_RE.search(block)
        dm = _DISPLAY_RE.search(block)
        fm = _FILTER_RE.search(block)
        out.append(
            {
                "region": region,
                "source": sm.group(1) if sm else "",
                "display": dm.group(1) if dm else "",
                "filter": fm.group(1).strip() if fm else "",
                "block": block,
            }
        )
    return out


def _metrics_use_current_user(reg: dict[str, str]) -> bool:
    if reg.get("display") != "metrics":
        return False
    block = reg.get("block", "")
    if "aggregate:" not in block and "aggregate :" not in block:
        # still allow metrics without aggregate keyword if block has current_user
        return bool(_AGG_CURRENT_USER_RE.search(block))
    return bool(_AGG_CURRENT_USER_RE.search(block))


def _is_list_like(reg: dict[str, str]) -> bool:
    display = reg.get("display") or ""
    if display in _LIST_DISPLAYS:
        return True
    # Regions with a filter + source but no display still act as lists
    return bool(reg.get("source") and reg.get("filter") and display != "metrics")


def _list_seed_hits(
    reg: dict[str, str],
    *,
    uid: str | None,
    seed: Path | None,
) -> int:
    """Count seed rows for a list region when it binds current_user."""
    filter_text = reg.get("filter") or ""
    bind_m = (
        _CURRENT_USER_RE.search(filter_text)
        or _CURRENT_CONTEXT_RE.search(filter_text)
        or _COUNT_BIND_RE.search(filter_text)
    )
    if not bind_m or not uid or seed is None:
        return 0
    bind_field = bind_m.group(1)
    status_m = _STATUS_RE.search(filter_text)
    status = status_m.group(1) if status_m else None
    source = reg.get("source") or ""
    if not source:
        return 0
    rows = _load_jsonl(seed / f"{source}.jsonl")
    if not rows:
        return 0
    return _count_seed_hits(rows, bind_field=bind_field, user_id=uid, status=status)


def score_metric_list(
    app_dir: Path,
    *,
    min_list_hits: int = 1,
) -> list[MetricListHome]:
    """Score metric↔list current_user disagreement risk for one app.

    Residual when:
    - default workspace has a metrics region whose aggregates reference current_user
    - a sibling list-like region has seed hits ≥ min_list_hits for the persona
    """
    text = _read_dsl(app_dir)
    if not text.strip():
        return []

    personas, workspaces = _collect_personas_and_workspaces(text)
    seed = _seed_dir(app_dir)
    homes: list[MetricListHome] = []

    for pid, dws in personas:
        home = MetricListHome(persona=pid, default_workspace=dws)
        if not dws or dws in _PLATFORM_WORKSPACES or dws not in workspaces:
            homes.append(home)
            continue

        uid = STABLE_PERSONA_USER_IDS.get(pid)
        regions = _parse_regions_rich(workspaces[dws])
        metric_regs = [r for r in regions if _metrics_use_current_user(r)]
        list_regs = [r for r in regions if _is_list_like(r) and r not in metric_regs]

        if not metric_regs:
            homes.append(home)
            continue

        for mreg in metric_regs:
            for lreg in list_regs:
                hits = _list_seed_hits(lreg, uid=uid, seed=seed)
                if hits < min_list_hits:
                    continue
                home.pairs.append(
                    MetricListPair(
                        persona=pid,
                        workspace=dws,
                        metric_region=mreg["region"],
                        list_region=lreg["region"],
                        list_seed_hits=hits,
                        residual=True,
                        reason=(
                            f"metric_current_user_lie: metrics use current_user while "
                            f"sibling list {lreg['region']} has seed_hits={hits} "
                            f"(trust lists/stills over KPI tiles; F10/#1632)"
                        ),
                    )
                )
        homes.append(home)
    return homes
