#!/usr/bin/env python3
"""Print a Hyperpart's full anatomy — every code item that makes up the unit.

A Hyperpart is physically distributed by the build (markup + contract in
the registry, CSS concatenated in layer order across component files, JS
bundled from controllers/), but it is logically ONE unit. This assembles
the scattered parts back into one view, for a human or an agent about to
work on it:

    $ python tools/hyperpart.py command
    Hyperpart: command  (Command palette)
      partial     site/registry.py           (inline markup)
      exchanges   GET /app/command
      styles      components/hm-core.css:256  (HYPERPART: command marker)
      controller  controllers/dz-command.js
      mock        /mock/command

`styles` are discovered from `HYPERPART: <id>` marker comments at the code
site (the marker is the source of truth — a component's CSS is genuinely
many-to-many across files). `controller`/`mock` come from the registry
manifest. With no id, lists all Hyperparts and their part counts.
"""

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "site"))

from registry import HYPERPARTS  # noqa: E402

_MARKER_RE = re.compile(r"HYPERPART:\s*([a-z0-9-]+)")

# Where markers may live (CSS blocks + controllers).
_MARKER_ROOTS = [PKG / "components", PKG / "base", PKG / "controllers"]


def marker_sites() -> dict[str, list[str]]:
    """id -> ['relpath:line', …] for every HYPERPART marker in the tree."""
    sites: dict[str, list[str]] = {}
    for root in _MARKER_ROOTS:
        for f in sorted(root.rglob("*")):
            if f.suffix not in (".css", ".js") or not f.is_file():
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                m = _MARKER_RE.search(line)
                if m:
                    sites.setdefault(m.group(1), []).append(f"{f.relative_to(PKG)}:{i}")
    return sites


def anatomy(hp_id: str) -> dict:
    hp = next((h for h in HYPERPARTS if h.id == hp_id), None)
    if hp is None:
        raise SystemExit(f"no Hyperpart {hp_id!r} (see: python tools/hyperpart.py)")
    sites = marker_sites().get(hp_id, [])
    return {
        "id": hp.id,
        "title": hp.title,
        "partial": "site/registry.py (inline markup)",
        "exchanges": [f"{e.method} {e.endpoint}" for e in hp.exchanges],
        "styles": [s for s in sites if ".css" in s],
        "controller": hp.controller,
        "mock": hp.mock,
    }


def _print(hp_id: str) -> None:
    a = anatomy(hp_id)
    print(f"Hyperpart: {a['id']}  ({a['title']})")
    print(f"  partial     {a['partial']}")
    print(f"  exchanges   {', '.join(a['exchanges']) or '—'}")
    print(f"  styles      {', '.join(a['styles']) or '(no HYPERPART marker yet)'}")
    print(f"  controller  {a['controller'] or '—'}")
    print(f"  mock        {a['mock'] or '—'}")


def main() -> int:
    if len(sys.argv) < 2:
        sites = marker_sites()
        for hp in HYPERPARTS:
            parts = sum(
                [
                    bool(hp.exchanges),
                    bool(sites.get(hp.id)),
                    bool(hp.controller),
                    bool(hp.mock),
                ]
            )
            print(f"  {hp.id:14} +{parts} parts beyond markup")
        return 0
    _print(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
