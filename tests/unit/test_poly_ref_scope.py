"""#1448: poly_ref scope path parsing → PolyPathCheck build → validation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _build_appspec(dsl: str):
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(dsl)
        f.flush()
        fpath = Path(f.name)
    try:
        modules = parse_modules([fpath])
        return build_appspec(modules, modules[0].name)
    finally:
        os.unlink(fpath)


_OK = """module m
app a "A"

entity Cohort "Cohort":
  id: uuid pk
  uploaded_by: uuid

entity AIJob "AI Job":
  id: uuid pk
  target: poly_ref [Cohort] required

  permit:
    read: role(teacher)

  scope:
    read: target[Cohort].uploaded_by = current_user
      as: teacher
"""


def test_scope_builds_poly_path_check():
    from dazzle.core.ir.predicates import PolyPathCheck, UserAttrCheck

    appspec = _build_appspec(_OK)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    pred = aijob.access.scopes[0].predicate
    assert isinstance(pred, PolyPathCheck)
    assert pred.field == "target"
    assert pred.type_field == "target_type"
    assert pred.id_field == "target_id"
    assert pred.type_value == "Cohort"
    assert pred.target_entity == "Cohort"
    assert isinstance(pred.sub, UserAttrCheck)
    assert pred.sub.field == "uploaded_by"


def test_validation_accepts_poly_scope():
    from dazzle.core.validation.rbac import validate_scope_predicates

    appspec = _build_appspec(_OK)
    errors, _ = validate_scope_predicates(appspec)
    assert errors == []


def test_validation_rejects_undeclared_branch():
    from dazzle.core.validation.rbac import validate_scope_predicates

    src = _OK.replace("target[Cohort].uploaded_by", "target[Manuscript].uploaded_by")
    appspec = _build_appspec(src)
    errors, _ = validate_scope_predicates(appspec)
    assert any("Manuscript" in e or "BRANCH_UNDECLARED" in e for e in errors)


def test_validation_requires_selector():
    from dazzle.core.validation.rbac import validate_scope_predicates

    src = _OK.replace("target[Cohort].uploaded_by", "target.uploaded_by")
    appspec = _build_appspec(src)
    errors, _ = validate_scope_predicates(appspec)
    assert any("SELECTOR_REQUIRED" in e or "poly_ref" in e.lower() for e in errors)


_CREATE_POLY = """module m
app a "A"

entity Cohort "Cohort":
  id: uuid pk
  uploaded_by: uuid

entity AIJob "AI Job":
  id: uuid pk
  target: poly_ref [Cohort] required

  permit:
    create: role(teacher)

  scope:
    create: target[Cohort].uploaded_by = current_user
      as: teacher
"""


def test_validation_rejects_poly_on_create():
    # Adversarial-review fix: create/update poly scopes fail closed at runtime;
    # reject them loudly at validate time (MVP non-goal — read/list/delete only).
    from dazzle.core.validation.rbac import validate_scope_predicates

    appspec = _build_appspec(_CREATE_POLY)
    errors, _ = validate_scope_predicates(appspec)
    assert any("VERB_UNSUPPORTED" in e for e in errors)
