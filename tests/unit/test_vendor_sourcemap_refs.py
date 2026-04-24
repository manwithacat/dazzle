"""Regression test: vendored libraries must not reference missing source maps (#860).

Minified vendor bundles shipped with Dazzle intentionally omit the `.map`
companion files. If the minified source carries a trailing
`//# sourceMappingURL=...` or `/*# sourceMappingURL=... */` comment, any
browser with DevTools open fires a 404 for the map — noisy in logs and
distracting for developers.

Fix: strip those comments from the vendored source. This test catches
the regression when a vendor file is re-fetched from upstream without
running the strip step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

VENDOR_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "runtime" / "static" / "vendor"
)

# Every vendored file whose map we know is not shipped. Add to this list
# when pulling in a new vendor that strip_sourcemap would have touched.
_FILES_WITHOUT_SHIPPED_MAPS = [
    "tom-select.min.js",
    "tom-select.css",
    "quill.min.js",
    "quill.snow.css",
    "pickr.min.js",
]


@pytest.mark.parametrize("name", _FILES_WITHOUT_SHIPPED_MAPS)
def test_vendor_file_has_no_sourcemap_reference(name: str) -> None:
    path = VENDOR_DIR / name
    if not path.exists():
        pytest.skip(f"{name} no longer vendored — update the list.")

    content = path.read_text()
    assert "sourceMappingURL" not in content, (
        f"{name} references a source-map file that is not shipped in "
        f"the vendor directory — browsers will fire 404s for it. "
        f"Strip the trailing `sourceMappingURL=` comment (or commit the "
        f"matching .map file alongside the bundle)."
    )


def test_no_new_vendor_files_with_unshipped_maps() -> None:
    """Scan the whole vendor dir for any minified file that still
    references a missing .map companion."""
    offending: list[tuple[str, str]] = []
    for path in VENDOR_DIR.iterdir():
        if not path.is_file():
            continue
        if path.suffix not in {".js", ".css"}:
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            continue
        if "sourceMappingURL" not in content:
            continue
        # Extract the referenced map name and check whether it's shipped.
        marker_start = content.find("sourceMappingURL=")
        marker_tail = content[marker_start + len("sourceMappingURL=") :]
        map_ref = ""
        for ch in marker_tail:
            if ch in (" ", "\n", "*", ")"):
                break
            map_ref += ch
        if not map_ref:
            continue
        map_path = VENDOR_DIR / map_ref
        if not map_path.exists():
            offending.append((path.name, map_ref))

    assert not offending, (
        "Vendor file(s) reference a source-map that isn't shipped:\n"
        + "\n".join(f"  {f} → {m}" for f, m in offending)
        + "\n\nEither strip the sourceMappingURL comment or commit the "
        "matching .map alongside the bundle."
    )
