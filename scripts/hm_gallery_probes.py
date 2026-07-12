#!/usr/bin/env python3
"""Monorepo entrypoint for HM gallery interaction probes.

Delegates to ``packages/hatchi-maxchi/tools/gallery_probes.py``.
See that module for full docs.

Examples::

    python scripts/hm_gallery_probes.py --list
    python scripts/hm_gallery_probes.py --discover
    python scripts/hm_gallery_probes.py --run
    python scripts/hm_gallery_probes.py --run --stem menubar --json
    python scripts/hm_gallery_probes.py --run --emit-findings
    python scripts/hm_gallery_probes.py --validate-observation '{"stem":"menubar","claim":"File stays open when Edit opens"}'
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

TOOL = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "hatchi-maxchi"
    / "tools"
    / "gallery_probes.py"
)


def main() -> int:
    # runpy keeps a single source of truth in the package tool
    sys.argv[0] = str(TOOL)
    runpy.run_path(str(TOOL), run_name="__main__")
    return 0


if __name__ == "__main__":
    # gallery_probes.main handles SystemExit via raise SystemExit in __main__
    # but run_path doesn't propagate exit codes from inside — call main() API
    sys.path.insert(0, str(TOOL.parent))
    from gallery_probes import main as gp_main

    raise SystemExit(gp_main())
