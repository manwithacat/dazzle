#!/usr/bin/env python3
"""HM gallery interaction probes — deterministic UX contracts for Hyperparts.

Autonomous improve of HaTchi-MaXchi needs more than static screenshots:
many real gallery bugs are **interaction** defects (e.g. menubar: open Edit
does not close File). This tool is the machine half of that loop:

1. **Catalog** — declarative probes keyed by stem + claim
2. **Discover** — static scan for multi-``<details>`` roots that need exclusive-open
3. **Run** — Playwright against local ``site/`` (or a base URL)
4. **Report** — JSON findings agents / improve can drain
5. **Observe** — map a human observation card onto a probe (or FAIL with
   ``NO_PROBE`` so we know what to author next)

Does **not** call metered vision APIs. Cognitive review of FAIL screenshots
is optional host-Read (subscription), same policy as ``hm_visual_smoke``.

Usage (monorepo root or package)::

    python packages/hatchi-maxchi/tools/gallery_probes.py --list
    python packages/hatchi-maxchi/tools/gallery_probes.py --discover
    python packages/hatchi-maxchi/tools/gallery_probes.py --run
    python packages/hatchi-maxchi/tools/gallery_probes.py --run --stem menubar
    python packages/hatchi-maxchi/tools/gallery_probes.py --run --json
    python packages/hatchi-maxchi/tools/gallery_probes.py \\
        --validate-observation '{"stem":"menubar","claim":"exclusive open"}'

Exit codes: 0 all PASS/SKIP; 1 any FAIL; 2 harness ERROR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
SITE = PKG / "site"
DEFAULT_OUT = PKG.parents[1] / ".dazzle" / "hm-gallery-probes"  # monorepo .dazzle/
if not (PKG.parents[1] / "src" / "dazzle").is_dir():
    DEFAULT_OUT = PKG / ".dazzle" / "hm-gallery-probes"

SCHEMA = "hm.gallery_probes.v1"


# ── Catalog ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Probe:
    """One interaction contract for a gallery Hyperpart."""

    id: str
    stem: str
    page: str  # path under site/, e.g. hyperparts/menubar.html
    category: str  # interaction | layout | a11y | …
    severity: str  # blocker | high | medium | low
    claim: str
    kind: str  # runner dispatch key
    params: dict[str, Any] = field(default_factory=dict)
    fix_surface: str = "controller"  # controller | css | partial | gallery-only | contract
    # exclusive = only one open; multi_open = intentional multi-expand (tree)
    intent: str = "exclusive"


# Built-in probes. Author more here (or later: probes/*.toml discovery).
PROBES: tuple[Probe, ...] = (
    Probe(
        id="menubar.exclusive_open",
        stem="menubar",
        page="hyperparts/menubar.html",
        category="interaction",
        severity="high",
        claim=(
            "Opening a second menubar item closes the previously open item "
            "(exclusive open — File then Edit leaves only Edit open)"
        ),
        kind="exclusive_details_open",
        params={
            "root": "[data-dz-menubar], .dz-menubar, .menubar, [data-menubar]",
            "item": "details.dz-menubar__item, details.menubar__item",
            "trigger": "summary.dz-menubar__trigger, summary.menubar__trigger",
            "sequence": ["File", "Edit"],
            "expect_open_labels": ["Edit"],
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="navigation_menu.exclusive_open",
        stem="navigation-menu",
        page="hyperparts/navigation-menu.html",
        category="interaction",
        severity="high",
        claim=(
            "Opening a second navigation-menu panel closes the previously open "
            "panel (exclusive open — Product then Resources leaves only Resources open)"
        ),
        kind="exclusive_details_open",
        params={
            "root": (
                "[data-dz-navigation-menu], .dz-navigation-menu, "
                ".navigation-menu, [data-navigation-menu]"
            ),
            # bare <details> under each nav item (gallery partial has no item class)
            "item": (
                "[data-dz-navigation-menu] details, .dz-navigation-menu details, "
                ".navigation-menu details, [data-navigation-menu] details"
            ),
            "trigger": ("summary.dz-navigation-menu__trigger, summary.navigation-menu__trigger"),
            "sequence": ["Product", "Resources"],
            # summary text includes caret glyph — match by contains
            "expect_open_contains": ["Resources"],
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="accordion.exclusive_open",
        stem="accordion",
        page="hyperparts/accordion.html",
        category="interaction",
        severity="medium",
        claim=(
            "Accordion items sharing the HTML name= attribute stay exclusive "
            "(open second trigger leaves only that panel open — zero JS)"
        ),
        kind="exclusive_details_open",
        params={
            "root": ".dz-accordion, .accordion",
            "item": "details.dz-accordion__item, details.accordion__item",
            "trigger": "summary.dz-accordion__trigger, summary.accordion__trigger",
            "sequence": [
                "Do I need a client framework?",
                "Can two panels be open at once?",
            ],
            "expect_open_contains": ["Can two panels be open at once?"],
        },
        fix_surface="partial",  # native name= on details
        intent="exclusive",
    ),
    Probe(
        id="tree.multi_open",
        stem="tree",
        page="hyperparts/tree.html",
        category="interaction",
        severity="medium",
        claim=(
            "Tree nodes stay multi-open by design — expanding Platform then "
            "Design systems leaves both open (native details forest, no exclusive controller)"
        ),
        kind="multi_details_open",
        params={
            "root": "[data-dz-tree], .dz-tree, .tree, [data-tree]",
            # single class branch only — avoid OR multi-match double-counting open nodes
            "item": "details.dz-tree-node, details.tree-node",
            "trigger": "summary.dz-tree-summary, summary.tree-summary",
            # Engineering is open by default; open two siblings under it
            "sequence": ["Platform", "Design systems"],
            "expect_open_contains_all": ["Engineering", "Platform", "Design systems"],
            "expect_min_open": 3,
        },
        fix_surface="partial",
        intent="multi_open",
    ),
)


# ── Runner kinds ─────────────────────────────────────────────────────────


def _norm_label(text: str) -> str:
    return " ".join(text.split())


def _open_item_selector(item_sel: str) -> str:
    """Append ``[open]`` to each comma-separated selector branch.

    ``f\"{item_sel}[open]\"`` is wrong for multi-branch lists: only the last
    branch gets the attribute filter, so closed items still match earlier
    branches (false FAIL with open_count inflated).
    """
    parts = [p.strip() for p in item_sel.split(",") if p.strip()]
    return ", ".join(f"{p}[open]" for p in parts)


def _labels_match_expect(
    open_labels: list[str],
    *,
    expect_exact: list[str] | None,
    expect_contains: list[str] | None,
) -> bool:
    if expect_contains:
        if len(open_labels) != len(expect_contains):
            return False
        for got, needle in zip(open_labels, expect_contains, strict=True):
            if needle.lower() not in got.lower():
                return False
        return True
    expect = expect_exact or []
    return open_labels == expect


def _run_exclusive_details_open(page: Any, probe: Probe) -> dict[str, Any]:
    """Click triggers in sequence; assert only the last item stays open."""
    params = probe.params
    item_sel = params["item"]
    trigger_sel = params["trigger"]
    sequence: list[str] = list(params["sequence"])
    expect_exact: list[str] | None = (
        list(params["expect_open_labels"]) if "expect_open_labels" in params else None
    )
    expect_contains: list[str] | None = (
        list(params["expect_open_contains"]) if "expect_open_contains" in params else None
    )
    if expect_exact is None and expect_contains is None:
        expect_exact = sequence[-1:]

    root_loc = page.locator(params["root"])
    if root_loc.count() == 0:
        return {
            "verdict": "ERROR",
            "detail": f"root not found ({params['root']})",
        }

    n_items = page.locator(item_sel).count()
    if n_items < len(sequence):
        return {
            "verdict": "ERROR",
            "detail": f"need ≥{len(sequence)} items, found {n_items}",
        }

    for label in sequence:
        trig = page.locator(trigger_sel).filter(has_text=label).first
        if trig.count() == 0:
            return {"verdict": "ERROR", "detail": f"trigger not found: {label!r}"}
        trig.click()
        page.wait_for_timeout(80)

    open_items = page.locator(_open_item_selector(item_sel))
    open_count = open_items.count()
    # direct child summary only — nested forests (tree) have descendant summaries
    open_labels = [
        _norm_label(open_items.nth(i).locator(":scope > summary").inner_text())
        for i in range(open_count)
    ]

    if _labels_match_expect(
        open_labels, expect_exact=expect_exact, expect_contains=expect_contains
    ):
        return {
            "verdict": "PASS",
            "detail": f"open_labels={open_labels}",
            "open_count": open_count,
            "open_labels": open_labels,
        }
    expect_desc = expect_contains if expect_contains is not None else expect_exact
    return {
        "verdict": "FAIL",
        "detail": (
            f"expected open≈{expect_desc}, got open_count={open_count} open_labels={open_labels}"
        ),
        "open_count": open_count,
        "open_labels": open_labels,
        "dom_hint": item_sel,
    }


def _run_multi_details_open(page: Any, probe: Probe) -> dict[str, Any]:
    """Click triggers in sequence; assert multiple items stay open (tree forest)."""
    params = probe.params
    item_sel = params["item"]
    trigger_sel = params["trigger"]
    sequence: list[str] = list(params.get("sequence") or [])
    expect_all: list[str] = list(params.get("expect_open_contains_all") or sequence)
    min_open = int(params.get("expect_min_open") or len(expect_all) or 2)

    root_loc = page.locator(params["root"])
    if root_loc.count() == 0:
        return {"verdict": "ERROR", "detail": f"root not found ({params['root']})"}

    n_items = page.locator(item_sel).count()
    if n_items < min_open:
        return {
            "verdict": "ERROR",
            "detail": f"need ≥{min_open} items, found {n_items}",
        }

    for label in sequence:
        trig = page.locator(trigger_sel).filter(has_text=label).first
        if trig.count() == 0:
            return {"verdict": "ERROR", "detail": f"trigger not found: {label!r}"}
        # open if closed (click summary toggles)
        trig.click()
        page.wait_for_timeout(80)

    open_items = page.locator(_open_item_selector(item_sel))
    open_count = open_items.count()
    open_labels = [
        _norm_label(open_items.nth(i).locator(":scope > summary").inner_text())
        for i in range(open_count)
    ]
    joined = " ".join(open_labels).lower()
    missing = [n for n in expect_all if n.lower() not in joined]
    if open_count >= min_open and not missing:
        return {
            "verdict": "PASS",
            "detail": f"open_count={open_count} open_labels={open_labels}",
            "open_count": open_count,
            "open_labels": open_labels,
        }
    return {
        "verdict": "FAIL",
        "detail": (
            f"expected multi-open min={min_open} contains_all={expect_all}, "
            f"got open_count={open_count} open_labels={open_labels} missing={missing}"
        ),
        "open_count": open_count,
        "open_labels": open_labels,
        "dom_hint": item_sel,
    }


KIND_RUNNERS: dict[str, Callable[[Any, Probe], dict[str, Any]]] = {
    "exclusive_details_open": _run_exclusive_details_open,
    "multi_details_open": _run_multi_details_open,
}


# ── Discover (static) ────────────────────────────────────────────────────


_DETAILS_RE = re.compile(r"<details\b", re.I)
_NAME_ATTR_RE = re.compile(r"<details\b[^>]*\bname\s*=", re.I)


def discover_candidates() -> list[dict[str, Any]]:
    """Scan registry partials for multi-details roots needing an intent probe.

    Heuristic (cheap, no browser):
    - partial contains ≥2 ``<details``
    - not all details share a native ``name=`` (browser exclusivity → skip)
    - stem covered by **any** catalog probe (exclusive *or* multi_open intent)

    Uncovered stems need an authored probe that declares intent:
    exclusive (controller/name=) vs multi_open (tree forest).
    """
    sys.path.insert(0, str(SITE))
    try:
        from registry import HYPERPARTS  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return [{"verdict": "ERROR", "detail": f"cannot import registry: {exc}"}]

    probes_by_stem: dict[str, list[Probe]] = {}
    for p in PROBES:
        probes_by_stem.setdefault(p.stem, []).append(p)

    rows: list[dict[str, Any]] = []
    for h in HYPERPARTS:
        partial = getattr(h, "partial", "") or ""
        n = len(_DETAILS_RE.findall(partial))
        if n < 2:
            continue
        named = len(_NAME_ATTR_RE.findall(partial))
        native_exclusive = named >= 2 and named == n
        if native_exclusive:
            continue
        page = f"hyperparts/{h.id}.html"
        has_controller = bool(getattr(h, "controller", None))
        stem_probes = probes_by_stem.get(h.id, [])
        in_catalog = bool(stem_probes)
        intents = sorted({p.intent for p in stem_probes}) if stem_probes else []
        if in_catalog:
            rec = "catalog_ok_multi_open" if "multi_open" in intents else "catalog_ok"
        elif not has_controller:
            rec = "author_probe_declare_intent"  # exclusive controller vs multi_open partial
        else:
            rec = "author_probe_verify_controller"
        rows.append(
            {
                "stem": h.id,
                "page": page,
                "details_count": n,
                "named_details": named,
                "native_exclusive": native_exclusive,
                "has_controller": has_controller,
                "controller": getattr(h, "controller", None),
                "in_probe_catalog": in_catalog,
                "intents": intents,
                "probe_ids": [p.id for p in stem_probes],
                "recommendation": rec,
            }
        )
    rows.sort(key=lambda r: (r.get("in_probe_catalog", False), r.get("stem", "")))
    return rows


def discover_report() -> dict[str, Any]:
    candidates = discover_candidates()
    uncovered = [c for c in candidates if not c.get("in_probe_catalog")]
    return {
        "schema": SCHEMA,
        "mode": "discover",
        "run_at": datetime.now(UTC).isoformat(),
        "candidates": candidates,
        "summary": {
            "total_multi_details": len(candidates),
            "uncovered": len(uncovered),
            "catalog_covered": len(candidates) - len(uncovered),
        },
        "uncovered_stems": [c["stem"] for c in uncovered],
    }


# ── Execution ────────────────────────────────────────────────────────────


def _page_url(base: str | None, page: str) -> str:
    if base:
        b = base.rstrip("/")
        path = page if page.startswith("/") else f"/{page}"
        if b.startswith("file://"):
            root = b[len("file://") :]
            return Path(root + path).as_uri()
        return b + path
    return (SITE / page).resolve().as_uri()


def run_probes(
    *,
    probes: list[Probe],
    out: Path,
    base: str | None = None,
    screenshot_on_fail: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run probes; return a report dict (also written under *out*)."""
    pw_mod = __import__("playwright.sync_api", fromlist=["sync_playwright"])
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    with pw_mod.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        for probe in probes:
            url = _page_url(base, probe.page)
            row: dict[str, Any] = {
                "id": probe.id,
                "stem": probe.stem,
                "page": probe.page,
                "url": url,
                "category": probe.category,
                "severity": probe.severity,
                "claim": probe.claim,
                "kind": probe.kind,
                "fix_surface": probe.fix_surface,
            }
            runner = KIND_RUNNERS.get(probe.kind)
            if runner is None:
                row.update({"verdict": "ERROR", "detail": f"unknown kind {probe.kind!r}"})
                results.append(row)
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(150)
                outcome = runner(page, probe)
                row.update(outcome)
                if outcome.get("verdict") == "FAIL" and screenshot_on_fail:
                    png = out / f"{probe.id.replace('.', '_')}.png"
                    page.screenshot(path=str(png), full_page=False)
                    row["evidence_png"] = str(png.resolve())
            except Exception as exc:  # noqa: BLE001 — per-probe isolation
                row.update({"verdict": "ERROR", "detail": f"{type(exc).__name__}: {exc}"})
            results.append(row)
            if not quiet:
                print(f"{row.get('verdict', '?'):5} {probe.id}  {row.get('detail', '')[:100]}")
        browser.close()

    summary = {
        "pass": sum(1 for r in results if r.get("verdict") == "PASS"),
        "fail": sum(1 for r in results if r.get("verdict") == "FAIL"),
        "error": sum(1 for r in results if r.get("verdict") == "ERROR"),
        "skip": sum(1 for r in results if r.get("verdict") == "SKIP"),
        "total": len(results),
    }
    report = {
        "schema": SCHEMA,
        "run_at": datetime.now(UTC).isoformat(),
        "base": base or SITE.as_uri(),
        "site": str(SITE.resolve()),
        "results": results,
        "summary": summary,
    }
    report_path = out / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not quiet:
        print(f"wrote {report_path}  summary={summary}")
    return report


def emit_findings(report: dict[str, Any]) -> str:
    """Markdown HMC-style rows for FAIL probes (paste into improve-backlog)."""
    lines = [
        "<!-- gallery_probes findings — auto from report.json FAILs -->",
        "",
    ]
    fails = [r for r in report.get("results", []) if r.get("verdict") == "FAIL"]
    if not fails:
        lines.append("_No FAIL probes._")
        return "\n".join(lines) + "\n"
    for r in fails:
        pid = str(r.get("id", "unknown")).replace(".", "-")
        lines.extend(
            [
                f"### HMC-probe-{pid}",
                "- **status:** PENDING",
                f"- **stem:** `{r.get('stem')}`",
                f"- **probe:** `{r.get('id')}`",
                f"- **severity:** {r.get('severity')}",
                f"- **fix_surface:** {r.get('fix_surface')}",
                f"- **claim:** {r.get('claim')}",
                f"- **detail:** {r.get('detail')}",
                f"- **evidence:** `{r.get('evidence_png', '')}`",
                "- **playbook:** `improve/strategies/gallery_probes.md`",
                "",
            ]
        )
    return "\n".join(lines)


def match_observation(obs: dict[str, Any]) -> list[Probe]:
    """Map a human observation card to catalog probes (stem + claim keywords)."""
    stem_raw = (obs.get("stem") or obs.get("page") or "").strip().lower()
    stem = stem_raw.replace("_", "-")
    claim = (obs.get("claim") or obs.get("one_line") or obs.get("description") or "").lower()
    hits: list[Probe] = []
    claim_keys = (
        "exclusive",
        "close",
        "menu",
        "open",
        "file",
        "edit",
        "panel",
        "accordion",
        "product",
        "resources",
        "multi",
        "stay",
        "tree",
        "expand",
        "collapse",
        "branch",
        "sibling",
    )
    for p in PROBES:
        p_stem = p.stem.lower()
        stem_hit = bool(stem) and (
            p_stem == stem or stem in p.page or stem.replace("-", "") == p_stem.replace("-", "")
        )
        if stem and not stem_hit and stem not in p.claim.lower():
            continue
        if claim:
            if stem_hit or any(k in claim and k in p.claim.lower() for k in claim_keys):
                hits.append(p)
        elif stem_hit:
            hits.append(p)
    if stem and not hits:
        hits = [p for p in PROBES if p.stem.lower() == stem or stem in p.page]
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[Probe] = []
    for p in hits:
        if p.id not in seen:
            seen.add(p.id)
            out.append(p)
    return out


def validate_observation(obs: dict[str, Any], *, out: Path, base: str | None) -> dict[str, Any]:
    """Run matching probes for a human observation; return validation envelope."""
    hits = match_observation(obs)
    if not hits:
        return {
            "schema": SCHEMA,
            "observation": obs,
            "verdict": "NO_PROBE",
            "detail": (
                "No catalog probe matches this observation. Author a Probe in "
                "packages/hatchi-maxchi/tools/gallery_probes.py PROBES, then re-run. "
                "Hint: python …/gallery_probes.py --discover"
            ),
            "results": [],
        }
    report = run_probes(probes=hits, out=out, base=base, quiet=True)
    verdicts = {r.get("verdict") for r in report["results"]}
    if "FAIL" in verdicts:
        overall = "CONFIRMED"
    elif "ERROR" in verdicts:
        overall = "HARNESS_ERROR"
    elif verdicts <= {"PASS", "SKIP"}:
        overall = "NOT_REPRO"
    else:
        overall = "PARTIAL"
    return {
        "schema": SCHEMA,
        "observation": obs,
        "verdict": overall,
        "matched_probes": [p.id for p in hits],
        "report": report,
    }


def list_probes() -> None:
    print(f"{'id':36} {'stem':18} severity  claim")
    for p in PROBES:
        print(f"{p.id:36} {p.stem:18} {p.severity:8}  {p.claim[:70]}")


def write_catalog() -> Path:
    path = PKG / "GALLERY_PROBES.md"
    lines = [
        "# HM gallery interaction probes",
        "",
        "Auto-generated by `tools/gallery_probes.py --write-catalog`.",
        "Do not hand-edit — update `PROBES` in `tools/gallery_probes.py`.",
        "",
        "Run:",
        "",
        "```bash",
        "python packages/hatchi-maxchi/tools/gallery_probes.py --discover",
        "python packages/hatchi-maxchi/tools/gallery_probes.py --run",
        "python scripts/hm_gallery_probes.py --run   # monorepo entrypoint",
        "```",
        "",
        "| id | stem | intent | severity | fix_surface | claim |",
        "|----|------|--------|----------|-------------|-------|",
    ]
    for p in PROBES:
        claim = p.claim.replace("|", "\\|")
        lines.append(
            f"| `{p.id}` | `{p.stem}` | {p.intent} | {p.severity} | {p.fix_surface} | {claim} |"
        )
    lines.extend(
        [
            "",
            "## Loop (autonomous improve)",
            "",
            "1. `--discover` → uncovered multi-details stems (must declare intent)",
            "2. Author `Probe` with `intent=exclusive|multi_open` + fix_surface",
            "3. `--run` → FAIL drains via `improve/strategies/gallery_probes.md`",
            "4. Human observation → `--validate-observation '{…}'`",
            "5. CI pin optional: `tests/test_behaviour.py` scenario for ship-grade contracts",
            "",
            "### Intent",
            "",
            "- **exclusive** — menubar / nav / accordion: only one panel open",
            "- **multi_open** — tree forests: expanding siblings must *not* close peers",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="List catalog probes")
    ap.add_argument(
        "--discover",
        action="store_true",
        help="Static scan for multi-details stems needing an intent probe (exclusive|multi_open)",
    )
    ap.add_argument("--run", action="store_true", help="Run probes")
    ap.add_argument("--stem", action="append", default=[], help="Filter by stem (repeatable)")
    ap.add_argument(
        "--id", action="append", default=[], dest="probe_ids", help="Filter by probe id"
    )
    ap.add_argument(
        "--base",
        default=None,
        help="Gallery base URL (default: local site/ file://). "
        "Example: file:///…/packages/hatchi-maxchi/site",
    )
    ap.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="Output directory for report/PNGs"
    )
    ap.add_argument("--json", action="store_true", help="Print full report JSON to stdout")
    ap.add_argument(
        "--emit-findings",
        action="store_true",
        help="After --run, print HMC-style markdown for FAIL rows",
    )
    ap.add_argument(
        "--validate-observation",
        default=None,
        metavar="JSON",
        help='Human observation card as JSON string, e.g. \'{"stem":"menubar","claim":"…"}\'',
    )
    ap.add_argument(
        "--write-catalog",
        action="store_true",
        help="Write packages/hatchi-maxchi/GALLERY_PROBES.md from PROBES",
    )
    args = ap.parse_args(argv)

    if args.list:
        list_probes()
        return 0

    if args.write_catalog:
        path = write_catalog()
        print(f"wrote {path}")
        return 0

    if args.discover:
        report = discover_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(
                f"multi-details candidates: {report['summary']['total_multi_details']}  "
                f"uncovered: {report['summary']['uncovered']}"
            )
            for c in report["candidates"]:
                flag = "CATALOG" if c.get("in_probe_catalog") else "NEED_PROBE"
                print(
                    f"  {flag:10} {c['stem']:24} details={c['details_count']}  "
                    f"ctrl={c.get('controller') or '—'}  → {c['recommendation']}"
                )
            if report["uncovered_stems"]:
                print("uncovered_stems:", ", ".join(report["uncovered_stems"]))
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "discover.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        # discover never fails the run — it is inventory
        return 0

    if args.validate_observation:
        obs = json.loads(args.validate_observation)
        envelope = validate_observation(obs, out=args.out / "observation", base=args.base)
        print(json.dumps(envelope, indent=2))
        if envelope["verdict"] == "CONFIRMED":
            return 1
        if envelope["verdict"] in {"HARNESS_ERROR", "NO_PROBE"}:
            return 2
        return 0

    if not args.run:
        ap.print_help()
        return 2

    probes = list(PROBES)
    if args.stem:
        stems = set(args.stem)
        probes = [p for p in probes if p.stem in stems]
    if args.probe_ids:
        ids = set(args.probe_ids)
        probes = [p for p in probes if p.id in ids]
    if not probes:
        print("no probes selected", file=sys.stderr)
        return 2

    report = run_probes(probes=probes, out=args.out, base=args.base)
    if args.emit_findings:
        findings = emit_findings(report)
        findings_path = args.out / "findings.md"
        findings_path.write_text(findings, encoding="utf-8")
        print(findings)
        print(f"wrote {findings_path}")
    if args.json:
        print(json.dumps(report, indent=2))
    if report["summary"]["error"]:
        return 2
    if report["summary"]["fail"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
