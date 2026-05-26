"""#1277 regression — vendored htmx extensions are v2-clean.

The htmx 1.x extension files (preserved at `bigskysoftware/htmx`'s
`dist/ext/` directory for backward-compat unpkg URLs) ship a runtime
guard that fires:

    console.warn("WARNING: You are using an htmx 1 extension with htmx <ver>...")

against any htmx 2.x core. `scripts/update_vendors.py` originally
fetched from that deprecated path; the fix (v0.78.11) repoints it at
`bigskysoftware/htmx-extensions` at `src/<name>/<name>.js`, which is
the canonical v2 source.

This test pins two invariants:
- No vendored extension file carries the v1-warning guard string.
- The built `dazzle.min.js` bundle is correspondingly clean.

Both are content-gate checks on the on-disk artifacts, so the test is
fast and doesn't need a JS runtime.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR = REPO_ROOT / "src" / "dazzle" / "ui" / "runtime" / "static" / "vendor"
DIST_BUNDLE = REPO_ROOT / "src" / "dazzle" / "ui" / "runtime" / "static" / "dist" / "dazzle.min.js"

# The exact warning string the deprecated v1 extensions emit. Matching
# the literal text rather than a regex keeps the gate narrow — any v2
# extension that legitimately references "htmx 1" for other reasons
# won't trip it as long as it doesn't reproduce this exact phrasing.
V1_WARNING_FRAGMENT = "htmx 1 extension with htmx"

UPDATED_EXTENSIONS = [
    "htmx-ext-json-enc.js",
    "htmx-ext-preload.js",
    "htmx-ext-response-targets.js",
    "htmx-ext-loading-states.js",
    "htmx-ext-sse.js",
]


@pytest.mark.parametrize("filename", UPDATED_EXTENSIONS)
def test_vendored_extension_has_no_v1_warning_1277(filename: str) -> None:
    """Each htmx extension fetched by update_vendors.py is sourced from
    the v2 repo (`bigskysoftware/htmx-extensions`) and must not embed
    the v1-warning guard."""
    path = VENDOR / filename
    assert path.exists(), f"Vendored extension {filename} missing from {VENDOR}"
    text = path.read_text(encoding="utf-8")
    assert V1_WARNING_FRAGMENT not in text, (
        f"{filename} still contains the htmx-1 warning fragment "
        f"({V1_WARNING_FRAGMENT!r}). This means update_vendors.py "
        "fetched from the deprecated `bigskysoftware/htmx` "
        "`dist/ext/` path instead of `bigskysoftware/htmx-extensions` "
        "`src/<name>/<name>.js`. See #1277."
    )


def test_built_bundle_has_no_v1_warning_1277() -> None:
    """The built `dist/dazzle.min.js` is the concatenation of every
    file in `JS_SOURCES` (see scripts/build_dist.py); it must also be
    free of the htmx-1 warning."""
    if not DIST_BUNDLE.exists():
        pytest.skip("dist/dazzle.min.js not built — run scripts/build_dist.py")
    text = DIST_BUNDLE.read_text(encoding="utf-8")
    assert V1_WARNING_FRAGMENT not in text, (
        "Built bundle dist/dazzle.min.js carries the htmx-1 warning. "
        "Run scripts/update_vendors.py htmx + scripts/build_dist.py to "
        "rebuild from v2 sources. See #1277."
    )
