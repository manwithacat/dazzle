#!/usr/bin/env python3
"""Print /etc/hosts lines for dazzle.local + each example app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HUB_DIR = Path(__file__).resolve().parent
if str(_HUB_DIR) not in sys.path:
    sys.path.insert(0, str(_HUB_DIR))

from registry import discover_apps  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--showcase-only", action="store_true")
    ap.add_argument("--ip", default="127.0.0.1")
    args = ap.parse_args()
    domain = "dazzle.local"
    apps = discover_apps(showcase_only=args.showcase_only)
    print("# Dazzle eval hub — paste into /etc/hosts")
    print(f"{args.ip}  {domain} www.{domain} hub.{domain}")
    for a in apps:
        print(f"{args.ip}  {a.host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
