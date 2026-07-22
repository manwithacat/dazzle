#!/usr/bin/env python3
"""CLI wrapper for fleet L2.5 smoke dig (see dazzle.qa.smoke_dig)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))


def main(argv: list[str] | None = None) -> int:
    from dazzle.qa.smoke_dig import dig_cycle

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--app", "-a", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--once", action="store_true", default=True)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--max-clicks", type=int, default=12)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--fail-on-product", action="store_true")
    p.add_argument("--no-coverage", action="store_true")
    args = p.parse_args(argv)
    results = dig_cycle(
        app=args.app,
        all_apps=args.all,
        seed=args.seed,
        max_clicks=args.max_clicks,
        headless=not args.headed,
        fail_on_product=args.fail_on_product,
        run_coverage=not args.no_coverage,
    )
    n_fail = sum(1 for r in results if not r.ok)
    return 1 if args.fail_on_product and n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
