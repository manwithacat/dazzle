#!/usr/bin/env python3
"""Run the local Dazzle example eval hub.

Usage (from monorepo root)::

    .venv/bin/python scripts/example_hub/server.py
    .venv/bin/python scripts/example_hub/server.py --port 9080 --showcase-only
    .venv/bin/python scripts/example_hub/server.py --start-all

Hub:  http://dazzle.local:9080/   (after DNS)
Apps: http://simple_task.dazzle.local:9080/
Fallback without DNS: http://127.0.0.1:9080/

See docs/superpowers/specs/2026-07-21-example-eval-hub-design.md
and scripts/example_hub/README.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow `python scripts/example_hub/server.py` imports
_HUB_DIR = Path(__file__).resolve().parent
if str(_HUB_DIR) not in sys.path:
    sys.path.insert(0, str(_HUB_DIR))

from app import build_default  # noqa: E402

HUB_DOMAIN = "dazzle.local"
DEFAULT_HUB_PORT = 9080
DEFAULT_BACKEND_BASE = 9100


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=DEFAULT_HUB_PORT, help="Hub listen port")
    ap.add_argument("--host", default="127.0.0.1", help="Hub bind host")
    ap.add_argument(
        "--base-backend-port",
        type=int,
        default=DEFAULT_BACKEND_BASE,
        help="First port for example backends (stable index offset)",
    )
    ap.add_argument(
        "--showcase-only",
        action="store_true",
        help="Only register showcase fleet apps (demo_fleet / story_walk set)",
    )
    ap.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Do not spawn dazzle serve on first request",
    )
    ap.add_argument(
        "--start-all",
        action="store_true",
        help="Start every registered example before accepting traffic",
    )
    ap.add_argument(
        "--no-test-mode",
        action="store_true",
        help="Pass --no-test-mode to child dazzle serve processes",
    )
    args = ap.parse_args(argv)

    starlette_app, apps, supervisor = build_default(
        showcase_only=args.showcase_only,
        hub_port=args.port,
        backend_base=args.base_backend_port,
        auto_start=not args.no_auto_start,
        test_mode=not args.no_test_mode,
    )
    supervisor.test_mode = not args.no_test_mode

    print(f"Eval hub:  http://{HUB_DOMAIN}:{args.port}/")
    print(f"           http://127.0.0.1:{args.port}/  (no DNS)")
    print(f"Apps ({len(apps)}):")
    for a in apps:
        print(f"  http://{a.host}:{args.port}/  →  127.0.0.1:{a.port}  ({a.path.name})")
    print("State: .dazzle/eval-hub/")
    print("DNS:   see scripts/example_hub/README.md")

    if args.start_all:
        print("Starting all backends…")
        for st in supervisor.start_all(apps):
            print(f"  {st.app}: port={st.port} pid={st.pid}")

    try:
        import uvicorn
    except ImportError:
        print("uvicorn required: pip install uvicorn", file=sys.stderr)
        return 1

    uvicorn.run(starlette_app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
