#!/usr/bin/env python3
"""Generate docs/reference/ux-catalogue.md from the component_showcase ux_catalogue workspace.

Thin CLI over ``dazzle.testing.ux_catalogue.generate_catalogue_markdown`` (the logic lives
there so it's importable + unit-tested). ``--mode=ci`` fails when the committed page is stale
(mirrors scripts/gen_reference_docs.py), so the docs workflow can gate freshness.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dazzle.testing.ux_catalogue import OUT_PATH, generate_catalogue_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["write", "ci"], default="write")
    args = ap.parse_args()

    md = generate_catalogue_markdown()
    if args.mode == "ci":
        current = OUT_PATH.read_text() if OUT_PATH.exists() else ""
        if current != md:
            print(
                "docs/reference/ux-catalogue.md is stale — run: python scripts/gen_ux_catalogue.py",
                file=sys.stderr,
            )
            return 1
        print("ux-catalogue.md is current")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(md)
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
