"""Tests for the Dazzle typed expression language.

Covers:
- Tokenizer: all token types, edge cases
- Parser: precedence, all node types, error handling
- Evaluator: arithmetic, comparison, logic, functions, null handling
- Type checker: type inference and compatibility
"""

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from dazzle.core.expression_lang.evaluator import ExpressionEvalError, evaluate
from dazzle.core.expression_lang.parser import ExpressionParseError, parse_expr
from dazzle.core.expression_lang.tokenizer import ExpressionTokenError, TokenKind, tokenize
from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    Expr,
    FieldRef,
    FuncCall,
    IfExpr,
    InExpr,
    Literal,
    UnaryExpr,
    UnaryOp,
)
from dazzle.i18n.display_locale import calendar_today

# ============================================================================
# Tokenizer tests
# ============================================================================


class TestTokenizer:
    """Tokenizer produces correct token sequences."""

    @pytest.mark.parametrize(
        ("source", "expected_kind", "expected_value"),
        [
            ("42", TokenKind.INT, "42"),
            ("3.14", TokenKind.FLOAT, "3.14"),
            ('"hello"', TokenKind.STRING, "hello"),
            ("'world'", TokenKind.STRING, "world"),
            ('"he\\"llo"', None, 'he"llo'),
        ],
        ids=[
            "test_integer",
            "test_float",
            "test_string_double_quotes",
            "test_string_single_quotes",
            "test_string_escape",
        ],
    )
    def test_first_token(self, source, expected_kind, expected_value) -> None:
        tokens = tokenize(source)
        if expected_kind is not None:
            assert tokens[0].kind == expected_kind
        assert tokens[0].value == expected_value

    @pytest.mark.parametrize(
        ("source", "expected_kinds"),
        [
            (
                "true false null and or not in is if elif else",
                [
                    TokenKind.TRUE,
                    TokenKind.FALSE,
                    TokenKind.NULL,
                    TokenKind.AND,
                    TokenKind.OR,
                    TokenKind.NOT,
                    TokenKind.IN,
                    TokenKind.IS,
                    TokenKind.IF,
                    TokenKind.ELIF,
                    TokenKind.ELSE,
                    TokenKind.EOF,
                ],
            ),
            (
                "+ - * / % == != < > <= >= ->",
                [
                    TokenKind.PLUS,
                    TokenKind.MINUS,
                    TokenKind.STAR,
                    TokenKind.SLASH,
                    TokenKind.PERCENT,
                    TokenKind.EQ,
                    TokenKind.NE,
                    TokenKind.LT,
                    TokenKind.GT,
                    TokenKind.LE,
                    TokenKind.GE,
                    TokenKind.ARROW,
                    TokenKind.EOF,
                ],
            ),
            (
                "()[],.",
                [
                    TokenKind.LPAREN,
                    TokenKind.RPAREN,
                    TokenKind.LBRACKET,
                    TokenKind.RBRACKET,
                    TokenKind.COMMA,
                    TokenKind.DOT,
                    TokenKind.EOF,
                ],
            ),
        ],
        ids=["test_keywords", "test_operators", "test_punctuation"],
    )
    def test_token_kinds(self, source, expected_kinds) -> None:
        tokens = tokenize(source)
        assert [t.kind for t in tokens] == expected_kinds

    def test_duration_literals(self) -> None:
        for src, expected in [
            ("7d", "7d"),
            ("9m", "9m"),
            ("24h", "24h"),
            ("1y", "1y"),
            ("2w", "2w"),
        ]:
            tokens = tokenize(src)
            assert tokens[0].kind == TokenKind.DURATION
            assert tokens[0].value == expected

    def test_identifier(self) -> None:
        tokens = tokenize("my_field")
        assert tokens[0].kind == TokenKind.IDENT
        assert tokens[0].value == "my_field"

    def test_complex_expression(self) -> None:
        tokens = tokenize("box1 + box2 * 1.2")
        kinds = [t.kind for t in tokens]
        assert kinds == [
            TokenKind.IDENT,
            TokenKind.PLUS,
            TokenKind.IDENT,
            TokenKind.STAR,
            TokenKind.FLOAT,
            TokenKind.EOF,
        ]

    def test_unterminated_string(self) -> None:
        with pytest.raises(ExpressionTokenError, match="Unterminated"):
            tokenize('"hello')

    def test_unexpected_character(self) -> None:
        with pytest.raises(ExpressionTokenError, match="Unexpected"):
            tokenize("@")

    def test_whitespace_handling(self) -> None:
        tokens = tokenize("  a  +  b  ")
        kinds = [t.kind for t in tokens if t.kind != TokenKind.EOF]
        assert kinds == [TokenKind.IDENT, TokenKind.PLUS, TokenKind.IDENT]


# ============================================================================
# Parser tests
# ============================================================================


def _f(*path: str) -> FieldRef:
    return FieldRef(path=list(path))


def _bin(left: Expr, op: BinaryOp, right: Expr) -> BinaryExpr:
    return BinaryExpr(left=left, op=op, right=right)


_A, _B, _C = _f("a"), _f("b"), _f("c")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # ── literals ──
        pytest.param("42", Literal(value=42), id="int"),
        pytest.param("3.14", Literal(value=3.14), id="float"),
        pytest.param('"hello"', Literal(value="hello"), id="string"),
        pytest.param("true", Literal(value=True), id="true"),
        pytest.param("false", Literal(value=False), id="false"),
        pytest.param("null", Literal(value=None), id="null"),
        pytest.param("7d", DurationLiteral(value=7, unit="d"), id="duration-days"),
        pytest.param("9m", DurationLiteral(value=9, unit="m"), id="duration-months"),
        # ── field references ──
        pytest.param("amount", _f("amount"), id="simple-field"),
        pytest.param("contact.name", _f("contact", "name"), id="dotted-field"),
        pytest.param(
            "self->contact->aml_status", _f("self", "contact", "aml_status"), id="arrow-field"
        ),
        pytest.param(
            "order.customer->address.city",
            _f("order", "customer", "address", "city"),
            id="mixed-dot-arrow",
        ),
        # ── arithmetic + precedence ──
        pytest.param("a + b", _bin(_A, BinaryOp.ADD, _B), id="addition"),
        pytest.param("a - b", _bin(_A, BinaryOp.SUB, _B), id="subtraction"),
        pytest.param("a * b", _bin(_A, BinaryOp.MUL, _B), id="multiplication"),
        pytest.param("-x", UnaryExpr(op=UnaryOp.NEG, operand=_f("x")), id="unary-minus"),
        pytest.param(
            "a + b * c", _bin(_A, BinaryOp.ADD, _bin(_B, BinaryOp.MUL, _C)), id="mul-before-add"
        ),
        pytest.param(
            "(a + b) * c",
            _bin(_bin(_A, BinaryOp.ADD, _B), BinaryOp.MUL, _C),
            id="parentheses-override-precedence",
        ),
        pytest.param(
            "a + b + c",
            _bin(_bin(_A, BinaryOp.ADD, _B), BinaryOp.ADD, _C),
            id="chained-addition-left-assoc",
        ),
        # ── comparison ──
        pytest.param(
            'status == "active"',
            _bin(_f("status"), BinaryOp.EQ, Literal(value="active")),
            id="equality",
        ),
        pytest.param("x != 0", _bin(_f("x"), BinaryOp.NE, Literal(value=0)), id="inequality"),
        pytest.param("age < 18", _bin(_f("age"), BinaryOp.LT, Literal(value=18)), id="less-than"),
        pytest.param(
            "score >= 90", _bin(_f("score"), BinaryOp.GE, Literal(value=90)), id="greater-equal"
        ),
        pytest.param(
            "name is null", _bin(_f("name"), BinaryOp.EQ, Literal(value=None)), id="is-null"
        ),
        pytest.param(
            "name is not null",
            _bin(_f("name"), BinaryOp.NE, Literal(value=None)),
            id="is-not-null",
        ),
        # ── logic + precedence ──
        pytest.param("a and b", _bin(_A, BinaryOp.AND, _B), id="and"),
        pytest.param("a or b", _bin(_A, BinaryOp.OR, _B), id="or"),
        pytest.param("not x", UnaryExpr(op=UnaryOp.NOT, operand=_f("x")), id="not"),
        pytest.param(
            "a or b and c", _bin(_A, BinaryOp.OR, _bin(_B, BinaryOp.AND, _C)), id="and-before-or"
        ),
        pytest.param(
            'x > 0 and y == "ok"',
            _bin(
                _bin(_f("x"), BinaryOp.GT, Literal(value=0)),
                BinaryOp.AND,
                _bin(_f("y"), BinaryOp.EQ, Literal(value="ok")),
            ),
            id="comparison-and-logic",
        ),
    ],
)
def test_parse_tree(source: str, expected: Expr) -> None:
    """Parser builds the exact IR tree. Compared via repr because pydantic
    ``==`` conflates ``True`` with ``1`` and ``42`` with ``42.0``."""
    assert repr(parse_expr(source)) == repr(expected)


class TestParserIn:
    """Parser handles 'in' and 'not in' expressions."""

    def test_in_list(self) -> None:
        expr = parse_expr('status in ["open", "pending"]')
        assert isinstance(expr, InExpr)
        assert not expr.negated
        assert len(expr.items) == 2

    def test_not_in_list(self) -> None:
        expr = parse_expr('status not in ["closed", "archived"]')
        assert isinstance(expr, InExpr)
        assert expr.negated

    def test_in_with_numbers(self) -> None:
        expr = parse_expr("priority in [1, 2, 3]")
        assert isinstance(expr, InExpr)
        assert len(expr.items) == 3


class TestParserFuncCall:
    """Parser handles function calls."""

    def test_no_args(self) -> None:
        expr = parse_expr("today()")
        assert isinstance(expr, FuncCall)
        assert expr.name == "today"
        assert expr.args == []

    def test_single_arg(self) -> None:
        expr = parse_expr("days_until(due_date)")
        assert isinstance(expr, FuncCall)
        assert expr.name == "days_until"
        assert len(expr.args) == 1
        assert isinstance(expr.args[0], FieldRef)

    def test_multiple_args(self) -> None:
        expr = parse_expr('concat(first_name, " ", last_name)')
        assert isinstance(expr, FuncCall)
        assert expr.name == "concat"
        assert len(expr.args) == 3

    def test_nested_func_call(self) -> None:
        expr = parse_expr("abs(x - y)")
        assert isinstance(expr, FuncCall)
        assert expr.name == "abs"
        assert isinstance(expr.args[0], BinaryExpr)


class TestParserIfExpr:
    """Parser handles conditional expressions."""

    def test_simple_if_else(self) -> None:
        expr = parse_expr('if active: "yes" else: "no"')
        assert isinstance(expr, IfExpr)
        assert isinstance(expr.condition, FieldRef)
        assert isinstance(expr.then_expr, Literal)
        assert expr.then_expr.value == "yes"
        assert isinstance(expr.else_expr, Literal)
        assert expr.else_expr.value == "no"

    def test_if_elif_else(self) -> None:
        expr = parse_expr('if x > 10: "high" elif x > 5: "mid" else: "low"')
        assert isinstance(expr, IfExpr)
        assert len(expr.elif_branches) == 1

    def test_multiple_elif(self) -> None:
        expr = parse_expr(
            'if days < 0: "red" elif days < 7: "amber" elif days < 30: "yellow" else: "green"'
        )
        assert isinstance(expr, IfExpr)
        assert len(expr.elif_branches) == 2


class TestParserErrors:
    """Parser produces clear errors for invalid expressions."""

    def test_missing_closing_paren(self) -> None:
        with pytest.raises(ExpressionParseError, match="Expected"):
            parse_expr("(a + b")

    def test_trailing_operator(self) -> None:
        with pytest.raises(ExpressionParseError):
            parse_expr("a +")

    def test_empty_expression(self) -> None:
        with pytest.raises(ExpressionParseError):
            parse_expr("")

    def test_missing_else(self) -> None:
        with pytest.raises(ExpressionParseError, match="Expected"):
            parse_expr('if x: "yes"')

    def test_unexpected_token(self) -> None:
        with pytest.raises(ExpressionParseError):
            parse_expr("a + + b")


# ============================================================================
# Evaluator tests
# ============================================================================


class TestEvalArithmetic:
    """Evaluator handles arithmetic correctly."""

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected"),
        [
            ("a + b", {"a": 10, "b": 20}, 30),
            ("a - b", {"a": 50, "b": 20}, 30),
            ("a * b", {"a": 5, "b": 4}, 20),
            ("a / b", {"a": 10, "b": 4}, 2.5),
            ("a % b", {"a": 10, "b": 3}, 1),
            ("a + b * c", {"a": 2, "b": 3, "c": 4}, 14),  # precedence
            ("(a + b) * c", {"a": 2, "b": 3, "c": 4}, 20),  # parentheses
            ("-x", {"x": 5}, -5),
            # Real-world: VAT 9-box calculation
            ("box1 + box2 - box4", {"box1": 1000, "box2": 200, "box4": 350}, 850),
            ('a + " " + b', {"a": "hello", "b": "world"}, "hello world"),
        ],
        ids=[
            "addition",
            "subtraction",
            "multiplication",
            "division",
            "modulo",
            "precedence",
            "parentheses",
            "unary_minus",
            "vat_box",
            "string_concat",
        ],
    )
    def test_arithmetic(self, expr_str, ctx, expected) -> None:
        assert evaluate(parse_expr(expr_str), ctx) == expected

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected"),
        [
            ("a * b", {"a": 3.5, "b": 2.0}, 7.0),
            ("a + b", {"a": 1, "b": 0.5}, 1.5),
        ],
        ids=["float_mul", "int_plus_float_promotes"],
    )
    def test_arithmetic_approx(self, expr_str, ctx, expected) -> None:
        """Float arithmetic: pinned with pytest.approx for IEEE-754 wobble."""
        assert evaluate(parse_expr(expr_str), ctx) == pytest.approx(expected)

    def test_division_by_zero(self) -> None:
        with pytest.raises(ExpressionEvalError, match="Division by zero"):
            evaluate(parse_expr("x / y"), {"x": 10, "y": 0})


class TestEvalComparison:
    """Evaluator handles comparison operators."""

    @pytest.mark.parametrize(
        ("expr_str", "ctx_true", "ctx_false"),
        [
            ('status == "active"', {"status": "active"}, {"status": "closed"}),
            ("x != 0", {"x": 5}, {"x": 0}),
            ("age < 18", {"age": 16}, {"age": 25}),
            ("score >= 90", {"score": 90}, {"score": 89}),
            ("x is null", {"x": None}, {"x": 5}),
            ("x is not null", {"x": 5}, {"x": None}),
            # Membership: 'in' / 'not in'
            ('status in ["open", "pending"]', {"status": "open"}, {"status": "closed"}),
            ('status not in ["closed", "archived"]', {"status": "open"}, {"status": "closed"}),
            ("priority in [1, 2, 3]", {"priority": 2}, {"priority": 5}),
        ],
        ids=[
            "equality",
            "inequality",
            "less_than",
            "greater_equal",
            "null_equality",
            "null_inequality",
            "in_string_list",
            "not_in",
            "in_number_list",
        ],
    )
    def test_comparison(self, expr_str, ctx_true, ctx_false) -> None:
        """Comparison and membership predicates: True for one ctx, False for another."""
        expr = parse_expr(expr_str)
        assert evaluate(expr, ctx_true) is True
        assert evaluate(expr, ctx_false) is False

    def test_null_comparison_returns_false(self) -> None:
        """Comparison against null returns False (3-valued logic short-circuit)."""
        assert evaluate(parse_expr("x > 0"), {"x": None}) is False


class TestEvalLogic:
    """Evaluator handles logical operators with short-circuit."""

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected"),
        [
            ("a and b", {"a": True, "b": True}, True),
            ("a and b", {"a": False, "b": True}, False),
            ("a or b", {"a": False, "b": True}, True),
            ("a or b", {"a": False, "b": False}, False),
            ("not x", {"x": False}, True),
            ("not x", {"x": True}, False),
            # Compound: comparison + logic
            ('age >= 18 and status == "active"', {"age": 25, "status": "active"}, True),
        ],
        ids=[
            "and_true",
            "and_false",
            "or_true",
            "or_false",
            "not_false",
            "not_true",
            "compound",
        ],
    )
    def test_logic(self, expr_str, ctx, expected) -> None:
        assert evaluate(parse_expr(expr_str), ctx) is expected


class TestEvalFunctions:
    """Evaluator handles built-in functions."""

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected"),
        [
            # Stringy
            ('concat(first, " ", last)', {"first": "John", "last": "Doe"}, "John Doe"),
            ("concat(a, b)", {"a": "hello", "b": None}, "hello"),  # null skipped
            # Sequence/length
            ("len(items)", {"items": [1, 2, 3]}, 3),
            ("len(items)", {"items": None}, 0),
            # Numeric
            ("abs(x)", {"x": -5}, 5),
            ("abs(x)", {"x": 5}, 5),
            ("min(a, b, c)", {"a": 3, "b": 1, "c": 2}, 1),
            ("max(a, b, c)", {"a": 3, "b": 1, "c": 2}, 3),
            ("round(x)", {"x": 3.7}, 4),
            # Coalesce: first non-null
            ("coalesce(a, b, c)", {"a": None, "b": None, "c": 42}, 42),
            ("coalesce(a, b, c)", {"a": None, "b": 10, "c": 42}, 10),
            ("coalesce(a, b)", {"a": None, "b": None}, None),
        ],
        ids=[
            "concat_strings",
            "concat_skips_null",
            "len_list",
            "len_null",
            "abs_negative",
            "abs_positive",
            "min_three",
            "max_three",
            "round_default",
            "coalesce_third",
            "coalesce_second",
            "coalesce_all_null",
        ],
    )
    def test_function_call(self, expr_str, ctx, expected) -> None:
        assert evaluate(parse_expr(expr_str), ctx) == expected

    def test_round_with_digits(self) -> None:
        """Float result needs pytest.approx for IEEE-754 wobble."""
        assert evaluate(parse_expr("round(x, 2)"), {"x": 3.14159}) == pytest.approx(3.14)

    def test_today(self) -> None:
        result = evaluate(parse_expr("today()"), {})
        assert result == calendar_today()

    def test_now(self) -> None:
        result = evaluate(parse_expr("now()"), {})
        assert isinstance(result, datetime)

    @pytest.mark.parametrize(
        ("expr_str", "offset_days", "expected"),
        [
            pytest.param("days_since(d)", -10, 10, id="days_since"),
            pytest.param("days_until(d)", 5, 5, id="days_until"),
        ],
    )
    def test_days_relative_to_today(self, expr_str: str, offset_days: int, expected: int) -> None:
        d = calendar_today() + timedelta(days=offset_days)
        assert evaluate(parse_expr(expr_str), {"d": d}) == expected

    def test_days_null_returns_null(self) -> None:
        assert evaluate(parse_expr("days_until(due)"), {"due": None}) is None

    def test_unknown_function(self) -> None:
        with pytest.raises(ExpressionEvalError, match="Unknown function"):
            evaluate(parse_expr("unknown_fn()"), {})


@pytest.mark.parametrize(
    ("expr_str", "start", "expected"),
    [
        pytest.param("start + 7d", date(2026, 1, 1), date(2026, 1, 8), id="date-plus-days"),
        pytest.param("start - 3d", date(2026, 1, 15), date(2026, 1, 12), id="date-minus-days"),
        # 9m ≈ 270 days
        pytest.param(
            "start + 9m",
            date(2026, 1, 1),
            date(2026, 1, 1) + timedelta(days=270),
            id="date-plus-months",
        ),
    ],
)
def test_date_plus_duration(expr_str: str, start: date, expected: date) -> None:
    """Evaluator handles date + duration arithmetic."""
    assert evaluate(parse_expr(expr_str), {"start": start}) == expected


class TestEvalIfExpr:
    """Evaluator handles conditional expressions."""

    def test_simple_if_true(self) -> None:
        expr = parse_expr('if active: "yes" else: "no"')
        assert evaluate(expr, {"active": True}) == "yes"

    def test_simple_if_false(self) -> None:
        expr = parse_expr('if active: "yes" else: "no"')
        assert evaluate(expr, {"active": False}) == "no"

    def test_if_elif_else(self) -> None:
        expr = parse_expr('if x > 10: "high" elif x > 5: "mid" else: "low"')
        assert evaluate(expr, {"x": 15}) == "high"
        assert evaluate(expr, {"x": 7}) == "mid"
        assert evaluate(expr, {"x": 3}) == "low"

    def test_urgency_calculation(self) -> None:
        """Real-world: compliance deadline RAG status."""
        expr = parse_expr('if days < 0: "red" elif days < 7: "amber" else: "green"')
        assert evaluate(expr, {"days": -1}) == "red"
        assert evaluate(expr, {"days": 3}) == "amber"
        assert evaluate(expr, {"days": 30}) == "green"


class TestEvalFieldRef:
    """Evaluator resolves field references correctly."""

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected"),
        [
            pytest.param("amount", {"amount": 100}, 100, id="simple_field"),
            pytest.param(
                "contact.name",
                {"contact": {"name": "John", "email": "john@example.com"}},
                "John",
                id="nested_dict",
            ),
            pytest.param(
                "self.contact.address.city",
                {"self": {"contact": {"address": {"city": "London"}}}},
                "London",
                id="deep_nested",
            ),
        ],
    )
    def test_resolves(self, expr_str: str, ctx: dict[str, Any], expected: Any) -> None:
        assert evaluate(parse_expr(expr_str), ctx) == expected

    def test_missing_field_returns_none(self) -> None:
        assert evaluate(parse_expr("missing"), {}) is None

    def test_missing_nested(self) -> None:
        assert evaluate(parse_expr("a.b.c"), {"a": {"x": 1}}) is None


class TestEvalNullHandling:
    """Evaluator handles null correctly throughout."""

    def test_null_arithmetic_propagates(self) -> None:
        assert evaluate(parse_expr("x + 1"), {"x": None}) is None

    def test_null_negation(self) -> None:
        assert evaluate(parse_expr("-x"), {"x": None}) is None

    def test_null_equality(self) -> None:
        assert evaluate(parse_expr("x == null"), {"x": None}) is True
        assert evaluate(parse_expr("x == null"), {"x": 5}) is False

    def test_null_in_coalesce(self) -> None:
        expr = parse_expr("coalesce(x, 0)")
        assert evaluate(expr, {"x": None}) == 0
        assert evaluate(expr, {"x": 42}) == 42


# ============================================================================
# Integration / real-world expression tests
# ============================================================================


class TestRealWorldExpressions:
    """End-to-end tests with real-world DSL-inspired expressions."""

    def test_vat_9box_calculation(self) -> None:
        """box3 = box1 + box2; box5 = box3 - box4"""
        ctx = {"box1": 1500, "box2": 300, "box4": 600}
        box3 = evaluate(parse_expr("box1 + box2"), ctx)
        assert box3 == 1800
        ctx["box3"] = box3
        box5 = evaluate(parse_expr("box3 - box4"), ctx)
        assert box5 == 1200

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected"),
        [
            pytest.param(
                "(current_tasks * 100) / max_tasks",
                {"current_tasks": 7, "max_tasks": 10},
                pytest.approx(70.0),
                id="utilization_percentage",
            ),
            # Default value for missing field.
            pytest.param(
                "coalesce(nickname, first_name, email)",
                {"nickname": None, "first_name": None, "email": "j@ex.com"},
                "j@ex.com",
                id="coalesce_with_default",
            ),
            # Round a computed percentage.
            pytest.param(
                "round(completed * 100 / total, 1)",
                {"completed": 7, "total": 9},
                pytest.approx(77.8),
                id="nested_arithmetic_with_function",
            ),
        ],
    )
    def test_computed_value(self, expr_str: str, ctx: dict[str, Any], expected: Any) -> None:
        assert evaluate(parse_expr(expr_str), ctx) == expected

    @pytest.mark.parametrize(
        ("expr_str", "ctx"),
        [
            pytest.param(
                'self.signatory.aml_status == "completed"',
                {"self": {"signatory": {"aml_status": "completed"}}},
                id="cross_entity_guard",
            ),
            pytest.param(
                'aml_status == "completed" and status == "viewed"',
                {"status": "viewed", "aml_status": "completed"},
                id="compound_guard",
            ),
            # Process guard with stage check.
            pytest.param(
                'stage in ["business_details", "complete"]',
                {"stage": "business_details"},
                id="status_in_list",
            ),
        ],
    )
    def test_guard_passes(self, expr_str: str, ctx: dict[str, Any]) -> None:
        assert evaluate(parse_expr(expr_str), ctx) is True
