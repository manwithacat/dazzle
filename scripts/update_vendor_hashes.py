"""Rebuild the vendor hash manifest from on-disk files.

Use this when you've deliberately replaced a vendored file by hand
(flatpickr, pdfjs, etc.) and need the drift gate to
accept the new state. Auto-updated files (htmx core + 4 extensions,
idiomorph, lucide) get their manifest entries refreshed by
``scripts/update_vendors.py`` and don't need this.

Usage:

    python scripts/update_vendor_hashes.py             # rewrite, show diff
    python scripts/update_vendor_hashes.py --check     # dry run, exit 1 if drift
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable when run directly (python scripts/...).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendor_manifest import (  # noqa: E402
    MANIFEST_PATH,
    compute_current_hashes,
    load_manifest,
    write_manifest,
)


def main() -> int:
    check_only = "--check" in sys.argv

    on_disk = compute_current_hashes()
    pinned = load_manifest()

    added = sorted(set(on_disk) - set(pinned))
    removed = sorted(set(pinned) - set(on_disk))
    changed = sorted(f for f in on_disk if f in pinned and on_disk[f] != pinned[f])

    if not (added or removed or changed):
        print("Vendor manifest is up to date.")
        return 0

    for f in added:
        print(f"+ {f}  {on_disk[f]}")
    for f in removed:
        print(f"- {f}  (was {pinned[f]})")
    for f in changed:
        print(f"~ {f}")
        print(f"    was: {pinned[f]}")
        print(f"    now: {on_disk[f]}")

    if check_only:
        print(
            f"\n{len(added) + len(removed) + len(changed)} drift(s) detected. "
            "Re-run without --check to rewrite the manifest.",
            file=sys.stderr,
        )
        return 1

    write_manifest(on_disk)
    print(f"\nWrote {MANIFEST_PATH.relative_to(MANIFEST_PATH.parent.parent)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
