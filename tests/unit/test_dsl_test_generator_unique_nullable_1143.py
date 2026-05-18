"""#1143: VAL_*_UNIQUE tests must populate the target unique field
explicitly, even when it's nullable.

Pre-fix the generator copied the default test payload (which only
emits required fields), so a nullable unique field was absent from
both POSTs — Postgres stores two NULLs and the standard UNIQUE
constraint allows that, so the test could never trip. Both create
steps must now carry a concrete value for the target field.
"""

from __future__ import annotations

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.testing.dsl_test_generator import DSLTestGenerator


def _pk_field() -> FieldSpec:
    return FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


def _str_field(name: str, *, required: bool, unique: bool) -> FieldSpec:
    mods = []
    if required:
        mods.append(FieldModifier.REQUIRED)
    if unique:
        mods.append(FieldModifier.UNIQUE)
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.STR, max_length=100),
        modifiers=mods,
    )


def _appspec(entity: EntitySpec) -> AppSpec:
    return AppSpec(
        name="test",
        title="Test",
        domain=DomainSpec(entities=[entity]),
        surfaces=[
            SurfaceSpec(
                name=f"{entity.name.lower()}_create",
                entity_ref=entity.name,
                mode=SurfaceMode.CREATE,
            )
        ],
        views=[],
        enums=[],
        processes=[],
        ledgers=[],
        transactions=[],
        workspaces=[],
        experiences=[],
        personas=[],
        stories=[],
        webhooks=[],
        approvals=[],
        slas=[],
        islands=[],
    )


def _find_val_unique_test(suite, field_name: str):
    for t in suite.designs:
        if t["test_id"].endswith(f"_{field_name.upper()}_UNIQUE"):
            return t
    return None


def test_nullable_unique_field_populated_in_both_steps() -> None:
    """The bug class: `xero_invoice_id: str(100) unique` (not required)
    used to be omitted from both POSTs. Now both create steps carry
    a concrete value for it."""
    entity = EntitySpec(
        name="SubscriptionInvoice",
        title="Subscription Invoice",
        fields=[
            _pk_field(),
            _str_field("name", required=True, unique=False),  # required filler
            _str_field("xero_invoice_id", required=False, unique=True),
        ],
    )
    gen = DSLTestGenerator(_appspec(entity))
    tests = gen.generate_all()

    test = _find_val_unique_test(tests, "xero_invoice_id")
    assert test is not None, "VAL_*_XERO_INVOICE_ID_UNIQUE test not generated"

    create_steps = [s for s in test["steps"] if s["action"] in ("create", "create_expect_error")]
    assert len(create_steps) == 2
    for step in create_steps:
        assert "xero_invoice_id" in step["data"], (
            f"target unique field missing from {step['action']!r} payload: {step['data']!r}"
        )
        assert step["data"]["xero_invoice_id"] is not None


def test_two_create_steps_send_identical_unique_value() -> None:
    """Both POSTs must carry the SAME concrete value for the target
    field — that's what the runner's #1139 stash relies on. The
    explicit injection here doesn't break that contract."""
    entity = EntitySpec(
        name="FiscalYear",
        title="Fiscal Year",
        fields=[
            _pk_field(),
            _str_field("label", required=True, unique=False),
            _str_field("code", required=False, unique=True),
        ],
    )
    gen = DSLTestGenerator(_appspec(entity))
    tests = gen.generate_all()
    test = _find_val_unique_test(tests, "code")
    assert test is not None

    create_steps = [s for s in test["steps"] if s["action"] in ("create", "create_expect_error")]
    assert create_steps[0]["data"]["code"] == create_steps[1]["data"]["code"]


def test_required_unique_field_still_populated() -> None:
    """Regression guard: required-unique fields were always populated
    pre-#1143; that path must still produce a value."""
    entity = EntitySpec(
        name="User",
        title="User",
        fields=[
            _pk_field(),
            _str_field("email", required=True, unique=True),
        ],
    )
    gen = DSLTestGenerator(_appspec(entity))
    tests = gen.generate_all()
    test = _find_val_unique_test(tests, "email")
    assert test is not None
    create_steps = [s for s in test["steps"] if s["action"] in ("create", "create_expect_error")]
    for step in create_steps:
        assert step["data"].get("email")
