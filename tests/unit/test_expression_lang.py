"""Tests for the Dazzle typed expression language.

Covers:
- Tokenizer: all token types, edge cases
- Parser: precedence, all node types, error handling
- Evaluator: arithmetic, comparison, logic, functions, null handling
- Type checker: type inference and compatibility
"""

from datetime import date, datetime, timedelta

import pytest

from dazzle.core.expression_lang.evaluator import ExpressionEvalError, evaluate
from dazzle.core.expression_lang.parser import ExpressionParseError, parse_expr
from dazzle.core.expression_lang.tokenizer import ExpressionTokenError, TokenKind, tokenize
from dazzle.core.expression_lang.type_checker import infer_type
from dazzle.core.ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    ExprType,
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


class TestParserLiterals:
    """Parser handles all literal types."""

    def test_integer(self) -> None:
        expr = parse_expr("42")
        assert isinstance(expr, Literal)
        assert expr.value == 42

    def test_float(self) -> None:
        expr = parse_expr("3.14")
        assert isinstance(expr, Literal)
        assert expr.value == 3.14

    def test_string(self) -> None:
        expr = parse_expr('"hello"')
        assert isinstance(expr, Literal)
        assert expr.value == "hello"

    def test_true(self) -> None:
        expr = parse_expr("true")
        assert isinstance(expr, Literal)
        assert expr.value is True

    def test_false(self) -> None:
        expr = parse_expr("false")
        assert isinstance(expr, Literal)
        assert expr.value is False

    def test_null(self) -> None:
        expr = parse_expr("null")
        assert isinstance(expr, Literal)
        assert expr.value is None

    def test_duration(self) -> None:
        expr = parse_expr("7d")
        assert isinstance(expr, DurationLiteral)
        assert expr.value == 7
        assert expr.unit == "d"

    def test_duration_months(self) -> None:
        expr = parse_expr("9m")
        assert isinstance(expr, DurationLiteral)
        assert expr.value == 9
        assert expr.unit == "m"


class TestParserFieldRef:
    """Parser handles field references."""

    def test_simple_field(self) -> None:
        expr = parse_expr("amount")
        assert isinstance(expr, FieldRef)
        assert expr.path == ["amount"]

    def test_dotted_field(self) -> None:
        expr = parse_expr("contact.name")
        assert isinstance(expr, FieldRef)
        assert expr.path == ["contact", "name"]

    def test_arrow_field(self) -> None:
        expr = parse_expr("self->contact->aml_status")
        assert isinstance(expr, FieldRef)
        assert expr.path == ["self", "contact", "aml_status"]

    def test_mixed_dot_arrow(self) -> None:
        expr = parse_expr("order.customer->address.city")
        assert isinstance(expr, FieldRef)
        assert expr.path == ["order", "customer", "address", "city"]


class TestParserArithmetic:
    """Parser handles arithmetic with correct precedence."""

    def test_addition(self) -> None:
        expr = parse_expr("a + b")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.ADD

    def test_subtraction(self) -> None:
        expr = parse_expr("a - b")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.SUB

    def test_multiplication(self) -> None:
        expr = parse_expr("a * b")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.MUL

    def test_mul_before_add(self) -> None:
        # a + b * c should be a + (b * c)
        expr = parse_expr("a + b * c")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.ADD
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == BinaryOp.MUL

    def test_parentheses_override_precedence(self) -> None:
        # (a + b) * c
        expr = parse_expr("(a + b) * c")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.MUL
        assert isinstance(expr.left, BinaryExpr)
        assert expr.left.op == BinaryOp.ADD

    def test_unary_minus(self) -> None:
        expr = parse_expr("-x")
        assert isinstance(expr, UnaryExpr)
        assert expr.op == UnaryOp.NEG

    def test_chained_addition(self) -> None:
        # a + b + c is (a + b) + c (left-associative)
        expr = parse_expr("a + b + c")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.ADD
        assert isinstance(expr.left, BinaryExpr)
        assert expr.left.op == BinaryOp.ADD


class TestParserComparison:
    """Parser handles comparison operators."""

    @pytest.mark.parametrize(
        ("source", "expected_op"),
        [
            ('status == "active"', BinaryOp.EQ),
            ("x != 0", BinaryOp.NE),
            ("age < 18", BinaryOp.LT),
            ("score >= 90", BinaryOp.GE),
        ],
        ids=["test_equality", "test_inequality", "test_less_than", "test_greater_equal"],
    )
    def test_comparison_operator(self, source: str, expected_op: BinaryOp) -> None:
        expr = parse_expr(source)
        assert isinstance(expr, BinaryExpr)
        assert expr.op == expected_op

    def test_is_null(self) -> None:
        expr = parse_expr("name is null")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.EQ
        assert isinstance(expr.right, Literal)
        assert expr.right.value is None

    def test_is_not_null(self) -> None:
        expr = parse_expr("name is not null")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.NE
        assert isinstance(expr.right, Literal)
        assert expr.right.value is None


class TestParserLogic:
    """Parser handles logical operators with correct precedence."""

    def test_and(self) -> None:
        expr = parse_expr("a and b")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.AND

    def test_or(self) -> None:
        expr = parse_expr("a or b")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.OR

    def test_not(self) -> None:
        expr = parse_expr("not x")
        assert isinstance(expr, UnaryExpr)
        assert expr.op == UnaryOp.NOT

    def test_and_before_or(self) -> None:
        # a or b and c should be a or (b and c)
        expr = parse_expr("a or b and c")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.OR
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == BinaryOp.AND

    def test_comparison_and_logic(self) -> None:
        expr = parse_expr('x > 0 and y == "ok"')
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.AND
        assert isinstance(expr.left, BinaryExpr)
        assert expr.left.op == BinaryOp.GT
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == BinaryOp.EQ


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
        ],
        ids=[
            "equality",
            "inequality",
            "less_than",
            "greater_equal",
            "null_equality",
            "null_inequality",
        ],
    )
    def test_comparison(self, expr_str, ctx_true, ctx_false) -> None:
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


class TestEvalIn:
    """Evaluator handles 'in' and 'not in'."""

    def test_in_string_list(self) -> None:
        expr = parse_expr('status in ["open", "pending"]')
        assert evaluate(expr, {"status": "open"}) is True
        assert evaluate(expr, {"status": "closed"}) is False

    def test_not_in(self) -> None:
        expr = parse_expr('status not in ["closed", "archived"]')
        assert evaluate(expr, {"status": "open"}) is True
        assert evaluate(expr, {"status": "closed"}) is False

    def test_in_number_list(self) -> None:
        expr = parse_expr("priority in [1, 2, 3]")
        assert evaluate(expr, {"priority": 2}) is True
        assert evaluate(expr, {"priority": 5}) is False


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

    def test_days_since(self) -> None:
        past = calendar_today() - timedelta(days=10)
        result = evaluate(parse_expr("days_since(created)"), {"created": past})
        assert result == 10

    def test_days_until(self) -> None:
        future = calendar_today() + timedelta(days=5)
        result = evaluate(parse_expr("days_until(due)"), {"due": future})
        assert result == 5

    def test_days_null_returns_null(self) -> None:
        assert evaluate(parse_expr("days_until(due)"), {"due": None}) is None

    def test_unknown_function(self) -> None:
        with pytest.raises(ExpressionEvalError, match="Unknown function"):
            evaluate(parse_expr("unknown_fn()"), {})


class TestEvalDateArithmetic:
    """Evaluator handles date + duration arithmetic."""

    def test_date_plus_days(self) -> None:
        d = date(2026, 1, 1)
        result = evaluate(parse_expr("start + 7d"), {"start": d})
        assert result == date(2026, 1, 8)

    def test_date_minus_days(self) -> None:
        d = date(2026, 1, 15)
        result = evaluate(parse_expr("due - 3d"), {"due": d})
        assert result == date(2026, 1, 12)

    def test_date_plus_months(self) -> None:
        d = date(2026, 1, 1)
        result = evaluate(parse_expr("start + 9m"), {"start": d})
        # 9m ≈ 270 days
        assert result == d + timedelta(days=270)


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

    def test_simple_field(self) -> None:
        assert evaluate(parse_expr("amount"), {"amount": 100}) == 100

    def test_missing_field_returns_none(self) -> None:
        assert evaluate(parse_expr("missing"), {}) is None

    def test_nested_dict(self) -> None:
        ctx = {"contact": {"name": "John", "email": "john@example.com"}}
        assert evaluate(parse_expr("contact.name"), ctx) == "John"

    def test_deep_nested(self) -> None:
        ctx = {"self": {"contact": {"address": {"city": "London"}}}}
        assert evaluate(parse_expr("self.contact.address.city"), ctx) == "London"

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
# Type checker tests
# ============================================================================


class TestTypeInference:
    """Type checker infers expression types correctly."""

    @pytest.mark.parametrize(
        ("expr_str", "ctx", "expected_type"),
        [
            # Literals (no context needed)
            ("42", {}, ExprType.INT),
            ("3.14", {}, ExprType.FLOAT),
            ('"hello"', {}, ExprType.STR),
            ("true", {}, ExprType.BOOL),
            ("null", {}, ExprType.NULL),
            ("7d", {}, ExprType.DURATION),
            # Field references resolve through context (or default to ANY)
            ("amount", {"amount": ExprType.MONEY}, ExprType.MONEY),
            ("amount", {}, ExprType.ANY),
            # Arithmetic propagates / promotes type
            ("a + b", {"a": ExprType.INT, "b": ExprType.INT}, ExprType.INT),
            ("a + b", {"a": ExprType.INT, "b": ExprType.FLOAT}, ExprType.FLOAT),
            ("price + tax", {"price": ExprType.MONEY, "tax": ExprType.MONEY}, ExprType.MONEY),
            ("price * qty", {"price": ExprType.MONEY, "qty": ExprType.INT}, ExprType.MONEY),
            ("a / b", {"a": ExprType.INT, "b": ExprType.INT}, ExprType.FLOAT),
            ("a + b", {"a": ExprType.STR, "b": ExprType.STR}, ExprType.STR),
            # Boolean-producing ops
            ("x > 0", {}, ExprType.BOOL),
            ("x == y", {}, ExprType.BOOL),
            ("a and b", {}, ExprType.BOOL),
            ("not x", {}, ExprType.BOOL),
            ("x in [1, 2]", {}, ExprType.BOOL),
            # Date arithmetic
            ("start + 7d", {"start": ExprType.DATE}, ExprType.DATE),
            ("a - b", {"a": ExprType.DATE, "b": ExprType.DATE}, ExprType.DURATION),
            # Built-in functions
            ("today()", {}, ExprType.DATE),
            ("days_until(x)", {}, ExprType.INT),
            ("concat(a, b)", {}, ExprType.STR),
            # If-expression returns the type of its branches
            ('if x: "yes" else: "no"', {}, ExprType.STR),
            # abs() preserves operand type
            ("abs(x)", {"x": ExprType.MONEY}, ExprType.MONEY),
        ],
        ids=[
            "int_literal",
            "float_literal",
            "string_literal",
            "bool_literal",
            "null_literal",
            "duration_literal",
            "field_with_ctx",
            "field_without_ctx",
            "int_plus_int",
            "int_plus_float_promotes",
            "money_plus_money",
            "money_times_int",
            "int_div_int_returns_float",
            "str_concat",
            "comparison_gt",
            "comparison_eq",
            "logic_and",
            "logic_not",
            "in_list",
            "date_plus_duration",
            "date_minus_date",
            "today_returns_date",
            "days_until_returns_int",
            "concat_returns_str",
            "if_returns_branch_type",
            "abs_preserves_type",
        ],
    )
    def test_infer_type(self, expr_str, ctx, expected_type) -> None:
        assert infer_type(parse_expr(expr_str), ctx) == expected_type


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

    def test_utilization_percentage(self) -> None:
        """(current_tasks * 100) / max_tasks"""
        ctx = {"current_tasks": 7, "max_tasks": 10}
        result = evaluate(parse_expr("(current_tasks * 100) / max_tasks"), ctx)
        assert result == pytest.approx(70.0)

    def test_compliance_deadline_rag(self) -> None:
        """Classify deadline urgency."""
        expr = parse_expr(
            'if days_remaining < 0: "red" elif days_remaining < 7: "amber" else: "green"'
        )
        assert evaluate(expr, {"days_remaining": -1}) == "red"
        assert evaluate(expr, {"days_remaining": 3}) == "amber"
        assert evaluate(expr, {"days_remaining": 30}) == "green"

    def test_cross_entity_guard(self) -> None:
        """Guard: self->signatory->aml_status == "completed" """
        ctx = {
            "self": {
                "signatory": {
                    "aml_status": "completed",
                }
            }
        }
        expr = parse_expr('self.signatory.aml_status == "completed"')
        assert evaluate(expr, ctx) is True

    def test_compound_guard(self) -> None:
        """Multiple conditions combined."""
        ctx = {"status": "viewed", "aml_status": "completed"}
        expr = parse_expr('aml_status == "completed" and status == "viewed"')
        assert evaluate(expr, ctx) is True

    def test_status_in_list(self) -> None:
        """Process guard with stage check."""
        ctx = {"stage": "business_details"}
        expr = parse_expr('stage in ["business_details", "complete"]')
        assert evaluate(expr, ctx) is True

    def test_coalesce_with_default(self) -> None:
        """Default value for missing field."""
        expr = parse_expr("coalesce(nickname, first_name, email)")
        ctx = {"nickname": None, "first_name": None, "email": "j@ex.com"}
        assert evaluate(expr, ctx) == "j@ex.com"

    def test_nested_arithmetic_with_function(self) -> None:
        """Round a computed percentage."""
        ctx = {"completed": 7, "total": 9}
        expr = parse_expr("round(completed * 100 / total, 1)")
        result = evaluate(expr, ctx)
        assert result == pytest.approx(77.8)
