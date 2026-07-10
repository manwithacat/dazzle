#!/usr/bin/env python3
"""Generate docs/reference/hm-design-context.md from core.design_context.

Thin CLI over ``dazzle.core.design_context.render_markdown`` (the render logic lives
in the module so it is importable + unit-tested). ``--mode=ci`` fails when the committed
doc is stale, so the docs workflow / gate can enforce freshness.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dazzle.core.design_context import DOC_PATH, render_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["write", "ci"], default="write")
    args = ap.parse_args()

    # Exactly one trailing newline — matches the repo's end-of-file-fixer hook so
    # the generator and the hook never tug-of-war (same convention as docs_gen).
    content = render_markdown().rstrip("\n") + "\n"

    if args.mode == "ci":
        if not DOC_PATH.exists() or DOC_PATH.read_text(encoding="utf-8") != content:
            print(
                f"STALE: {DOC_PATH} is out of date — run: python scripts/gen_design_context.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {DOC_PATH} is current")
        return 0

    DOC_PATH.write_text(content, encoding="utf-8")
    print(f"WROTE: {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
