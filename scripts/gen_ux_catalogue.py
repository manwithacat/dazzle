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

from dazzle.testing.ux_catalogue import (  # noqa: E402
    CSS_OUT_PATH,
    OUT_PATH,
    generate_catalogue_css,
    generate_catalogue_markdown,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["write", "ci"], default="write")
    args = ap.parse_args()

    outputs = [(OUT_PATH, generate_catalogue_markdown()), (CSS_OUT_PATH, generate_catalogue_css())]

    if args.mode == "ci":
        stale = [p for p, content in outputs if (p.read_text() if p.exists() else "") != content]
        if stale:
            names = ", ".join(
                str(p.relative_to(Path(__file__).resolve().parents[1])) for p in stale
            )
            print(
                f"stale: {names} — run: python scripts/gen_ux_catalogue.py",
                file=sys.stderr,
            )
            return 1
        print("ux catalogue is current")
        return 0

    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
