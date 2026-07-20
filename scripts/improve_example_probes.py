#!/usr/bin/env python3
"""Unified example-app probe status for /improve OBSERVE (agent-first loop).

Runs structural maturity probes, the felt product_quality bar
(persona-home seeds + empty-hero stills), **story_walk** residual
(landing stories ↔ scene walks), and **trial_verdict** residual
(last qa-trial recommend / missing panel). Exit 1 if **any** residual remains.

```bash
python scripts/improve_example_probes.py --status
python scripts/improve_example_probes.py --next    # first residual across probes
python scripts/improve_example_probes.py --json
python scripts/improve_example_probes.py --strict
# preferred agent surface:
#   dazzle demo quality -p examples
#   MCP product_quality(operation=score)
#   python scripts/story_walk_bar.py --status
```
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _product() -> tuple[str, str | None, int]:
    mod = _load("example_product_maturity", REPO / "scripts" / "example_product_maturity.py")
    rows = mod.scan()
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else None
    line = mod.format_status(rows)
    return line, nxt, len(residual)


def _warehouse_index_line() -> str:
    """One-line WI summary for quiet-fleet feature_creep (residual may already be 0)."""
    mod = _load("example_product_maturity", REPO / "scripts" / "example_product_maturity.py")
    rows = mod.scan()
    wi_mean = mod.fleet_wi_mean(rows)
    wi_next = mod.next_wi_app(rows)
    above = sum(1 for r in rows if r.wi > mod.WI_FLOOR)
    dens = 1 if mod.densify_allowed(rows) else 0
    orphans = sum(r.orphan_ops_desks for r in rows)
    smells = sum(r.scoreboard_smells for r in rows)
    return (
        f"warehouse_index apps={len(rows)} wi_fleet={wi_mean:.3f} "
        f"wi_floor={mod.WI_FLOOR:.2f} wi_next={wi_next.app if wi_next else '-'} "
        f"wi_primary={wi_next.wi_primary if wi_next else '-'} "
        f"above_floor={above}/{len(rows)} densify_allowed={dens} "
        f"orphan_ops={orphans} scoreboard_smells={smells}"
    )


def _demo() -> tuple[str, str | None, int]:
    mod = _load("demo_fleet_bar", REPO / "scripts" / "demo_fleet_bar.py")
    rows = [mod.score_app(a) for a in mod.SHOWCASE if (mod.EXAMPLES / a).is_dir()]
    residual = [r for r in rows if not r.ok]
    nxt = residual[0].app if residual else None
    line = mod.format_status(rows)
    return line, nxt, len(residual)


def _journey() -> tuple[str, str | None, int]:
    mod = _load("example_journey_maturity", REPO / "scripts" / "example_journey_maturity.py")
    if hasattr(mod, "scan"):
        rows = mod.scan()
    else:
        apps = sorted(
            p for p in (REPO / "examples").iterdir() if p.is_dir() and (p / "dazzle.toml").exists()
        )
        rows = [mod.score_app(p) for p in apps]
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else None
    line = mod.format_status(rows)
    return line, nxt, len(residual)


def _product_quality() -> tuple[list[str], str | None, int, str | None]:
    """Felt demo bar — persona homes + stills + probe aggregate (#1626)."""
    from dazzle.product_quality import score_project, score_status_lines

    report = score_project(REPO / "examples")
    lines = score_status_lines(report)
    # residual_total includes structural probes already counted above; use the
    # felt-only delta so status total isn't triple-counted.
    probe_res = sum(max(p.residual, 0) for p in report.probes)
    felt = max(report.residual_total - probe_res, 0)
    return lines, report.next, felt, report.force


def _story_walk() -> tuple[str, str | None, int]:
    """Landing stories without scene walks — agent interaction residual."""
    mod = _load("story_walk_bar", REPO / "scripts" / "story_walk_bar.py")
    rows = mod.scan()
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else None
    return mod.format_status(rows), nxt, len(residual)


def _trial_verdict() -> tuple[str, str | None, int]:
    """Last qa-trial recommend / missing panel → acceptance residual."""
    mod = _load("trial_verdict_bar", REPO / "scripts" / "trial_verdict_bar.py")
    rows = mod.scan()
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else None
    return mod.format_status(rows), nxt, len(residual)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", action="store_true", help="One-line suite (default)")
    ap.add_argument(
        "--next",
        action="store_true",
        help=(
            "Print first residual app (preference: product → demo → journey → "
            "felt → story_walk → trial_verdict)"
        ),
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any residual")
    args = ap.parse_args(argv)

    # Structural three + felt product_quality + story walks + trial verdicts.
    results: list[tuple[str, str, str | None, int]] = []
    for name, fn in (
        ("product_maturity", _product),
        ("demo_fleet", _demo),
        ("journey_maturity", _journey),
    ):
        try:
            line, nxt, n = fn()
            results.append((name, line, nxt, n))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"{name} error={type(exc).__name__}", None, -1))

    pq_lines: list[str] = []
    pq_force: str | None = None
    try:
        pq_lines, pq_next, pq_felt, pq_force = _product_quality()
        results.append(
            ("product_quality", pq_lines[-1] if pq_lines else "product_quality", pq_next, pq_felt)
        )
    except Exception as exc:  # noqa: BLE001
        results.append(("product_quality", f"product_quality error={type(exc).__name__}", None, -1))

    for name, fn in (
        ("story_walk", _story_walk),
        ("trial_verdict", _trial_verdict),
    ):
        try:
            line, nxt, n = fn()
            results.append((name, line, nxt, n))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"{name} error={type(exc).__name__}", None, -1))

    # Selection order: structure → demo → journey → felt stills → story walks → trials.
    STRATEGY_FOR = {
        "product_maturity": "product_maturity",
        "demo_fleet": "demo_fleet",
        "journey_maturity": "journey_dogfood",
        "product_quality": "demo_fleet",
        "story_walk": "story_walk",
        "trial_verdict": "agent_acceptance_panel",
    }
    preferred_next: str | None = None
    preferred_probe: str | None = None
    preferred_strategy: str | None = None
    for name, _line, nxt, n in results:
        if n and n > 0 and nxt:
            preferred_next = nxt
            preferred_probe = name
            preferred_strategy = STRATEGY_FOR.get(name, name)
            break
    if preferred_strategy is None and pq_force:
        # force like "example-apps demo_fleet"
        parts = pq_force.split()
        preferred_strategy = parts[-1] if parts else "demo_fleet"

    if args.next:
        print(preferred_next or "")
        return 0 if preferred_next is None else 1

    # Always emit WI line on --status / default / --json (continuous anti-warehouse).
    wi_line = ""
    try:
        wi_line = _warehouse_index_line()
    except Exception as exc:  # noqa: BLE001
        wi_line = f"warehouse_index error={type(exc).__name__}"

    if args.json:
        print(
            json.dumps(
                {
                    "warehouse_index": wi_line,
                    "probes": [
                        {
                            "name": name,
                            "status": line,
                            "next": nxt,
                            "residual": n,
                        }
                        for name, line, nxt, n in results
                    ],
                    "product_quality_lines": pq_lines,
                    "next": preferred_next,
                    "next_probe": preferred_probe,
                    "next_strategy": preferred_strategy,
                    "force": (f"example-apps {preferred_strategy}" if preferred_strategy else None),
                },
                indent=2,
            )
        )
    else:
        # structural three
        for _name, line, _nxt, _n in results[:3]:
            print(line)
        for line in pq_lines:
            if line not in {r[1] for r in results[:3]}:
                print(line)
        # story_walk + trial_verdict status lines
        for name, line, _nxt, _n in results:
            if name in {"story_walk", "trial_verdict"}:
                print(line)
        if wi_line:
            print(wi_line)
        total = sum(max(n, 0) for _a, _b, _c, n in results)
        force = f" force=example-apps {preferred_strategy}" if preferred_strategy else ""
        print(f"example_probes residual_total={total} next={preferred_next or '-'}{force}")

    if args.strict:
        if any(n != 0 for _a, _b, _c, n in results):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
