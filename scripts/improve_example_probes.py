#!/usr/bin/env python3
"""Unified example-app probe status for /improve OBSERVE (agent-first loop).

Runs the three machine-checkable maturity probes in one shot and prints
status lines the cycle log can paste. Exit 1 if **any** residual remains
(so loops keep firing until product + demo + journey are all clean).

```bash
python scripts/improve_example_probes.py --status
python scripts/improve_example_probes.py --next    # first residual across probes
python scripts/improve_example_probes.py --json
python scripts/improve_example_probes.py --strict
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", action="store_true", help="One-line suite (default)")
    ap.add_argument(
        "--next",
        action="store_true",
        help="Print first residual app across probes (probe preference: product, demo, journey)",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any residual")
    args = ap.parse_args(argv)

    # Always collect all three (cheap, deterministic).
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

    # Selection preference for --next: structural product → demo → journey
    # Strategy force names match improve/strategies/*.md + /improve ARGUMENTS.
    STRATEGY_FOR = {
        "product_maturity": "product_maturity",
        "demo_fleet": "demo_fleet",
        "journey_maturity": "journey_dogfood",
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

    if args.next:
        print(preferred_next or "")
        return 0 if preferred_next is None else 1

    if args.json:
        print(
            json.dumps(
                {
                    "probes": [
                        {
                            "name": name,
                            "status": line,
                            "next": nxt,
                            "residual": n,
                        }
                        for name, line, nxt, n in results
                    ],
                    "next": preferred_next,
                    "next_probe": preferred_probe,
                    "next_strategy": preferred_strategy,
                    "force": (f"example-apps {preferred_strategy}" if preferred_strategy else None),
                },
                indent=2,
            )
        )
    else:
        # Default: status lines for cycle log
        for _name, line, _nxt, _n in results:
            print(line)
        total = sum(max(n, 0) for _a, _b, _c, n in results)
        force = f" force=example-apps {preferred_strategy}" if preferred_strategy else ""
        print(f"example_probes residual_total={total} next={preferred_next or '-'}{force}")

    if args.strict:
        if any(n != 0 for _a, _b, _c, n in results):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
