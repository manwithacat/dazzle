"""Served bundles must not reference missing source maps (#860).

``vendor/`` stores published npm/CDN bytes, which often end with
``//# sourceMappingURL=....map``. We do not ship those ``.map`` files.
``scripts/build_dist.py`` strips the comment when assembling ``dist/``,
which is what the browser loads (``/static/dist/dazzle*.min.js``).

This gate watches the served tree, not the ingest tree — so a vendor
update can keep the published SHA-256.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
DIST_DIR = REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "dist"
VENDOR_DIR = REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "vendor"


def _unshipped_map_refs(root: Path) -> list[tuple[str, str]]:
    offending: list[tuple[str, str]] = []
    if not root.exists():
        return offending
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".css", ".mjs"}:
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            continue
        if "sourceMappingURL" not in content:
            continue
        marker_start = content.find("sourceMappingURL=")
        marker_tail = content[marker_start + len("sourceMappingURL=") :]
        map_ref = ""
        for ch in marker_tail:
            if ch in (" ", "\n", "*", ")"):
                break
            map_ref += ch
        if not map_ref:
            continue
        map_path = path.parent / map_ref
        if not map_path.exists():
            offending.append((str(path.relative_to(root)), map_ref))
    return offending


def test_dist_bundles_have_no_unshipped_sourcemaps() -> None:
    """Browsers load dist/; a leftover map comment is a DevTools 404."""
    assert DIST_DIR.is_dir(), "run scripts/build_dist.py"
    offending = _unshipped_map_refs(DIST_DIR)
    assert not offending, (
        "dist bundle(s) reference a source-map that isn't shipped:\n"
        + "\n".join(f"  {f} → {m}" for f, m in offending)
        + "\n\nStrip in scripts/build_dist.py (strip_sourcemap_text), "
        "not by rewriting vendor/ ingest bytes."
    )


def test_vendor_lucide_keeps_published_sourcemap_comment() -> None:
    """Ingest is byte-exact: lucide's UMD ships a sourceMappingURL line.

    If this fails, someone stripped vendor/lucide.min.js again and the
    committed hash will no longer match npm/jsdelivr.
    """
    lucide = VENDOR_DIR / "lucide.min.js"
    assert lucide.is_file()
    text = lucide.read_text()
    assert "sourceMappingURL=lucide.min.js.map" in text
    dist = DIST_DIR / "dazzle-icons.min.js"
    assert dist.is_file()
    assert "sourceMappingURL" not in dist.read_text()
