#!/usr/bin/env python3
"""Scaffold a new Hyperpart contract module (Phase B).

Usage (from monorepo root or package):

    python packages/hatchi-maxchi/tools/scaffold_contract.py button
    python packages/hatchi-maxchi/tools/scaffold_contract.py my_part --root '[data-dz-my-part]'

Creates ``contracts/<stem>.py`` if missing. Does not register dual-locks —
add a row to monorepo ``tests/unit/hm_contract_registry.py`` when emission
is stable (see contracts/AUTHORING.md).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
CONTRACTS = PKG / "contracts"


def _stem_ok(stem: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", stem))


def _class_name(stem: str) -> str:
    return "".join(p.capitalize() for p in stem.split("_")) + "Field"


def scaffold(stem: str, *, root: str) -> Path:
    if not _stem_ok(stem):
        raise SystemExit(f"invalid stem {stem!r} — use snake_case [a-z0-9_]")
    dest = CONTRACTS / f"{stem}.py"
    if dest.exists():
        raise SystemExit(f"already exists: {dest}")

    hyphen = stem.replace("_", "-")
    root_sel = root or f"[data-dz-{hyphen}]"
    class_name = _class_name(stem)

    if root_sel.startswith("[hx-"):
        attr_key = root_sel.strip("[]")
        node_attrs = f'attrs={{"{attr_key}": Present()}}'
        render_body = (
            f"    return (\n"
            f'        f\'<button type="button" {attr_key}="Are you sure?">'
            f"{{html.escape(field.name)}}</button>'\n"
            f"    )"
        )
    else:
        attr_key = f"data-dz-{hyphen}"
        node_attrs = f'attrs={{"{attr_key}": Present()}}'
        render_body = (
            f"    return (\n"
            f'        f\'<div class="dz-{hyphen}" {attr_key} '
            f'data-name="{{html.escape(field.name, quote=True)}}"></div>\'\n'
            f"    )"
        )

    text = f'''"""HYPERPART: {stem} — scaffolded contract (fill model + render + exemplars).

See contracts/AUTHORING.md. After emission is stable, dual-lock in monorepo
``tests/unit/hm_contract_registry.py`` and regenerate DUAL_LOCK_COVERAGE.md.
"""

from __future__ import annotations

import html

from pydantic import BaseModel

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="{stem}",
    root="{root_sel}",
    nodes=(
        Node(
            "{root_sel}",
            {node_attrs},
        ),
    ),
)


class {class_name}(BaseModel):
    """TODO: replace with the real ingestion shape."""

    name: str = "{stem}"


EXEMPLARS: list[{class_name}] = [
    {class_name}(),
]


def render(field: {class_name}) -> str:
    """Minimal conforming markup — expand to match gallery partial."""
{render_body}


__all__ = ["DOM_CONTRACT", "{class_name}", "EXEMPLARS", "render"]
'''
    dest.write_text(text, encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stem", help="snake_case part id (e.g. button, my_part)")
    ap.add_argument(
        "--root",
        default="",
        help="CSS selector for DOM root (default: [data-dz-<stem-with-hyphens>])",
    )
    args = ap.parse_args(argv)
    path = scaffold(args.stem, root=args.root)
    print(f"wrote {path}")
    print("Next:")
    print("  1. Fill model / exemplars / render to match gallery partial")
    print("  2. Add controller if needed (HYPERPART marker)")
    print("  3. Dual-lock: DOM_ONLY_CONTRACTS or CONTRACT_MODELS + fixture")
    print("  4. python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
