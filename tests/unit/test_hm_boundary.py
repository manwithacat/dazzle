"""Dazzle-side HM boundary gates (Phase 3 of the boundary design,
docs/superpowers/specs/2026-07-03-hm-boundary-and-wcag-gate-design.md).

Dazzle is DOWNSTREAM of the HaTchi-MaXchi package: it may consume the
package only through sanctioned seams. Two invariants:

1. Every reference to the package from Dazzle code sits in the
   sanctioned-seams allowlist — no new back-channel reads appear.
2. The two build lists (dev concat + dist build) reference the SAME set
   of package CSS files. Drift between them means the dev bundle and
   the shipped bundle silently diverge.

(The mirror gate — HM never imports dazzle.* — lives in the package
itself: packages/hatchi-maxchi/tests/test_boundary.py, and runs in the
standalone repo's CI too.)
"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]

# Sanctioned seams. Additions here need a rationale comment — prefer
# consuming the package's published artifacts (dist/, icons registry)
# over reaching into its internals.
SANCTIONED = {
    # build seams: assemble the CSS/JS bundles from package sources
    # (Phase 2 narrows these to dist/ consumption).
    "src/dazzle/page/runtime/css_loader.py",
    "scripts/build_dist.py",
    # vendored icons: the generated copy + the docstring pointer to the
    # generator (drift-gated by test_icon_registry_drift.py).
    "src/dazzle/render/fragment/icon_registry.py",
    "src/dazzle/render/fragment/icon_html.py",
    # UX catalogue reads token/badge CSS to document them.
    "src/dazzle/testing/ux_catalogue.py",
}


def test_package_references_confined_to_sanctioned_seams() -> None:
    offenders = []
    for root in ("src/dazzle", "scripts"):
        for py in (REPO / root).rglob("*.py"):
            rel = str(py.relative_to(REPO))
            if rel in SANCTIONED:
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if "hatchi-maxchi" in text or "hatchi_maxchi" in text:
                offenders.append(rel)
    assert not offenders, (
        f"unsanctioned references to the HM package: {offenders}. "
        "Consume its published artifacts through an existing seam (or add "
        "the file to SANCTIONED with a rationale)."
    )


def _hm_entries_from_css_loader() -> set[str]:
    from dazzle.page.runtime.css_loader import CSS_SOURCE_FILES

    return {rel.removeprefix("@hm:") for _, rel in CSS_SOURCE_FILES if rel.startswith("@hm:")}


def _hm_entries_from_build_dist() -> set[str]:
    spec = importlib.util.spec_from_file_location("build_dist", REPO / "scripts" / "build_dist.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hm_root = Path(mod.HM)
    return {
        str(path.relative_to(hm_root)).replace("\\", "/")
        for _, path in mod.CSS_SOURCES
        if hm_root in path.parents or path == hm_root
    }


def test_build_lists_reference_the_same_package_files() -> None:
    dev = _hm_entries_from_css_loader()
    dist = _hm_entries_from_build_dist()
    assert dev == dist, (
        "css_loader @hm: entries and build_dist HM entries drifted — the dev "
        f"bundle and dist bundle would diverge. dev-only: {sorted(dev - dist)}, "
        f"dist-only: {sorted(dist - dev)}"
    )
    assert dev == {"dist/hatchi-maxchi.css"}, (
        "Phase 2 invariant: Dazzle consumes ONLY the published dist artifact — "
        f"found {sorted(dev)}. Per-source @hm: reads reopen the internals seam."
    )


def test_hm_paths_in_build_lists_exist() -> None:
    pkg = REPO / "packages" / "hatchi-maxchi"
    missing = sorted(rel for rel in _hm_entries_from_css_loader() if not (pkg / rel).is_file())
    assert not missing, f"@hm: entries point at missing package files: {missing}"


def _code_without_docs(path: Path) -> str:
    """Module source with docstrings and # comments stripped — what's left
    is executable code."""
    import ast
    import io
    import tokenize

    text = path.read_text(encoding="utf-8")
    doc_strings: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                doc_strings.add(doc)
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.string.strip("rbuRBU").strip("\"'") in doc_strings:
            continue
        out.append(tok.string)
    return " ".join(out)


def test_icon_seam_is_comment_only() -> None:
    """icon_html.py / icon_registry.py may MENTION the package (provenance
    docstrings/comments) but must not read from it at runtime — the vendored
    copy is the runtime artifact."""
    for rel in (
        "src/dazzle/render/fragment/icon_html.py",
        "src/dazzle/render/fragment/icon_registry.py",
    ):
        code = _code_without_docs(REPO / rel)
        assert "hatchi" not in code, (
            f"{rel} references the package in executable code (not just "
            "provenance comments) — runtime must use the vendored copy"
        )
