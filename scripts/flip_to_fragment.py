#!/usr/bin/env python3
"""Insert `render: fragment` after every flippable `mode:` declaration.

Idempotent: re-running on the same file is a no-op.

Scope: a "flippable" mode is one of list/view/create/edit. Other modes
(custom, dashboard, etc.) are skipped — the fragment-audit reports them
as blockers and they need adapter work first.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FLIPPABLE_MODES = ("list", "view", "create", "edit")


def flip_file(path: Path) -> int:
    """Insert `render: fragment` after every flippable mode line.

    Returns the number of insertions made. 0 means already fully flipped.
    """
    lines = path.read_text().splitlines(keepends=False)
    out: list[str] = []
    inserted = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        stripped = line.strip()
        if stripped.startswith("mode:"):
            mode_value = stripped.split(":", 1)[1].strip()
            if mode_value in _FLIPPABLE_MODES:
                indent = line[: len(line) - len(line.lstrip())]
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if next_line.strip() != "render: fragment":
                    out.append(f"{indent}render: fragment")
                    inserted += 1
        i += 1
    if inserted:
        original = path.read_text()
        suffix = "\n" if original.endswith("\n") else ""
        path.write_text("\n".join(out) + suffix)
    return inserted


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: flip_to_fragment.py <dsl-path> [<dsl-path>...]", file=sys.stderr)
        return 2
    total = 0
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"skip (not found): {path}", file=sys.stderr)
            continue
        n = flip_file(path)
        total += n
        print(f"{path}: {n} insertion(s)")
    print(f"total: {total} insertion(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
