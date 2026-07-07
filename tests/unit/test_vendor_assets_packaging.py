"""Every vendored asset in the hash manifest must be matched by the
package-data globs — the #1308 packaging bug class (hx-pdf P3 review):
a repo checkout serves any file from source, so CI and all quality
gates are structurally blind to wheel/sdist exclusions. The vendored
PDF.js `.mjs` files were invisible to `*.js`/`*.css` globs, which would
have 404'd every pip-installed viewer.
"""

import json
import re
from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "scripts" / "vendor_hashes.json"
STATIC_REL = "static/vendor"


def _package_data_globs() -> list[str]:
    """Extract the dazzle.page.runtime.static package-data globs."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'"dazzle\.page\.runtime\.static"\s*=\s*\[([^\]]*)\]', text)
    assert m, "package-data key for dazzle.page.runtime.static missing"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_every_vendored_asset_is_packaged() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    globs = _package_data_globs()
    missing = []
    for rel in manifest["files"]:
        path = f"vendor/{rel}"
        if not any(fnmatch(path, g) for g in globs):
            missing.append(rel)
    assert not missing, (
        "vendored assets excluded from the wheel (extend the package-data "
        "globs in pyproject.toml AND MANIFEST.in):\n  " + "\n  ".join(missing)
    )


def test_manifest_extensions_are_in_manifest_in() -> None:
    """MANIFEST.in (the sdist side) must cover every vendored extension."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    exts = {Path(rel).suffix for rel in manifest["files"]}
    manifest_in = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    line = next(
        (ln for ln in manifest_in.splitlines() if "page/runtime/static" in ln),
        "",
    )
    missing = sorted(e for e in exts if f"*{e}" not in line)
    assert not missing, f"MANIFEST.in static line missing extensions: {missing}"
