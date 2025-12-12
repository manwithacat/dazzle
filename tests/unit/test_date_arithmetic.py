"""
Tests for date arithmetic feature (v0.10.2).

Tests cover:
- Lexer: TODAY, NOW, DURATION_LITERAL tokens
- Parser: Field defaults, conditions, invariants
- Backend spec: Serialization of date expressions
- Runtime: Evaluation with default_factory
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from dazzle.core.dsl_parser_impl import Parser, parse_dsl
from dazzle.core.ir import (
    DateArithmeticExpr,
    DateArithmeticOp,
    DateLiteral,
    DateLiteralKind,
    DurationUnit,
)
from dazzle.core.lexer import Lexer, TokenType
from dazzle_dnr_back.converters.entity_converter import convert_entity
from dazzle_dnr_back.runtime.model_generator import _create_date_factory

# =============================================================================
# Lexer Tests
# =============================================================================


class TestLexerDateTokens:
    """Test lexer tokenization of date-related tokens."""

    def test_today_token(self):
        """TODAY is tokenized as keyword."""
        tokens = Lexer("today", Path("test.dsl")).tokenize()
        assert tokens[0].type == TokenType.TODAY
        assert tokens[0].value == "today"

    def test_now_token(self):
        """NOW is tokenized as keyword."""
        tokens = Lexer("now", Path("test.dsl")).tokenize()
        assert tokens[0].type == TokenType.NOW
        assert tokens[0].value == "now"

    def test_duration_literals(self):
        """Duration literals (7d, 24h, 30min, 2w, 3m, 1y) are tokenized."""
        test_cases = [
            ("7d", "7d"),
            ("24h", "24h"),
            ("30min", "30min"),
            ("2w", "2w"),
            ("3m", "3m"),
            ("1y", "1y"),
        ]
        for text, expected in test_cases:
            tokens = Lexer(text, Path("test.dsl")).tokenize()
            assert tokens[0].type == TokenType.DURATION_LITERAL
            assert tokens[0].value == expected

    def test_date_expression_tokens(self):
        """Full date expression tokenizes correctly."""
        tokens = Lexer("today + 7d", Path("test.dsl")).tokenize()
        assert tokens[0].type == TokenType.TODAY
        assert tokens[1].type == TokenType.PLUS
        assert tokens[2].type == TokenType.DURATION_LITERAL
        assert tokens[2].value == "7d"

    def test_new_duration_unit_keywords(self):
        """New duration unit keywords (weeks, months, years) are tokenized."""
        for keyword in ["weeks", "months", "years"]:
            tokens = Lexer(keyword, Path("test.dsl")).tokenize()
            assert tokens[0].type.value == keyword


# =============================================================================
# Parser Tests - Field Defaults
# =============================================================================


class TestParserFieldDefaults:
    """Test parsing date expressions as field defaults."""

    def _parse(self, dsl: str):
        """Helper to parse DSL and return fragment."""
        return parse_dsl(dsl, Path("test.dsl"))

    def test_today_literal_default(self):
        """Field with 'today' as default."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    created_date: date = today
"""
        _, _, _, _, _, fragment = self._parse(dsl)
        entity = fragment.entities[0]
        field = next(f for f in entity.fields if f.name == "created_date")
        assert isinstance(field.default, DateLiteral)
        assert field.default.kind == DateLiteralKind.TODAY

    def test_now_literal_default(self):
        """Field with 'now' as default."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    created_at: datetime = now
"""
        _, _, _, _, _, fragment = self._parse(dsl)
        entity = fragment.entities[0]
        field = next(f for f in entity.fields if f.name == "created_at")
        assert isinstance(field.default, DateLiteral)
        assert field.default.kind == DateLiteralKind.NOW

    def test_today_plus_days_default(self):
        """Field with 'today + 7d' as default."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    due_date: date = today + 7d
"""
        _, _, _, _, _, fragment = self._parse(dsl)
        entity = fragment.entities[0]
        field = next(f for f in entity.fields if f.name == "due_date")
        assert isinstance(field.default, DateArithmeticExpr)
        assert field.default.operator == DateArithmeticOp.ADD
        assert field.default.right.value == 7
        assert field.default.right.unit == DurationUnit.DAYS

    def test_now_minus_hours_default(self):
        """Field with 'now - 24h' as default."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    reminder_at: datetime = now - 24h
"""
        _, _, _, _, _, fragment = self._parse(dsl)
        entity = fragment.entities[0]
        field = next(f for f in entity.fields if f.name == "reminder_at")
        assert isinstance(field.default, DateArithmeticExpr)
        assert field.default.operator == DateArithmeticOp.SUBTRACT
        assert field.default.right.value == 24
        assert field.default.right.unit == DurationUnit.HOURS

    def test_all_duration_units(self):
        """Test all duration units in field defaults."""
        units_dsl = {
            "minutes": "30min",
            "hours": "24h",
            "days": "7d",
            "weeks": "2w",
            "months": "3m",
            "years": "1y",
        }
        for unit_name, duration_str in units_dsl.items():
            dsl = f"""
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    test_date: date = today + {duration_str}
"""
            _, _, _, _, _, fragment = self._parse(dsl)
            entity = fragment.entities[0]
            field = next(f for f in entity.fields if f.name == "test_date")
            assert isinstance(field.default, DateArithmeticExpr)
            assert field.default.right.unit == DurationUnit(unit_name)


# =============================================================================
# Parser Tests - Conditions
# =============================================================================


class TestParserConditions:
    """Test parsing date expressions in conditions."""

    def test_condition_with_date_expr(self):
        """Condition using date expression."""
        parser = Parser("due_date < today + 7d", Path("test.dsl"))
        lexer = Lexer("due_date < today + 7d", Path("test.dsl"))
        parser.tokens = lexer.tokenize()
        parser.pos = 0

        result = parser.parse_condition_expr()
        assert result.comparison is not None
        assert result.comparison.field == "due_date"
        assert result.comparison.value.date_expr is not None
        assert isinstance(result.comparison.value.date_expr, DateArithmeticExpr)

    def test_condition_with_today_literal(self):
        """Condition using just 'today'."""
        parser = Parser("created_date = today", Path("test.dsl"))
        lexer = Lexer("created_date = today", Path("test.dsl"))
        parser.tokens = lexer.tokenize()
        parser.pos = 0

        result = parser.parse_condition_expr()
        assert result.comparison is not None
        assert result.comparison.value.date_expr is not None
        assert isinstance(result.comparison.value.date_expr, DateLiteral)


# =============================================================================
# Parser Tests - Invariants
# =============================================================================


class TestParserInvariants:
    """Test parsing date expressions in invariants."""

    def test_invariant_with_compact_duration(self):
        """Invariant using compact duration syntax."""
        parser = Parser("duration <= 2w", Path("test.dsl"))
        lexer = Lexer("duration <= 2w", Path("test.dsl"))
        parser.tokens = lexer.tokenize()
        parser.pos = 0

        result = parser._parse_invariant_expr()
        assert str(result) == "(duration <= 2 weeks)"

    def test_invariant_with_verbose_duration(self):
        """Invariant using verbose duration syntax (14 days)."""
        parser = Parser("duration <= 14 days", Path("test.dsl"))
        lexer = Lexer("duration <= 14 days", Path("test.dsl"))
        parser.tokens = lexer.tokenize()
        parser.pos = 0

        result = parser._parse_invariant_expr()
        assert str(result) == "(duration <= 14 days)"


# =============================================================================
# Backend Spec Conversion Tests
# =============================================================================


class TestBackendSpecConversion:
    """Test conversion of date expressions to backend spec format."""

    def _parse_and_convert(self, dsl: str):
        """Parse DSL and convert entity to backend spec."""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]
        return convert_entity(entity)

    def test_today_literal_serialization(self):
        """DateLiteral(today) serializes to dict."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    created_date: date = today
"""
        backend_entity = self._parse_and_convert(dsl)
        field = next(f for f in backend_entity.fields if f.name == "created_date")
        assert field.default == {"kind": "today"}

    def test_date_arithmetic_serialization(self):
        """DateArithmeticExpr serializes to dict with all fields."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    due_date: date = today + 7d
"""
        backend_entity = self._parse_and_convert(dsl)
        field = next(f for f in backend_entity.fields if f.name == "due_date")
        assert field.default == {
            "kind": "today",
            "op": "+",
            "value": 7,
            "unit": "days",
        }


# =============================================================================
# Runtime Evaluation Tests
# =============================================================================


class TestRuntimeEvaluation:
    """Test runtime evaluation of date expressions."""

    def test_today_factory(self):
        """Factory for 'today' returns current date."""
        factory = _create_date_factory({"kind": "today"})
        result = factory()
        assert result == date.today()

    def test_now_factory(self):
        """Factory for 'now' returns current datetime (within tolerance)."""
        factory = _create_date_factory({"kind": "now"})
        before = datetime.now()
        result = factory()
        after = datetime.now()
        assert before <= result <= after

    def test_today_plus_days(self):
        """Factory for 'today + 7d' returns date 7 days from now."""
        factory = _create_date_factory({
            "kind": "today",
            "op": "+",
            "value": 7,
            "unit": "days",
        })
        result = factory()
        expected = date.today() + timedelta(days=7)
        assert result == expected

    def test_now_minus_hours(self):
        """Factory for 'now - 24h' returns datetime 24 hours ago."""
        factory = _create_date_factory({
            "kind": "now",
            "op": "-",
            "value": 24,
            "unit": "hours",
        })
        result = factory()
        # Allow 1 second tolerance
        expected = datetime.now() - timedelta(hours=24)
        assert abs((result - expected).total_seconds()) < 1

    def test_weeks_arithmetic(self):
        """Factory handles weeks correctly."""
        factory = _create_date_factory({
            "kind": "today",
            "op": "+",
            "value": 2,
            "unit": "weeks",
        })
        result = factory()
        expected = date.today() + timedelta(weeks=2)
        assert result == expected

    def test_minutes_arithmetic(self):
        """Factory handles minutes correctly."""
        factory = _create_date_factory({
            "kind": "now",
            "op": "+",
            "value": 30,
            "unit": "minutes",
        })
        result = factory()
        expected = datetime.now() + timedelta(minutes=30)
        # Allow 1 second tolerance
        assert abs((result - expected).total_seconds()) < 1

    def test_months_arithmetic(self):
        """Factory handles months (using relativedelta if available)."""
        factory = _create_date_factory({
            "kind": "today",
            "op": "+",
            "value": 3,
            "unit": "months",
        })
        result = factory()
        # Just verify it returns a date in the future
        assert result > date.today()
        # And roughly 3 months away (between 80-100 days)
        days_diff = (result - date.today()).days
        assert 80 < days_diff < 100

    def test_years_arithmetic(self):
        """Factory handles years (using relativedelta if available)."""
        factory = _create_date_factory({
            "kind": "today",
            "op": "+",
            "value": 1,
            "unit": "years",
        })
        result = factory()
        # Just verify it returns a date in the future
        assert result > date.today()
        # And roughly 1 year away (between 360-370 days)
        days_diff = (result - date.today()).days
        assert 360 < days_diff < 370


# =============================================================================
# Integration Tests
# =============================================================================


class TestEndToEnd:
    """End-to-end tests for date arithmetic feature."""

    def test_full_pipeline(self):
        """Test complete pipeline: DSL -> Parse -> Convert -> Evaluate."""
        dsl = """
module test
app Test "Test"

entity Task "Task":
    id: uuid pk
    title: str(200) required
    created_at: datetime = now
    due_date: date = today + 7d
"""
        # Parse
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = fragment.entities[0]

        # Verify IR types
        created_field = next(f for f in entity.fields if f.name == "created_at")
        due_field = next(f for f in entity.fields if f.name == "due_date")
        assert isinstance(created_field.default, DateLiteral)
        assert isinstance(due_field.default, DateArithmeticExpr)

        # Convert to backend spec
        backend_entity = convert_entity(entity)

        # Verify serialization
        backend_created = next(f for f in backend_entity.fields if f.name == "created_at")
        backend_due = next(f for f in backend_entity.fields if f.name == "due_date")
        assert backend_created.default == {"kind": "now"}
        assert backend_due.default == {
            "kind": "today",
            "op": "+",
            "value": 7,
            "unit": "days",
        }

        # Verify runtime evaluation
        created_factory = _create_date_factory(backend_created.default)
        due_factory = _create_date_factory(backend_due.default)

        created_result = created_factory()
        due_result = due_factory()

        # created_at should be ~now
        assert isinstance(created_result, datetime)
        assert abs((created_result - datetime.now()).total_seconds()) < 1

        # due_date should be today + 7 days
        assert isinstance(due_result, date)
        assert due_result == date.today() + timedelta(days=7)
