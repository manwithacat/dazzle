"""
Public-helpers API surface snapshot — cycle 4 of #961.

Walks the top-level package `__init__.py` of each public package
(`dazzle`, `dazzle_back`, `dazzle_ui`) and snapshots the resolved public
attributes — explicit `__all__` plus lazy `_LOADERS`-style re-exports.

Each resolved attribute is rendered with a category + signature so renames,
removals, and signature changes all fire the drift gate.
"""

import inspect
import types

from .dsl_constructs import REPO_ROOT, _format_annotation

BASELINE_PATH = REPO_ROOT / "docs" / "api-surface" / "public-helpers.txt"


def _load_packages() -> list[tuple[str, types.ModuleType]]:
    """Eagerly import the three public packages by literal reference.

    Static imports satisfy SAST tools (no dynamic module name passed to
    `importlib.import_module`); the trade-off is that adding a new
    public package to the snapshot is a code change, not a config change.
    """
    import dazzle
    import dazzle_back
    import dazzle_ui

    return [
        ("dazzle", dazzle),
        ("dazzle_back", dazzle_back),
        ("dazzle_ui", dazzle_ui),
    ]


PACKAGE_NAMES = ["dazzle", "dazzle_back", "dazzle_ui"]


def _public_names(module: types.ModuleType) -> list[str]:
    """Return the deliberately-public names exported by a module.

    Resolution order:
      1. `__all__` — if defined, that is the canonical list.
      2. `_LOADERS` — the lazy `__getattr__` convention used by dazzle_back.
      3. Otherwise: all module-level non-underscore attributes (a noisy
         fallback; only applied when both 1 and 2 are absent).
    """
    all_ = getattr(module, "__all__", None)
    if all_ is not None:
        return sorted(all_)
    loaders = getattr(module, "_LOADERS", None)
    if isinstance(loaders, dict):
        return sorted(loaders.keys())
    return sorted(name for name in vars(module) if not name.startswith("_"))


def _resolve(module: types.ModuleType, name: str) -> object:
    return getattr(module, name, None)


def _format_signature(obj: object) -> str:
    try:
        sig = inspect.signature(obj)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    return str(sig)


def _render_attr(name: str, obj: object) -> list[str]:
    if obj is None:
        return [f"  - {name}: MISSING"]

    if inspect.ismodule(obj):
        return [f"  - {name}: module ({obj.__name__})"]

    if inspect.isclass(obj):
        # Pydantic / non-Pydantic classes both go here. Snapshot the
        # __init__ signature; pydantic models render as their full
        # constructor (already covered field-by-field in cycle 2's
        # `ir-types.txt`, but having the constructor pinned at this
        # surface guards against rename + import-path changes).
        sig = _format_signature(obj)
        bases = ", ".join(b.__name__ for b in obj.__bases__ if b is not object)
        line = f"  - {name}: class"
        if bases:
            line += f" (bases=[{bases}])"
        if sig:
            line += f" {sig}"
        return [line]

    if inspect.isfunction(obj) or inspect.isbuiltin(obj):
        sig = _format_signature(obj)
        return [f"  - {name}: function {sig}".rstrip()]

    if callable(obj):
        sig = _format_signature(obj)
        return [f"  - {name}: callable ({type(obj).__name__}) {sig}".rstrip()]

    # Plain value — record its type + a short repr.
    if isinstance(obj, str):
        # Version strings, etc. Pin the *shape*, not the value, since version
        # strings will drift every release. Match `\d+\.\d+\.\d+(\.\w+)*`-ish
        # exactly so no value churn fires the gate. For non-version strings,
        # pin len + leading bytes.
        if all(c.isdigit() or c == "." for c in obj) and obj.count("."):
            return [f"  - {name}: str (version-like)"]
        return [f"  - {name}: str (len={len(obj)})"]
    annotation = _format_annotation(type(obj))
    return [f"  - {name}: {annotation} = {obj!r}"]


def snapshot_public_helpers() -> str:
    """Render the deterministic public-helpers API-surface snapshot."""
    lines: list[str] = []
    lines.append("# DAZZLE Public Helpers — API Surface (cycle 4 of #961)")
    lines.append("#")
    lines.append("# Source of truth: top-level `__init__.py` of each public package.")
    lines.append("# Regenerate: dazzle inspect-api public-helpers --write")
    lines.append("# Drift gate: tests/unit/test_api_surface_drift.py")
    lines.append("#")
    lines.append("# Resolution order per package:")
    lines.append("#   1. `__all__` if defined")
    lines.append("#   2. `_LOADERS` keys (lazy __getattr__ convention used by dazzle_back)")
    lines.append("#   3. all non-underscore module attributes (fallback)")
    lines.append("#")
    lines.append("# Adding/removing a name in `__all__` or `_LOADERS`, changing a function")
    lines.append("# signature, or repointing an export at a different class will fire the")
    lines.append("# drift gate.")
    lines.append("")

    for pkg_name, module in _load_packages():
        all_ = getattr(module, "__all__", None)
        loaders = getattr(module, "_LOADERS", None)
        source = (
            "__all__"
            if all_ is not None
            else "_LOADERS"
            if isinstance(loaders, dict)
            else "fallback (non-underscore attrs)"
        )

        names = _public_names(module)
        lines.append(f"package: {pkg_name}")
        lines.append(f"  source: {source}")
        lines.append(f"  count: {len(names)}")
        lines.append("  exports:")
        for name in names:
            obj = _resolve(module, name)
            lines.extend(_render_attr(name, obj))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def diff_against_baseline(snapshot: str | None = None) -> str:
    """Unified diff between baseline and live snapshot. Empty = no drift."""
    import difflib

    if snapshot is None:
        snapshot = snapshot_public_helpers()
    if not BASELINE_PATH.exists():
        return (
            f"(no baseline at {BASELINE_PATH} — run `dazzle inspect-api public-helpers --write`)\n"
        )
    baseline = BASELINE_PATH.read_text()
    if baseline == snapshot:
        return ""
    diff = difflib.unified_diff(
        baseline.splitlines(keepends=True),
        snapshot.splitlines(keepends=True),
        fromfile=str(BASELINE_PATH.relative_to(REPO_ROOT)),
        tofile="(live)",
        n=3,
    )
    return "".join(diff)


__all__ = [
    "BASELINE_PATH",
    "PACKAGE_NAMES",
    "diff_against_baseline",
    "snapshot_public_helpers",
]
