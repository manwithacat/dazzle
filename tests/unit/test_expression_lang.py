"""Tests for the Dazzle typed expression language.

Covers:
- Tokenizer: all token types, edge cases
- Parser: precedence, all node types, error handling
- Evaluator: arithmetic, comparison, logic, functions, null handling
- Type checker: type inference and compatibility
"""

from __future__ import annotations

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

# ============================================================================
# Tokenizer tests
# ============================================================================


class TestTokenizer:
    """Tokenizer produces correct token sequences."""

    def test_integer(self) -> None:
        tokens = tokenize("42")
        assert tokens[0].kind == TokenKind.INT
        assert tokens[0].value == "42"

    def test_float(self) -> None:
        tokens = tokenize("3.14")
        assert tokens[0].kind == TokenKind.FLOAT
        assert tokens[0].value == "3.14"

    def test_string_double_quotes(self) -> None:
        tokens = tokenize('"hello"')
        assert tokens[0].kind == TokenKind.STRING
        assert tokens[0].value == "hello"

    def test_string_single_quotes(self) -> None:
        tokens = tokenize("'world'")
        assert tokens[0].kind == TokenKind.STRING
        assert tokens[0].value == "world"

    def test_string_escape(self) -> None:
        tokens = tokenize('"he\\"llo"')
        assert tokens[0].value == 'he"llo'

    def test_keywords(self) -> None:
        source = "true false null and or not in is if elif else"
        tokens = tokenize(source)
        expected = [
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
        ]
        assert [t.kind for t in tokens] == expected

    def test_operators(self) -> None:
        source = "+ - * / % == != < > <= >= ->"
        tokens = tokenize(source)
        expected_kinds = [
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
        ]
        assert [t.kind for t in tokens] == expected_kinds

    def test_punctuation(self) -> None:
        source = "()[],."
        tokens = tokenize(source)
        expected = [
            TokenKind.LPAREN,
            TokenKind.RPAREN,
            TokenKind.LBRACKET,
            TokenKind.RBRACKET,
            TokenKind.COMMA,
            TokenKind.DOT,
            TokenKind.EOF,
        ]
        assert [t.kind for t in tokens] == expected

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

    def test_equality(self) -> None:
        expr = parse_expr('status == "active"')
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.EQ

    def test_inequality(self) -> None:
        expr = parse_expr("x != 0")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.NE

    def test_less_than(self) -> None:
        expr = parse_expr("age < 18")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.LT

    def test_greater_equal(self) -> None:
        expr = parse_expr("score >= 90")
        assert isinstance(expr, BinaryExpr)
        assert expr.op == BinaryOp.GE

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

    def test_addition(self) -> None:
        assert evaluate(parse_expr("a + b"), {"a": 10, "b": 20}) == 30

    def test_subtraction(self) -> None:
        assert evaluate(parse_expr("a - b"), {"a": 50, "b": 20}) == 30

    def test_multiplication(self) -> None:
        assert evaluate(parse_expr("a * b"), {"a": 5, "b": 4}) == 20

    def test_division(self) -> None:
        assert evaluate(parse_expr("a / b"), {"a": 10, "b": 4}) == 2.5

    def test_modulo(self) -> None:
        assert evaluate(parse_expr("a % b"), {"a": 10, "b": 3}) == 1

    def test_precedence(self) -> None:
        # a + b * c = 2 + 3 * 4 = 14
        assert evaluate(parse_expr("a + b * c"), {"a": 2, "b": 3, "c": 4}) == 14

    def test_parentheses(self) -> None:
        # (a + b) * c = (2 + 3) * 4 = 20
        assert evaluate(parse_expr("(a + b) * c"), {"a": 2, "b": 3, "c": 4}) == 20

    def test_unary_minus(self) -> None:
        assert evaluate(parse_expr("-x"), {"x": 5}) == -5

    def test_division_by_zero(self) -> None:
        with pytest.raises(ExpressionEvalError, match="Division by zero"):
            evaluate(parse_expr("x / y"), {"x": 10, "y": 0})

    def test_float_arithmetic(self) -> None:
        result = evaluate(parse_expr("a * b"), {"a": 3.5, "b": 2.0})
        assert result == pytest.approx(7.0)

    def test_mixed_int_float(self) -> None:
        result = evaluate(parse_expr("a + b"), {"a": 1, "b": 0.5})
        assert result == pytest.approx(1.5)

    def test_vat_box_arithmetic(self) -> None:
        """Real-world: VAT 9-box calculation."""
        ctx = {"box1": 1000, "box2": 200, "box4": 350}
        result = evaluate(parse_expr("box1 + box2 - box4"), ctx)
        assert result == 850

    def test_string_concatenation(self) -> None:
        result = evaluate(parse_expr('a + " " + b'), {"a": "hello", "b": "world"})
        assert result == "hello world"


class TestEvalComparison:
    """Evaluator handles comparison operators."""

    def test_equality(self) -> None:
        assert evaluate(parse_expr('status == "active"'), {"status": "active"}) is True
        assert evaluate(parse_expr('status == "active"'), {"status": "closed"}) is False

    def test_inequality(self) -> None:
        assert evaluate(parse_expr("x != 0"), {"x": 5}) is True
        assert evaluate(parse_expr("x != 0"), {"x": 0}) is False

    def test_less_than(self) -> None:
        assert evaluate(parse_expr("age < 18"), {"age": 16}) is True
        assert evaluate(parse_expr("age < 18"), {"age": 25}) is False

    def test_greater_equal(self) -> None:
        assert evaluate(parse_expr("score >= 90"), {"score": 90}) is True
        assert evaluate(parse_expr("score >= 90"), {"score": 89}) is False

    def test_null_equality(self) -> None:
        assert evaluate(parse_expr("x is null"), {"x": None}) is True
        assert evaluate(parse_expr("x is null"), {"x": 5}) is False

    def test_null_inequality(self) -> None:
        assert evaluate(parse_expr("x is not null"), {"x": 5}) is True
        assert evaluate(parse_expr("x is not null"), {"x": None}) is False

    def test_null_comparison_returns_false(self) -> None:
        assert evaluate(parse_expr("x > 0"), {"x": None}) is False


class TestEvalLogic:
    """Evaluator handles logical operators with short-circuit."""

    def test_and_true(self) -> None:
        assert evaluate(parse_expr("a and b"), {"a": True, "b": True}) is True

    def test_and_false(self) -> None:
        assert evaluate(parse_expr("a and b"), {"a": False, "b": True}) is False

    def test_or_true(self) -> None:
        assert evaluate(parse_expr("a or b"), {"a": False, "b": True}) is True

    def test_or_false(self) -> None:
        assert evaluate(parse_expr("a or b"), {"a": False, "b": False}) is False

    def test_not(self) -> None:
        assert evaluate(parse_expr("not x"), {"x": False}) is True
        assert evaluate(parse_expr("not x"), {"x": True}) is False

    def test_compound_logic(self) -> None:
        ctx = {"age": 25, "status": "active"}
        result = evaluate(parse_expr('age >= 18 and status == "active"'), ctx)
        assert result is True


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

    def test_concat(self) -> None:
        expr = parse_expr('concat(first, " ", last)')
        result = evaluate(expr, {"first": "John", "last": "Doe"})
        assert result == "John Doe"

    def test_concat_with_null(self) -> None:
        expr = parse_expr("concat(a, b)")
        result = evaluate(expr, {"a": "hello", "b": None})
        assert result == "hello"

    def test_len(self) -> None:
        expr = parse_expr("len(items)")
        assert evaluate(expr, {"items": [1, 2, 3]}) == 3

    def test_len_null(self) -> None:
        assert evaluate(parse_expr("len(items)"), {"items": None}) == 0

    def test_abs(self) -> None:
        assert evaluate(parse_expr("abs(x)"), {"x": -5}) == 5
        assert evaluate(parse_expr("abs(x)"), {"x": 5}) == 5

    def test_min(self) -> None:
        assert evaluate(parse_expr("min(a, b, c)"), {"a": 3, "b": 1, "c": 2}) == 1

    def test_max(self) -> None:
        assert evaluate(parse_expr("max(a, b, c)"), {"a": 3, "b": 1, "c": 2}) == 3

    def test_round(self) -> None:
        assert evaluate(parse_expr("round(x, 2)"), {"x": 3.14159}) == pytest.approx(3.14)

    def test_round_no_digits(self) -> None:
        assert evaluate(parse_expr("round(x)"), {"x": 3.7}) == 4

    def test_coalesce(self) -> None:
        expr = parse_expr("coalesce(a, b, c)")
        assert evaluate(expr, {"a": None, "b": None, "c": 42}) == 42
        assert evaluate(expr, {"a": None, "b": 10, "c": 42}) == 10

    def test_coalesce_all_null(self) -> None:
        expr = parse_expr("coalesce(a, b)")
        assert evaluate(expr, {"a": None, "b": None}) is None

    def test_today(self) -> None:
        result = evaluate(parse_expr("today()"), {})
        assert result == date.today()

    def test_now(self) -> None:
        result = evaluate(parse_expr("now()"), {})
        assert isinstance(result, datetime)

    def test_days_since(self) -> None:
        past = date.today() - timedelta(days=10)
        result = evaluate(parse_expr("days_since(created)"), {"created": past})
        assert result == 10

    def test_days_until(self) -> None:
        future = date.today() + timedelta(days=5)
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

    def test_int_literal(self) -> None:
        assert infer_type(parse_expr("42")) == ExprType.INT

    def test_float_literal(self) -> None:
        assert infer_type(parse_expr("3.14")) == ExprType.FLOAT

    def test_string_literal(self) -> None:
        assert infer_type(parse_expr('"hello"')) == ExprType.STR

    def test_bool_literal(self) -> None:
        assert infer_type(parse_expr("true")) == ExprType.BOOL

    def test_null_literal(self) -> None:
        assert infer_type(parse_expr("null")) == ExprType.NULL

    def test_duration(self) -> None:
        assert infer_type(parse_expr("7d")) == ExprType.DURATION

    def test_field_with_context(self) -> None:
        assert infer_type(parse_expr("amount"), {"amount": ExprType.MONEY}) == ExprType.MONEY

    def test_field_without_context(self) -> None:
        assert infer_type(parse_expr("amount")) == ExprType.ANY

    def test_int_addition(self) -> None:
        ctx = {"a": ExprType.INT, "b": ExprType.INT}
        assert infer_type(parse_expr("a + b"), ctx) == ExprType.INT

    def test_float_wins_over_int(self) -> None:
        ctx = {"a": ExprType.INT, "b": ExprType.FLOAT}
        assert infer_type(parse_expr("a + b"), ctx) == ExprType.FLOAT

    def test_money_arithmetic(self) -> None:
        ctx = {"price": ExprType.MONEY, "tax": ExprType.MONEY}
        assert infer_type(parse_expr("price + tax"), ctx) == ExprType.MONEY

    def test_money_times_scalar(self) -> None:
        ctx = {"price": ExprType.MONEY, "qty": ExprType.INT}
        assert infer_type(parse_expr("price * qty"), ctx) == ExprType.MONEY

    def test_division_returns_float(self) -> None:
        ctx = {"a": ExprType.INT, "b": ExprType.INT}
        assert infer_type(parse_expr("a / b"), ctx) == ExprType.FLOAT

    def test_comparison_returns_bool(self) -> None:
        assert infer_type(parse_expr("x > 0")) == ExprType.BOOL
        assert infer_type(parse_expr("x == y")) == ExprType.BOOL

    def test_logic_returns_bool(self) -> None:
        assert infer_type(parse_expr("a and b")) == ExprType.BOOL
        assert infer_type(parse_expr("not x")) == ExprType.BOOL

    def test_in_returns_bool(self) -> None:
        assert infer_type(parse_expr("x in [1, 2]")) == ExprType.BOOL

    def test_date_plus_duration(self) -> None:
        ctx = {"start": ExprType.DATE}
        assert infer_type(parse_expr("start + 7d"), ctx) == ExprType.DATE

    def test_date_minus_date(self) -> None:
        ctx = {"a": ExprType.DATE, "b": ExprType.DATE}
        assert infer_type(parse_expr("a - b"), ctx) == ExprType.DURATION

    def test_string_concat(self) -> None:
        ctx = {"a": ExprType.STR, "b": ExprType.STR}
        assert infer_type(parse_expr("a + b"), ctx) == ExprType.STR

    def test_today_returns_date(self) -> None:
        assert infer_type(parse_expr("today()")) == ExprType.DATE

    def test_days_until_returns_int(self) -> None:
        assert infer_type(parse_expr("days_until(x)")) == ExprType.INT

    def test_concat_returns_str(self) -> None:
        assert infer_type(parse_expr("concat(a, b)")) == ExprType.STR

    def test_if_returns_then_type(self) -> None:
        assert infer_type(parse_expr('if x: "yes" else: "no"')) == ExprType.STR

    def test_abs_preserves_type(self) -> None:
        ctx = {"x": ExprType.MONEY}
        assert infer_type(parse_expr("abs(x)"), ctx) == ExprType.MONEY


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
