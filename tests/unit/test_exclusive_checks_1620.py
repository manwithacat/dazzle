"""#1620 exclusive-anchor CHECK codegen."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from dazzle.core.parser import parse_modules
from dazzle.db.exclusive_checks import (
    check_constraint_specs,
    exclusive_check_name,
    exclusive_exactly_one_sql,
)
from dazzle.db.schema_diff import AddCheck, diff
from dazzle.db.schema_render import render
from dazzle.db.schema_snapshot import project_schema
from dazzle.http.runtime.sa_schema import build_metadata

pytestmark = pytest.mark.gate


def _doc_entities(tmp_path: Path):
    body = """
entity Case "Case":
  id: uuid pk

entity Matter "Matter":
  id: uuid pk

entity Doc "Doc":
  id: uuid pk
  case_ref: ref Case
  matter_ref: ref Matter
  invariant: case_ref != null or matter_ref != null
"""
    f = tmp_path / "app.dsl"
    f.write_text(f'module t\n\napp t "T"\n\n{body}', encoding="utf-8")
    (module,) = parse_modules([f])
    return list(module.fragment.entities)


def test_exactly_one_sql_shape() -> None:
    sql = exclusive_exactly_one_sql(["company", "sole_trader"])
    assert "company" in sql and "sole_trader" in sql
    assert "= 1" in sql
    assert exclusive_check_name("Sub", ["a", "b"]).startswith("ck_Sub_excl_")


def test_check_specs_from_invariant(tmp_path: Path) -> None:
    entities = _doc_entities(tmp_path)
    doc = next(e for e in entities if e.name == "Doc")
    specs = check_constraint_specs(doc)
    assert len(specs) == 1
    name, sql, fields = specs[0]
    assert fields == ["case_ref", "matter_ref"]
    assert "case_ref" in sql and "= 1" in sql
    assert name.startswith("ck_Doc_excl_")


def test_build_metadata_emits_check(tmp_path: Path) -> None:
    entities = _doc_entities(tmp_path)
    meta = build_metadata(entities)
    doc = meta.tables["Doc"]
    checks = [c for c in doc.constraints if isinstance(c, sa.CheckConstraint)]
    assert checks, "expected CheckConstraint on Doc"
    assert any("case_ref" in str(c.sqltext) for c in checks)


def test_snapshot_and_diff_render_add_check(tmp_path: Path) -> None:
    entities = _doc_entities(tmp_path)
    meta = build_metadata(entities)
    curr = project_schema(meta)
    assert curr["Doc"].get("checks"), "snapshot must capture checks"
    prev = {
        "Case": curr["Case"],
        "Matter": curr["Matter"],
        "Doc": {
            **curr["Doc"],
            "checks": [],  # no CHECKs yet
        },
    }
    # Only Doc constraints differ — rebuild prev Doc without checks
    prev["Doc"] = {
        "columns": curr["Doc"]["columns"],
        "fks": curr["Doc"]["fks"],
        "uniques": curr["Doc"]["uniques"],
        "indexes": curr["Doc"]["indexes"],
        "checks": [],
    }
    ops = diff(prev, curr)
    adds = [o for o in ops if isinstance(o, AddCheck)]
    assert adds, f"expected AddCheck, got {ops!r}"
    up, _down = render(adds)
    # Alembic CreateCheckConstraintOp in upgrade stream
    text = "\n".join(type(o).__name__ for o in up.ops)
    assert "CreateCheckConstraintOp" in text or any("Check" in type(o).__name__ for o in up.ops)
