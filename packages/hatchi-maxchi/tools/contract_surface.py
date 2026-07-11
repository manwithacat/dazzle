#!/usr/bin/env python3
"""Snapshot every Hyperpart contract module's public surface.

Detects breaking changes to lower-level parts *before* consumers notice:
DOM root/node attrs and Pydantic model fields are serialised to a committed
markdown table. CI fails when the live surface diverges from the committed
file without an intentional regenerate.

    python packages/hatchi-maxchi/tools/contract_surface.py
    python packages/hatchi-maxchi/tools/contract_surface.py --write

CI: ``tests/unit/test_contract_surface_tool.py``.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import types
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parent.parent
OUT = PKG / "CONTRACT_SURFACE.md"

# Ensure `import contracts.X` works
sys.path.insert(0, str(PKG))


def _validator_label(v: object) -> str:
    name = type(v).__name__
    if name == "Present":
        return "present"
    if name == "OneOf":
        vals = getattr(v, "values", ())
        return "one_of:" + "|".join(vals)
    if name == "JsonPairs":
        rw = getattr(v, "required_when", None)
        if rw:
            cond = ",".join(f"{k}={val}" for k, val in sorted(rw.items()))
            return f"json_pairs(when:{cond})"
        return "json_pairs"
    return name


def _ann_label(ann: object) -> str:
    """Stable type label across Python versions (3.12–3.14).

    Bare ``getattr(ann, "__name__")`` collapses ``list[tuple[str, str]] | None``
    to ``Union`` on some interpreters (CI 3.14), which thrashs CONTRACT_SURFACE.md
    without a real contract change.
    """
    if ann is None:
        return "None"
    if ann is type(None):
        return "None"

    origin = get_origin(ann)
    args = get_args(ann)

    # PEP 604 unions (X | Y) and typing.Union / Optional
    if origin is Union or origin is types.UnionType or isinstance(ann, types.UnionType):
        if not args and isinstance(ann, types.UnionType):
            args = get_args(ann)
        parts = sorted((_ann_label(a) for a in args), key=lambda s: (s == "None", s))
        # Drop duplicate Nones; keep stable X|None form
        seen: list[str] = []
        for p in parts:
            if p not in seen:
                seen.append(p)
        return "|".join(seen)

    if origin is list:
        return f"list[{_ann_label(args[0])}]" if args else "list"
    if origin is tuple:
        if not args:
            return "tuple"
        if len(args) == 2 and args[1] is Ellipsis:
            return f"tuple[{_ann_label(args[0])},...]"
        return "tuple[" + ",".join(_ann_label(a) for a in args) + "]"
    if origin is dict:
        if len(args) >= 2:
            return f"dict[{_ann_label(args[0])},{_ann_label(args[1])}]"
        return "dict"
    if origin is set:
        return f"set[{_ann_label(args[0])}]" if args else "set"
    if origin is Literal:
        return "Literal"

    if isinstance(ann, type):
        return ann.__name__

    # ForwardRef / string annotations
    text = str(ann)
    text = text.replace("typing.", "").replace("types.", "")
    text = text.replace("NoneType", "None")
    # Collapse Optional[X] if it ever appears as a string
    if text.startswith("Optional[") and text.endswith("]"):
        inner = text[len("Optional[") : -1]
        return f"{inner}|None"
    return text


def _model_fields(cls: type[BaseModel]) -> list[str]:
    # Pydantic v2
    fields = getattr(cls, "model_fields", None)
    if fields is not None:
        out = []
        for fname, finfo in fields.items():
            ann = getattr(finfo, "annotation", None)
            ann_s = _ann_label(ann)
            req = "req" if finfo.is_required() else "opt"
            out.append(f"{fname}:{ann_s}:{req}")
        return sorted(out)
    return []


def inventory() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted((PKG / "contracts").glob("*.py")):
        if path.stem.startswith("_") or path.stem == "__init__":
            continue
        mod = importlib.import_module(f"contracts.{path.stem}")
        dom = getattr(mod, "DOM_CONTRACT", None)
        root = getattr(dom, "root", "—") if dom is not None else "—"
        part = getattr(dom, "part", path.stem) if dom is not None else path.stem
        node_bits: list[str] = []
        if dom is not None:
            for node in getattr(dom, "nodes", ()) or ():
                attrs = []
                for attr, validator in sorted(node.attrs.items()):
                    attrs.append(f"{attr}={_validator_label(validator)}")
                node_bits.append(f"{node.selector}[{', '.join(attrs)}]")
        models: list[str] = []
        for name in dir(mod):
            obj = getattr(mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == mod.__name__
            ):
                models.append(f"{name}({'; '.join(_model_fields(obj))})")
        rows.append(
            {
                "module": path.stem,
                "part": str(part),
                "root": str(root),
                "nodes": "; ".join(node_bits) if node_bits else "—",
                "models": "; ".join(sorted(models)) if models else "—",
            }
        )
    return rows


def render_md(rows: list[dict[str, str]] | None = None) -> str:
    rows = rows if rows is not None else inventory()
    lines = [
        "# Contract surface snapshot",
        "",
        "Auto-generated by `tools/contract_surface.py`. Do not hand-edit.",
        "",
        "Regenerate: `python packages/hatchi-maxchi/tools/contract_surface.py --write`",
        "",
        "This is a **breaking-change detector** for dual-lock contracts. If you",
        "add/remove/rename a required DOM attr or model field, this file changes",
        "and CI fails until you regenerate *and* check `CONSUMER_MAP.md` for",
        "blast radius (who embeds / refuses this part).",
        "",
        f"| Modules | {len(rows)} |",
        "",
        "| Module | Part | Root | Nodes (attr constraints) | Models (field:type:req) |",
        "|--------|------|------|--------------------------|-------------------------|",
    ]
    for r in rows:
        # Escape pipes in cell content
        nodes = r["nodes"].replace("|", "\\|")
        models = r["models"].replace("|", "\\|")
        lines.append(f"| `{r['module']}` | `{r['part']}` | `{r['root']}` | {nodes} | {models} |")
    lines.extend(
        [
            "",
            "## Related",
            "",
            "- `CONSUMER_MAP.md` — reverse composition / non-composition index",
            "- `DUAL_LOCK_COVERAGE.md` — dual-lock tier inventory",
            "- `contracts/AUTHORING.md` — how to change a contract safely",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help=f"write {OUT}")
    args = ap.parse_args(argv)
    if not (PKG / "contracts").is_dir():
        print("error: contracts/ not found", file=sys.stderr)
        return 2
    try:
        md = render_md()
    except Exception as exc:  # noqa: BLE001 — tool surface; print and fail
        print(f"error building surface: {exc}", file=sys.stderr)
        return 1
    if args.write:
        OUT.write_text(md, encoding="utf-8")
        print(f"wrote {OUT}")
    else:
        print(md, end="" if md.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
