"""
DSL constructs API surface snapshot — cycle 1 of #961.

Walks the parser dispatch table, resolves each construct to its IR class via
`ModuleFragment.model_fields`, and emits a deterministic text snapshot. The
snapshot is committed to `docs/api-surface/dsl-constructs.txt`. Drift is
caught by `tests/unit/test_api_surface_drift.py`.
"""

import inspect
import re
import types
import typing
from pathlib import Path

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = REPO_ROOT / "docs" / "api-surface" / "dsl-constructs.txt"

_FIELD_KEY_RE = re.compile(r'"([a-z_][a-z0-9_]*)"\s*:')


def _instantiate_parser() -> typing.Any:
    from pathlib import Path as _Path

    from dazzle.core.dsl_parser_impl import Parser

    return Parser([], _Path("/synthetic-for-introspection"))


def _construct_to_fragment_fields() -> dict[str, list[str]]:
    """
    Map each parser-dispatched construct (DSL keyword) to the
    `ModuleFragment` field(s) it writes into.

    Source of truth: `Parser._build_parse_dispatch()` plus the special-case
    VIEW branch in `Parser.parse()`. Field names are extracted from the
    handler source by parsing the dict-literal updates.
    """
    parser = _instantiate_parser()
    table = parser._build_parse_dispatch()

    out: dict[str, list[str]] = {}
    for token_type, handler in table.items():
        construct = token_type.value
        src = inspect.getsource(handler.__func__ if hasattr(handler, "__func__") else handler)
        # Skip the dispatched dict that copies all existing fields:
        # `{f: getattr(fragment, f) for f in ir.ModuleFragment.model_fields}`
        # — only literal keys that follow that comprehension are real writes.
        before, _, after = src.partition("for f in ir.ModuleFragment.model_fields")
        target = after if after else src
        fields = sorted(set(_FIELD_KEY_RE.findall(target)))
        # Filter to fields that actually exist on ModuleFragment (defensive
        # against future handlers that build dict keys for other reasons).
        from dazzle.core.ir.module import ModuleFragment

        valid = set(ModuleFragment.model_fields)
        fields = [f for f in fields if f in valid]
        if fields:
            out[construct] = fields

    out.setdefault("view", ["views"])
    return dict(sorted(out.items()))


def _unwrap_optional(annotation: typing.Any) -> typing.Any:
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _ir_class_for_field(field_annotation: typing.Any) -> type[BaseModel] | None:
    inner = _unwrap_optional(field_annotation)
    origin = typing.get_origin(inner)
    if origin in (list, set, tuple):
        args = typing.get_args(inner)
        if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            return args[0]
        return None
    if isinstance(inner, type) and issubclass(inner, BaseModel):
        return inner
    return None


def _format_annotation(annotation: typing.Any) -> str:
    """
    Render a Pydantic field annotation as a stable, type-name-only string
    (no module prefixes — those are noise for diffing).
    """
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is None:
        if annotation is type(None):
            return "None"
        if isinstance(annotation, type):
            return annotation.__name__
        return str(annotation)

    if origin is typing.Union or origin is types.UnionType:
        return " | ".join(_format_annotation(a) for a in args)

    if origin is list:
        return f"list[{_format_annotation(args[0])}]" if args else "list"
    if origin is set:
        return f"set[{_format_annotation(args[0])}]" if args else "set"
    if origin is tuple:
        if not args:
            return "tuple"
        return "tuple[" + ", ".join(_format_annotation(a) for a in args) + "]"
    if origin is dict:
        if not args:
            return "dict"
        return f"dict[{_format_annotation(args[0])}, {_format_annotation(args[1])}]"

    if origin is type(None):
        return "None"

    name = getattr(origin, "__name__", str(origin))
    if args:
        return f"{name}[" + ", ".join(_format_annotation(a) for a in args) + "]"
    return name


def _format_default(info: FieldInfo) -> str:
    if info.default is not PydanticUndefined:
        return repr(info.default)
    factory = info.default_factory
    if factory is not None:
        # Render canonical empty containers as their literal form for clean
        # diffs; everything else falls back to the factory's qualified name.
        value: typing.Any = None
        try:
            value = factory()  # type: ignore[call-arg]
        except Exception:
            value = None
        if value == [] or value == {} or value == set():
            return repr(value)
        name = getattr(factory, "__qualname__", getattr(factory, "__name__", repr(factory)))
        return f"<factory:{name}>"
    return ""


def _is_required(info: FieldInfo) -> bool:
    return info.default is PydanticUndefined and info.default_factory is None


def _render_ir_class(cls: type[BaseModel]) -> list[str]:
    required: list[str] = []
    optional: list[str] = []
    for field_name in sorted(cls.model_fields):
        info = cls.model_fields[field_name]
        type_str = _format_annotation(info.annotation)
        if _is_required(info):
            required.append(f"    - {field_name}: {type_str}")
        else:
            default = _format_default(info)
            suffix = f" = {default}" if default else ""
            optional.append(f"    - {field_name}: {type_str}{suffix}")

    lines = [f"ir_class: {cls.__name__}"]
    lines.append("  required:" if required else "  required: (none)")
    lines.extend(required)
    lines.append("  optional:" if optional else "  optional: (none)")
    lines.extend(optional)
    return lines


def snapshot_dsl_constructs() -> str:
    """Render the deterministic DSL-constructs API-surface snapshot."""
    from dazzle.core.ir.module import ModuleFragment

    construct_map = _construct_to_fragment_fields()

    lines: list[str] = []
    lines.append("# DAZZLE DSL Constructs — API Surface (cycle 1 of #961)")
    lines.append("#")
    lines.append("# Source of truth: parser dispatch table + ModuleFragment.model_fields.")
    lines.append("# Regenerate: dazzle inspect-api dsl-constructs --write")
    lines.append("# Drift gate: tests/unit/test_api_surface_drift.py")
    lines.append("#")
    lines.append("# This snapshot pins the construct → IR-class mapping. Field-level")
    lines.append("# details for each IR class live in `docs/api-surface/ir-types.txt`")
    lines.append("# (cycle 2). Together they form the DSL surface contract.")
    lines.append("#")
    lines.append("# To accept drift: regenerate, review, add a CHANGELOG entry under")
    lines.append("# Added / Changed / Removed (the DSL is part of the public API).")
    lines.append("")
    lines.append("== Constructs ==")
    lines.append("")
    for construct, fields in construct_map.items():
        lines.append(f"construct: {construct}")
        lines.append(f"  fragment_fields: {', '.join(fields)}")
        ir_names = []
        for f in fields:
            info = ModuleFragment.model_fields.get(f)
            if info is None:
                continue
            cls = _ir_class_for_field(info.annotation)
            if cls is not None:
                ir_names.append(cls.__name__)
        if ir_names:
            lines.append(f"  ir_classes: {', '.join(sorted(set(ir_names)))}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def diff_against_baseline(snapshot: str | None = None) -> str:
    """
    Return a unified diff between the on-disk baseline and the live snapshot.
    Empty string means no drift.
    """
    import difflib

    if snapshot is None:
        snapshot = snapshot_dsl_constructs()
    if not BASELINE_PATH.exists():
        return (
            f"(no baseline at {BASELINE_PATH} — run `dazzle inspect-api dsl-constructs --write`)\n"
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
