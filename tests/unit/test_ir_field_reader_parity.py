"""Declaration-without-consumer parity lint for IR dataclass fields.

Catches the `WorkspaceContract.allow_personas` class of half-finished internal:
an IR field is declared but no framework code ever reads it.

This is a **ratchet lint**: a baseline (``tests/unit/fixtures/ir_reader_baseline.json``)
captures fields known to be orphans at the time the lint was introduced. The test
fails only if:

  * A *new* orphan appears (a newly-added IR field with no reader), or
  * A *baselined* orphan has acquired a reader (shrink the baseline).

Detection strategy
------------------

* Enumerate every annotated public field on every class in ``src/dazzle/core/ir/``
  via AST. Skip Enum-only classes (their members are values, not fields).
* Collect every ``.attr`` access across ``src/`` (excluding the IR tree) via AST,
  plus every string-literal argument to ``getattr``/``setattr``/``hasattr``/``delattr``
  (catches the common ``getattr(region, "heatmap_rows", None)`` pattern).
* Collect every ``.attr`` reference in Jinja templates (``src/**/*.html``) via regex.
* Any IR field name not in the reader set is an orphan.

Known limitations
-----------------

* Fields read only via pydantic ``model_dump()`` serialization to a wire format
  are classified as orphans; they are part of the current baseline. Future work
  could detect "class is routinely dumped" and treat its fields as wire-format.
* Fields read only through reflection with non-literal names (``getattr(obj, name_var)``)
  are not detected.
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IR_ROOT = REPO_ROOT / "src" / "dazzle" / "core" / "ir"
SRC_ROOT = REPO_ROOT / "src"
BASELINE_PATH = REPO_ROOT / "tests" / "unit" / "fixtures" / "ir_reader_baseline.json"

JINJA_ATTR_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)")
GETATTR_FAMILY = {"getattr", "setattr", "hasattr", "delattr"}
PYDANTIC_META = {"model_config", "model_fields", "model_computed_fields"}


def _is_scannable_field(name: str) -> bool:
    return not name.startswith("_") and name not in PYDANTIC_META


def _extract_ir_fields() -> list[tuple[str, str, str]]:
    """Return (module_stem, class_name, field_name) for every public IR field."""
    results: list[tuple[str, str, str]] = []
    for py_path in sorted(IR_ROOT.glob("*.py")):
        if py_path.name.startswith("_"):
            continue
        tree = ast.parse(py_path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                (
                    b.attr
                    if isinstance(b, ast.Attribute)
                    else (b.id if isinstance(b, ast.Name) else "")
                )
                for b in node.bases
            }
            # Skip Enum-only classes (values, not fields with readers).
            is_enum_only = (base_names & {"StrEnum", "IntEnum", "Enum"}) and not (
                base_names & {"BaseModel"}
            )
            if is_enum_only:
                continue
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fname = item.target.id
                    if _is_scannable_field(fname):
                        results.append((py_path.stem, node.name, fname))
    return results


def _collect_python_readers(py_path: Path) -> set[str]:
    try:
        tree = ast.parse(py_path.read_text())
    except SyntaxError:
        return set()
    attrs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attrs.add(node.attr)
        elif isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            if func_name in GETATTR_FAMILY and len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    attrs.add(arg.value)
    return attrs


def _collect_jinja_readers(html_path: Path) -> set[str]:
    return set(JINJA_ATTR_RE.findall(html_path.read_text(errors="ignore")))


def _compute_orphans() -> set[str]:
    """Return the set of 'module.Class.field' identifiers with no external reader."""
    readers: defaultdict[str, set[str]] = defaultdict(set)
    ir_rel = IR_ROOT.relative_to(SRC_ROOT.parent)

    for py_path in SRC_ROOT.rglob("*.py"):
        rel = py_path.relative_to(SRC_ROOT.parent)
        if str(rel).startswith(str(ir_rel)):
            continue
        if "__pycache__" in py_path.parts:
            continue
        for attr in _collect_python_readers(py_path):
            readers[attr].add(str(rel))

    for html_path in SRC_ROOT.rglob("*.html"):
        if "__pycache__" in html_path.parts:
            continue
        for attr in _collect_jinja_readers(html_path):
            readers[attr].add(str(html_path.relative_to(SRC_ROOT.parent)))

    orphans: set[str] = set()
    for module, cls, field in _extract_ir_fields():
        if not readers.get(field):
            orphans.add(f"{module}.{cls}.{field}")
    return orphans


def _load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    return set(json.loads(BASELINE_PATH.read_text()))


def test_no_new_ir_field_orphans() -> None:
    """New IR fields must have at least one external reader.

    If this test fails:
    * New orphan → either wire the field into a consumer, or (rarely) add it to
      ``tests/unit/fixtures/ir_reader_baseline.json`` with a comment in the PR.
    * Baselined orphan resolved → remove it from the baseline JSON.
    """
    current = _compute_orphans()
    baseline = _load_baseline()

    new_orphans = sorted(current - baseline)
    resolved = sorted(baseline - current)

    messages: list[str] = []
    if new_orphans:
        messages.append(
            f"{len(new_orphans)} new IR field(s) have zero external readers:\n  "
            + "\n  ".join(new_orphans)
            + "\n\nWire the field into a consumer, or justify adding to "
            + str(BASELINE_PATH.relative_to(REPO_ROOT))
        )
    if resolved:
        messages.append(
            f"{len(resolved)} baselined orphan(s) now have readers — remove them from "
            + str(BASELINE_PATH.relative_to(REPO_ROOT))
            + ":\n  "
            + "\n  ".join(resolved)
        )
    if messages:
        pytest.fail("\n\n".join(messages))


if __name__ == "__main__":
    # Regenerate-baseline convenience: `python tests/unit/test_ir_field_reader_parity.py`
    orphans = sorted(_compute_orphans())
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(orphans, indent=2) + "\n")
    print(f"Wrote {len(orphans)} orphans to {BASELINE_PATH}")
