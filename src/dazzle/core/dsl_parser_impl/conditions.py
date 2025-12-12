"""
Condition expression parsing for DAZZLE DSL.

Handles conditional expressions, comparisons, and logical operators
used in access rules, visibility, and UX specifications.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class ConditionParserMixin:
    """
    Mixin providing condition expression parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        file: Any
        _parse_literal_value: Any
        _parse_date_expr: Any  # From TypeParserMixin
        _parse_duration_literal: Any  # From TypeParserMixin

    def parse_condition_expr(self) -> ir.ConditionExpr:
        """
        Parse condition expression with full AST.

        Supports:
            - Simple comparisons: field = value, field in [a, b]
            - Function calls: days_since(field) > 30
            - Compound conditions: cond1 and cond2, cond1 or cond2
            - Parenthesized expressions: (cond1 and cond2) or cond3
        """
        return self._parse_or_expr()

    def _parse_or_expr(self) -> ir.ConditionExpr:
        """Parse OR expression (lowest precedence)."""
        left = self._parse_and_expr()

        while self.match(TokenType.OR):
            self.advance()
            right = self._parse_and_expr()
            left = ir.ConditionExpr(
                left=left,
                operator=ir.LogicalOperator.OR,
                right=right,
            )

        return left

    def _parse_and_expr(self) -> ir.ConditionExpr:
        """Parse AND expression."""
        left = self._parse_primary_condition()

        while self.match(TokenType.AND):
            self.advance()
            right = self._parse_primary_condition()
            left = ir.ConditionExpr(
                left=left,
                operator=ir.LogicalOperator.AND,
                right=right,
            )

        return left

    def _parse_primary_condition(self) -> ir.ConditionExpr:
        """Parse primary condition (comparison, role check, or parenthesized expr)."""
        # Handle parentheses
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self._parse_or_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # Handle role(name) - standalone role check (v0.7.0)
        if self.match(TokenType.ROLE):
            self.advance()
            self.expect(TokenType.LPAREN)
            role_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.RPAREN)
            return ir.ConditionExpr(role_check=ir.RoleCheck(role_name=role_name))

        # Parse comparison
        comparison = self._parse_comparison()
        return ir.ConditionExpr(comparison=comparison)

    def _parse_comparison(self) -> ir.Comparison:
        """
        Parse a single comparison.

        Examples:
            field = value
            field in [a, b, c]
            field is null
            days_since(field) > 30
            owner.team = current_team  (v0.7.0 - relationship traversal)
        """
        # Check for function call
        function = None
        field = None

        token = self.current_token()
        if token.type == TokenType.IDENTIFIER:
            name = self.advance().value
            if self.match(TokenType.LPAREN):
                # Function call
                self.advance()
                arg = self.expect_identifier_or_keyword().value
                self.expect(TokenType.RPAREN)
                function = ir.FunctionCall(name=name, argument=arg)
            else:
                # Check for dotted path (owner.team) - v0.7.0
                field = name
                while self.match(TokenType.DOT):
                    self.advance()
                    next_part = self.expect_identifier_or_keyword().value
                    field = f"{field}.{next_part}"
        else:
            # Allow keywords as field names
            field = self.expect_identifier_or_keyword().value
            # Also check for dotted path after keyword field names
            while self.match(TokenType.DOT):
                self.advance()
                next_part = self.expect_identifier_or_keyword().value
                field = f"{field}.{next_part}"

        # Parse operator
        operator = self._parse_comparison_operator()

        # Parse value
        value = self._parse_condition_value()

        return ir.Comparison(
            field=field,
            function=function,
            operator=operator,
            value=value,
        )

    def _parse_comparison_operator(self) -> ir.ComparisonOperator:
        """Parse comparison operator."""
        token = self.current_token()

        if self.match(TokenType.EQUALS):
            self.advance()
            return ir.ComparisonOperator.EQUALS
        elif self.match(TokenType.NOT_EQUALS):
            self.advance()
            return ir.ComparisonOperator.NOT_EQUALS
        elif self.match(TokenType.GREATER_THAN):
            self.advance()
            return ir.ComparisonOperator.GREATER_THAN
        elif self.match(TokenType.LESS_THAN):
            self.advance()
            return ir.ComparisonOperator.LESS_THAN
        elif self.match(TokenType.GREATER_EQUAL):
            self.advance()
            return ir.ComparisonOperator.GREATER_EQUAL
        elif self.match(TokenType.LESS_EQUAL):
            self.advance()
            return ir.ComparisonOperator.LESS_EQUAL
        elif self.match(TokenType.IN):
            self.advance()
            return ir.ComparisonOperator.IN
        elif self.match(TokenType.NOT):
            self.advance()
            if self.match(TokenType.IN):
                self.advance()
                return ir.ComparisonOperator.NOT_IN
            else:
                raise make_parse_error(
                    "Expected 'in' after 'not'",
                    self.file,
                    token.line,
                    token.column,
                )
        elif self.match(TokenType.IS):
            self.advance()
            if self.match(TokenType.NOT):
                self.advance()
                return ir.ComparisonOperator.IS_NOT
            return ir.ComparisonOperator.IS
        else:
            raise make_parse_error(
                f"Expected comparison operator, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def _parse_condition_value(self) -> ir.ConditionValue:
        """
        Parse value in a condition (literal, identifier, list, or date expression).

        v0.10.2: Added support for date expressions (today, now, today + 7d, etc.)
        """
        # List value: [a, b, c]
        if self.match(TokenType.LBRACKET):
            self.advance()
            values: list[str | int | float | bool] = []

            if not self.match(TokenType.RBRACKET):
                val = self._parse_literal_value()
                if val is not None:
                    values.append(val)
                while self.match(TokenType.COMMA):
                    self.advance()
                    val = self._parse_literal_value()
                    if val is not None:
                        values.append(val)

            self.expect(TokenType.RBRACKET)
            return ir.ConditionValue(values=values)

        # v0.10.2: Check for date expressions (today, now)
        if self.match(TokenType.TODAY) or self.match(TokenType.NOW):
            date_expr = self._parse_date_expr()
            return ir.ConditionValue(date_expr=date_expr)

        # Single value
        value = self._parse_literal_value()
        return ir.ConditionValue(literal=value)

    def parse_value(self) -> Any:
        """Parse a value (string, number, identifier, boolean)."""
        token = self.current_token()

        if self.match(TokenType.STRING):
            return self.advance().value

        elif self.match(TokenType.NUMBER):
            value = self.advance().value
            if "." in value:
                return float(value)
            return int(value)

        elif self.match(TokenType.TRUE):
            self.advance()
            return True

        elif self.match(TokenType.FALSE):
            self.advance()
            return False

        elif self.match(TokenType.IDENTIFIER):
            # Could be a variable reference
            return self.advance().value

        else:
            raise make_parse_error(
                f"Expected value, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )
