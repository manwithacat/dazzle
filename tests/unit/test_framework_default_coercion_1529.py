"""#1529 — framework-injected entity defaults are typed, not raw strings.

Framework entities (FeedbackReport, AIJob, AuditEntry, admin entities, …)
declare fields as tuples with DSL-style string defaults ("now", "false",
"0"). User DSL goes through the parser, which types these; the tuples
bypassed it, so raw strings flowed into pydantic models and the database
(PostgreSQL coerced 'now'::timestamptz by accident — the RBAC verifier
e2e surfaced it as pydantic serializer warnings).

Three layers under test:
1. ``coerce_framework_default`` — the parser-equivalent coercion helper.
2. Every framework field tuple coerces cleanly (sweep — a new tuple with
   an uncoercible string default fails here, not in production).
3. Layer B (service create default application) resolves date-expr dicts
   instead of storing them verbatim — the explicit-null hole.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field

from dazzle.core.ir import ModuleIR
from dazzle.core.ir.dates import DateLiteral, DateLiteralKind
from dazzle.core.ir.fields import FieldType, FieldTypeKind, coerce_framework_default
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_dsl

pytestmark = pytest.mark.unit


def _ft(kind: FieldTypeKind, **kw) -> FieldType:
    return FieldType(kind=kind, **kw)


# ── the helper ─────────────────────────────────────────────────────────────


class TestCoerceFrameworkDefault:
    def test_datetime_now_becomes_date_literal(self) -> None:
        got = coerce_framework_default("now", _ft(FieldTypeKind.DATETIME))
        assert got == DateLiteral(kind=DateLiteralKind.NOW)

    def test_date_today_becomes_date_literal(self) -> None:
        got = coerce_framework_default("today", _ft(FieldTypeKind.DATE))
        assert got == DateLiteral(kind=DateLiteralKind.TODAY)

    def test_bool_strings_become_bools(self) -> None:
        assert coerce_framework_default("false", _ft(FieldTypeKind.BOOL)) is False
        assert coerce_framework_default("true", _ft(FieldTypeKind.BOOL)) is True

    def test_int_strings_become_ints(self) -> None:
        assert coerce_framework_default("0", _ft(FieldTypeKind.INT)) == 0
        assert coerce_framework_default("1", _ft(FieldTypeKind.INT)) == 1

    def test_enum_and_str_defaults_pass_through(self) -> None:
        enum_ft = _ft(FieldTypeKind.ENUM, enum_values=["new", "done"])
        assert coerce_framework_default("new", enum_ft) == "new"
        assert coerce_framework_default("[]", _ft(FieldTypeKind.TEXT)) == "[]"

    def test_none_passes_through(self) -> None:
        assert coerce_framework_default(None, _ft(FieldTypeKind.DATETIME)) is None

    def test_untypeable_datetime_default_is_loud(self) -> None:
        with pytest.raises(ValueError, match="no typed form"):
            coerce_framework_default("yesterday", _ft(FieldTypeKind.DATETIME))

    def test_untypeable_bool_default_is_loud(self) -> None:
        with pytest.raises(ValueError, match="not true/false"):
            coerce_framework_default("maybe", _ft(FieldTypeKind.BOOL))


# ── sweep: every framework tuple coerces cleanly ──────────────────────────


def _all_framework_field_tuples():
    from dazzle.core.ir import admin_entities
    from dazzle.core.ir.audit import AUDIT_ENTRY_FIELDS
    from dazzle.core.ir.feedback_widget import FEEDBACK_REPORT_FIELDS
    from dazzle.core.ir.jobs import JOB_RUN_FIELDS
    from dazzle.core.ir.llm import AI_JOB_FIELDS
    from dazzle.core.ir.onboarding_state import ONBOARDING_STATE_FIELDS
    from dazzle.core.ir.process import PROCESS_RUN_FIELDS

    groups = {
        "AIJob": AI_JOB_FIELDS,
        "AuditEntry": AUDIT_ENTRY_FIELDS,
        "FeedbackReport": FEEDBACK_REPORT_FIELDS,
        "JobRun": JOB_RUN_FIELDS,
        "OnboardingState": ONBOARDING_STATE_FIELDS,
        "ProcessRun": PROCESS_RUN_FIELDS,
    }
    for attr in dir(admin_entities):
        value = getattr(admin_entities, attr)
        if attr.endswith("_FIELDS") and isinstance(value, tuple | list):
            groups[f"admin.{attr}"] = value
    for group, fields in groups.items():
        for entry in fields:
            yield group, entry


def test_every_framework_tuple_default_coerces() -> None:
    """A new framework tuple with an uncoercible default fails HERE."""
    from dazzle.core.linker import _parse_field_type

    checked = 0
    for group, (name, type_str, _mods, default) in _all_framework_field_tuples():
        if default is None:
            continue
        field_type = _parse_field_type(type_str)
        got = coerce_framework_default(default, field_type)  # must not raise
        checked += 1
        if field_type.kind in (FieldTypeKind.DATETIME, FieldTypeKind.DATE):
            assert isinstance(got, DateLiteral), f"{group}.{name}"
        elif field_type.kind == FieldTypeKind.BOOL:
            assert isinstance(got, bool), f"{group}.{name}"
        elif field_type.kind == FieldTypeKind.INT:
            assert isinstance(got, int), f"{group}.{name}"
    assert checked >= 20  # the 2026-07-02 inventory had 25 defaulted fields


# ── linker output: injected entities carry typed defaults ─────────────────


def test_injected_feedback_report_defaults_are_typed() -> None:
    dsl = """module t
app t "T"

feedback_widget: enabled

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""
    _, _, _, _, _, frag = parse_dsl(dsl, Path("t.dsl"))
    spec = build_appspec([ModuleIR(name="t", file=Path("t.dsl"), fragment=frag)], "t")
    report = next(e for e in spec.domain.entities if e.name == "FeedbackReport")
    by_name = {f.name: f for f in report.fields}

    assert by_name["created_at"].default == DateLiteral(kind=DateLiteralKind.NOW)
    assert by_name["updated_at"].default == DateLiteral(kind=DateLiteralKind.NOW)
    assert by_name["notification_sent"].default is False
    # enum defaults stay strings by design
    assert by_name["status"].default == "new"


# ── Layer B: service create resolves date-expr dict defaults ──────────────


class TestLayerBDateExprResolution:
    """Explicit null on a date-defaulted field must yield a typed datetime.

    The pydantic request model's default_factory covers OMITTED fields;
    an explicit null (or a create entry point bypassing the request model)
    reaches the service-layer default application, which previously
    assigned the raw ``{"kind": "now"}`` dict.
    """

    def _service(self):
        from dazzle.http.runtime.service_generator import CRUDService
        from dazzle.http.specs.entity import (
            EntitySpec,
            FieldSpec,
            FieldType,
            ScalarType,
        )

        entity = EntitySpec(
            name="Doc",
            description="date-expr default probe",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                    unique=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
                FieldSpec(
                    name="stamped_at",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.DATETIME),
                    default={"kind": "now"},
                ),
            ],
        )

        class DocModel(BaseModel):
            id: UUID = Field(default_factory=uuid4)
            title: str
            stamped_at: datetime | None = None

        class DocCreate(BaseModel):
            title: str
            stamped_at: datetime | None = None

        class DocUpdate(BaseModel):
            title: str | None = None

        return CRUDService(
            entity_name="Doc",
            model_class=DocModel,
            create_schema=DocCreate,
            update_schema=DocUpdate,
            entity_spec=entity,
        )

    @pytest.mark.asyncio
    async def test_explicit_null_resolves_to_datetime(self) -> None:
        service = self._service()
        before = datetime.now(UTC)
        result = await service.create(service.create_schema(title="x", stamped_at=None))
        after = datetime.now(UTC)
        assert isinstance(result.stamped_at, datetime)
        assert before <= result.stamped_at <= after
