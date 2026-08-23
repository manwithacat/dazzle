"""Invariant 422 speech must not dump duration_minutes (oral #202)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.htmx import json_or_htmx_error
from dazzle.http.runtime.invariant_evaluator import (
    InvariantViolationError,
    check_invariants_for_create,
    clerk_invariant_expr,
    clerk_invariant_speech,
    render_invariant_expr,
)
from dazzle.http.specs.entity import (
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
)
from dazzle.render.filters import clerk_form_error_field_label

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")


def _request(method: str, *, htmx: bool = True) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = "duration_minutes"
    return SimpleNamespace(method=method, headers=headers, query_params={})


def _field_ref(*path: str) -> InvariantExprSpec:
    return InvariantExprSpec(kind="field_ref", path=list(path))


def _literal(value: object) -> InvariantExprSpec:
    return InvariantExprSpec(kind="literal", value=value)


def _comparison(
    left: InvariantExprSpec,
    op: InvariantComparisonKind,
    right: InvariantExprSpec,
) -> InvariantExprSpec:
    return InvariantExprSpec(
        kind="comparison",
        comparison_left=left,
        comparison_op=op,
        comparison_right=right,
    )


def _logical(
    left: InvariantExprSpec,
    op: InvariantLogicalKind,
    right: InvariantExprSpec,
) -> InvariantExprSpec:
    return InvariantExprSpec(
        kind="logical",
        logical_left=left,
        logical_op=op,
        logical_right=right,
    )


def test_fieldtest_duration_minutes_invariant_is_live() -> None:
    block = (FIELDTEST / "dsl" / "app.dsl").read_text()
    assert 'entity TestSession "Test Session":' in block
    assert "duration_minutes: int" in block
    assert "invariant: duration_minutes > 0" in block
    create = block.split("surface test_session_create", 1)[1]
    assert 'field duration_minutes "Duration' in create.split("surface ", 1)[0]


def test_contact_email_or_phone_invariant_is_live() -> None:
    block = (CONTACT / "dsl" / "app.dsl").read_text()
    assert "invariant: email != null or phone != null" in block


def test_clerk_invariant_expr_is_clerk_not_schema() -> None:
    expr = _comparison(_field_ref("duration_minutes"), InvariantComparisonKind.GT, _literal(0))
    assert clerk_invariant_expr(expr) == "Duration Minutes > 0"
    assert render_invariant_expr(expr) == "duration_minutes > 0"
    assert clerk_form_error_field_label("duration_minutes") == "Duration Minutes"


def test_clerk_invariant_or_null_is_clerk_not_schema() -> None:
    expr = _logical(
        _comparison(_field_ref("email"), InvariantComparisonKind.NE, _literal(None)),
        InvariantLogicalKind.OR,
        _comparison(_field_ref("phone"), InvariantComparisonKind.NE, _literal(None)),
    )
    speech = clerk_invariant_expr(expr)
    assert "Email" in speech
    assert "Phone" in speech
    assert "empty" in speech
    assert "email" not in speech
    assert "phone" not in speech
    assert "null" not in speech
    assert render_invariant_expr(expr) == "email != null or phone != null"


def test_leftover_zzz_invents_no_field() -> None:
    expr = _comparison(_field_ref("zzz"), InvariantComparisonKind.GT, _literal("ghost"))
    speech = clerk_invariant_expr(expr)
    assert "zzz" in speech
    assert "ghost" in speech
    assert "Zzz" not in speech
    assert "Ghost" not in speech


def test_empty_expr_invents_no_field() -> None:
    assert clerk_invariant_expr(None) == ""
    assert clerk_invariant_speech(None) == "Invariant constraint violated"


def test_authored_message_wins_including_leftover() -> None:
    inv = InvariantSpec(
        expression=_comparison(
            _field_ref("duration_minutes"), InvariantComparisonKind.GT, _literal(0)
        ),
        message="zzz",
    )
    assert clerk_invariant_speech(inv) == "zzz"


def test_create_without_message_is_clerk_not_generic() -> None:
    inv = InvariantSpec(
        expression=_comparison(
            _field_ref("duration_minutes"), InvariantComparisonKind.GT, _literal(0)
        )
    )
    try:
        check_invariants_for_create([inv], {"duration_minutes": 0}, entity="TestSession")
    except InvariantViolationError as exc:
        assert str(exc) == "Duration Minutes > 0"
        assert "duration_minutes" not in str(exc)
        assert "Invariant constraint violated" not in str(exc)
        assert exc.entity == "TestSession"
        assert render_invariant_expr(exc.invariant.expression) == "duration_minutes > 0"
    else:
        raise AssertionError("expected InvariantViolationError")


def test_htmx_invariant_is_clerk_not_schema() -> None:
    speech = clerk_invariant_speech(
        InvariantSpec(
            expression=_comparison(
                _field_ref("duration_minutes"), InvariantComparisonKind.GT, _literal(0)
            )
        )
    )
    resp = json_or_htmx_error(
        _request("POST"),
        [{"loc": [], "msg": speech}],
        error_type="invariant_violation",
    )
    body = bytes(resp.body).decode()
    assert "Duration Minutes" in body
    assert "&gt; 0" in body
    assert "duration_minutes" not in body
    assert "Invariant constraint violated" not in body


def test_json_api_invariant_stays_identifier() -> None:
    expr = _comparison(_field_ref("duration_minutes"), InvariantComparisonKind.GT, _literal(0))
    inv = InvariantSpec(expression=expr)
    speech = clerk_invariant_speech(inv)
    resp = json_or_htmx_error(
        _request("POST", htmx=False),
        [{"loc": [], "msg": speech, "invariant": render_invariant_expr(expr)}],
        error_type="invariant_violation",
    )
    text = bytes(resp.body).decode()
    assert "Duration Minutes > 0" in text
    assert "duration_minutes" in text
    assert speech == "Duration Minutes > 0"
