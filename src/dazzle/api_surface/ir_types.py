"""
IR-types API surface snapshot — cycle 2 of #961.

Walks `dazzle.core.ir.__all__` and pins the public surface of every IR
type: BaseModel field listings, Enum member listings, and a manifest of
non-snapshotted exports (functions, type aliases, constants).
"""

import enum
import types

from pydantic import BaseModel

from .dsl_constructs import (
    REPO_ROOT,
    _format_annotation,
    _render_ir_class,
)

BASELINE_PATH = REPO_ROOT / "docs" / "api-surface" / "ir-types.txt"


def _render_enum(cls: type[enum.Enum]) -> list[str]:
    lines = [f"enum: {cls.__name__}"]
    members = []
    for member in cls:
        value = repr(member.value)
        members.append(f"    - {member.name} = {value}")
    if members:
        lines.append("  members:")
        lines.extend(sorted(members))
    else:
        lines.append("  members: (none)")
    return lines


def _categorize(obj: object) -> str:
    if isinstance(obj, type) and issubclass(obj, BaseModel):
        return "basemodel"
    if isinstance(obj, type) and issubclass(obj, enum.Enum):
        return "enum"
    if isinstance(obj, type):
        return "class_other"
    if callable(obj):
        return "function"
    if isinstance(obj, types.UnionType) or hasattr(obj, "__origin__"):
        return "typealias"
    return "constant"


def _render_other(name: str, obj: object, category: str) -> str:
    if category == "class_other":
        assert isinstance(obj, type)
        bases = ", ".join(b.__name__ for b in obj.__bases__ if b is not object)
        return f"  - {name} (class, bases=[{bases}])"
    if category == "function":
        return f"  - {name} (callable, type={type(obj).__name__})"
    if category == "typealias":
        return f"  - {name} (typealias = {_format_annotation(obj)})"
    if category == "constant":
        type_name = type(obj).__name__
        # For containers, record the length (short, change-detectable);
        # for scalars, record the repr (truncated).
        if hasattr(obj, "__len__"):
            try:
                length = len(obj)
                return f"  - {name}: {type_name} (len={length})"
            except TypeError:
                pass
        rep = repr(obj)
        if len(rep) > 80:
            rep = rep[:77] + "..."
        return f"  - {name}: {type_name} = {rep}"
    return f"  - {name} (uncategorized)"


def snapshot_ir_types() -> str:
    """Render the deterministic IR-types API-surface snapshot."""
    import dazzle.core.ir as ir

    exports = sorted(getattr(ir, "__all__", []))

    base_models: dict[str, type[BaseModel]] = {}
    enums: dict[str, type[enum.Enum]] = {}
    others: list[tuple[str, object, str]] = []
    missing: list[str] = []

    for name in exports:
        obj = getattr(ir, name, None)
        if obj is None:
            missing.append(name)
            continue
        category = _categorize(obj)
        if category == "basemodel":
            assert isinstance(obj, type) and issubclass(obj, BaseModel)
            base_models[name] = obj
        elif category == "enum":
            assert isinstance(obj, type) and issubclass(obj, enum.Enum)
            enums[name] = obj
        else:
            others.append((name, obj, category))

    lines: list[str] = []
    lines.append("# DAZZLE IR Types — API Surface (cycle 2 of #961)")
    lines.append("#")
    lines.append("# Source of truth: dazzle.core.ir.__all__")
    lines.append("# Regenerate: dazzle inspect-api ir-types --write")
    lines.append("# Drift gate: tests/unit/test_api_surface_drift.py")
    lines.append("#")
    lines.append("# Every IR type re-exported from `dazzle.core.ir` is part of the public")
    lines.append("# Python API. Adding, removing, or changing fields on a BaseModel — or")
    lines.append("# adding/removing enum members — drifts this baseline. To accept drift:")
    lines.append("# regenerate, review, add a CHANGELOG entry under Added / Changed / Removed.")
    lines.append("")
    lines.append(f"# Counts: {len(base_models)} BaseModels, {len(enums)} Enums, ")
    lines[-1] += f"{len(others)} other (functions / typealiases / constants)"
    lines.append("")
    lines.append("== BaseModels ==")
    lines.append("")
    for name in sorted(base_models):
        lines.extend(_render_ir_class(base_models[name]))
        lines.append("")

    lines.append("== Enums ==")
    lines.append("")
    for name in sorted(enums):
        lines.extend(_render_enum(enums[name]))
        lines.append("")

    lines.append("== Other Exports ==")
    lines.append("# Functions, type aliases, and module constants. Field-level details are not")
    lines.append("# snapshotted; only the export name + category is pinned (so removal/rename")
    lines.append("# fires the drift gate).")
    lines.append("")
    by_category: dict[str, list[tuple[str, object]]] = {}
    for name, obj, category in others:
        by_category.setdefault(category, []).append((name, obj))
    for category in sorted(by_category):
        lines.append(f"category: {category}")
        for name, obj in sorted(by_category[category]):
            lines.append(_render_other(name, obj, category))
        lines.append("")

    if missing:
        lines.append("== Missing (declared in __all__ but not importable) ==")
        for name in sorted(missing):
            lines.append(f"  - {name}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def diff_against_baseline(snapshot: str | None = None) -> str:
    """Unified diff between baseline and live snapshot. Empty = no drift."""
    import difflib

    if snapshot is None:
        snapshot = snapshot_ir_types()
    if not BASELINE_PATH.exists():
        return f"(no baseline at {BASELINE_PATH} — run `dazzle inspect-api ir-types --write`)\n"
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


# Re-export helpers used by the public API.
__all__ = [
    "BASELINE_PATH",
    "diff_against_baseline",
    "snapshot_ir_types",
]
