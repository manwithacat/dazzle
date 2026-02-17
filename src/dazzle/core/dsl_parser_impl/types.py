"""
Type parsing for DAZZLE DSL.

Handles field type specifications and field modifiers.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType

if TYPE_CHECKING:
    from ..ir.expressions import Expr as _Expr

# Type alias for default values (scalars or date expressions)
DefaultValue = str | int | float | bool | ir.DateLiteral | ir.DateArithmeticExpr | None

# Duration suffix to DurationUnit mapping
DURATION_SUFFIX_MAP = {
    "min": ir.DurationUnit.MINUTES,
    "h": ir.DurationUnit.HOURS,
    "d": ir.DurationUnit.DAYS,
    "w": ir.DurationUnit.WEEKS,
    "m": ir.DurationUnit.MONTHS,
    "y": ir.DurationUnit.YEARS,
}


class TypeParserMixin:
    """
    Mixin providing type and field modifier parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        peek_token: Any
        collect_line_as_expr: Any
        file: Any
        _is_keyword_as_identifier: Any

    def parse_type_spec(self) -> ir.FieldType:
        """
        Parse field type specification.

        Examples:
            str(200)
            decimal(10,2)
            enum[draft,issued,paid]
            ref Client
        """
        token = self.current_token()

        # str(N)
        if token.value == "str":
            self.advance()
            self.expect(TokenType.LPAREN)
            max_len = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=max_len)

        # text
        elif token.value == "text":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.TEXT)

        # int
        elif token.value == "int":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.INT)

        # decimal(P,S)
        elif token.value == "decimal":
            self.advance()
            self.expect(TokenType.LPAREN)
            precision = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.COMMA)
            scale = int(self.expect(TokenType.NUMBER).value)
            self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=precision, scale=scale)

        # bool
        elif token.value == "bool":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.BOOL)

        # date
        elif token.value == "date":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.DATE)

        # datetime
        elif token.value == "datetime":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.DATETIME)

        # uuid
        elif token.value == "uuid":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.UUID)

        # email
        elif token.value == "email":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.EMAIL)

        # json (v0.9.4)
        elif token.value == "json":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.JSON)

        # money or money(CURRENCY) (v0.9.5)
        elif token.value == "money":
            self.advance()
            currency_code = "GBP"  # Default to GBP for UK focus
            if self.match(TokenType.LPAREN):
                self.advance()
                # Currency code as identifier (e.g., USD, EUR, GBP)
                currency_code = self.expect_identifier_or_keyword().value.upper()
                self.expect(TokenType.RPAREN)
            return ir.FieldType(kind=ir.FieldTypeKind.MONEY, currency_code=currency_code)

        # file (v0.9.5)
        elif token.value == "file":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.FILE)

        # url (v0.9.5)
        elif token.value == "url":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.URL)

        # timezone (v0.10.3) - IANA timezone identifier
        elif token.value == "timezone":
            self.advance()
            return ir.FieldType(kind=ir.FieldTypeKind.TIMEZONE)

        # enum[val1,val2,...]
        elif token.value == "enum":
            self.advance()
            self.expect(TokenType.LBRACKET)

            values = []
            values.append(self.expect_identifier_or_keyword().value)

            while self.match(TokenType.COMMA):
                self.advance()
                values.append(self.expect_identifier_or_keyword().value)

            self.expect(TokenType.RBRACKET)
            return ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=values)

        # ref EntityName
        elif token.value == "ref":
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=entity_name)

        # v0.7.1: has_many EntityName [via JunctionEntity] [cascade|restrict|nullify] [readonly]
        elif token.type == TokenType.HAS_MANY:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value

            # v0.9.5: Optional via junction entity for many-to-many
            via_entity = None
            if self.match(TokenType.VIA):
                self.advance()
                via_entity = self.expect(TokenType.IDENTIFIER).value

            behavior, readonly = self._parse_relationship_modifiers()
            return ir.FieldType(
                kind=ir.FieldTypeKind.HAS_MANY,
                ref_entity=entity_name,
                via_entity=via_entity,
                relationship_behavior=behavior,
                readonly=readonly,
            )

        # v0.7.1: has_one EntityName [cascade|restrict] [readonly]
        elif token.type == TokenType.HAS_ONE:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            behavior, readonly = self._parse_relationship_modifiers()
            return ir.FieldType(
                kind=ir.FieldTypeKind.HAS_ONE,
                ref_entity=entity_name,
                relationship_behavior=behavior,
                readonly=readonly,
            )

        # v0.7.1: embeds EntityName
        elif token.type == TokenType.EMBEDS:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.EMBEDS, ref_entity=entity_name)

        # v0.7.1: belongs_to EntityName
        elif token.type == TokenType.BELONGS_TO:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            return ir.FieldType(kind=ir.FieldTypeKind.BELONGS_TO, ref_entity=entity_name)

        else:
            raise make_parse_error(
                f"Unknown type: {token.value}",
                self.file,
                token.line,
                token.column,
            )

    def _parse_relationship_modifiers(
        self,
    ) -> tuple[ir.RelationshipBehavior | None, bool]:
        """Parse optional relationship modifiers (cascade, restrict, nullify, readonly)."""
        behavior: ir.RelationshipBehavior | None = None
        readonly = False

        # Check for behavior modifier
        if self.match(TokenType.CASCADE):
            self.advance()
            behavior = ir.RelationshipBehavior.CASCADE
        elif self.match(TokenType.RESTRICT):
            self.advance()
            behavior = ir.RelationshipBehavior.RESTRICT
        elif self.match(TokenType.NULLIFY):
            self.advance()
            behavior = ir.RelationshipBehavior.NULLIFY

        # Check for readonly modifier
        if self.match(TokenType.READONLY):
            self.advance()
            readonly = True

        return behavior, readonly

    def _parse_duration_literal(self) -> ir.DurationLiteral:
        """
        Parse a duration literal from DURATION_LITERAL token (e.g., 7d, 24h, 30min).

        Returns:
            DurationLiteral with value and unit
        """
        token = self.expect(TokenType.DURATION_LITERAL)
        value_str = token.value

        # Extract numeric part and suffix
        import re

        match = re.match(r"(\d+)(min|h|d|w|m|y)", value_str)
        if not match:
            raise make_parse_error(
                f"Invalid duration literal: {value_str}",
                self.file,
                token.line,
                token.column,
            )

        value = int(match.group(1))
        suffix = match.group(2)
        unit = DURATION_SUFFIX_MAP[suffix]

        return ir.DurationLiteral(value=value, unit=unit)

    def _parse_date_expr(self) -> ir.DateLiteral | ir.DateArithmeticExpr:
        """
        Parse a date expression.

        Handles:
            - today (DateLiteral)
            - now (DateLiteral)
            - today + 7d (DateArithmeticExpr)
            - now - 24h (DateArithmeticExpr)

        Returns:
            DateLiteral or DateArithmeticExpr
        """
        # Parse the base (today or now)
        if self.match(TokenType.TODAY):
            self.advance()
            base = ir.DateLiteral(kind=ir.DateLiteralKind.TODAY)
        elif self.match(TokenType.NOW):
            self.advance()
            base = ir.DateLiteral(kind=ir.DateLiteralKind.NOW)
        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected 'today' or 'now', got {token.value}",
                self.file,
                token.line,
                token.column,
            )

        # Check for arithmetic operator
        if self.match(TokenType.PLUS):
            self.advance()
            duration = self._parse_duration_literal()
            return ir.DateArithmeticExpr(
                left=base,
                operator=ir.DateArithmeticOp.ADD,
                right=duration,
            )
        elif self.match(TokenType.MINUS):
            self.advance()
            duration = self._parse_duration_literal()
            return ir.DateArithmeticExpr(
                left=base,
                operator=ir.DateArithmeticOp.SUBTRACT,
                right=duration,
            )

        # Just a literal (today or now)
        return base

    def parse_field_modifiers(
        self,
    ) -> tuple[list[ir.FieldModifier], DefaultValue, "_Expr | None"]:
        """
        Parse field modifiers and default value.

        Returns:
            Tuple of (modifiers, default_value, default_expr)

        v0.10.2: default can now be a date expression (DateLiteral, DateArithmeticExpr)
        v0.29.0: default_expr for typed expression defaults (e.g., = box1 + box2)
        """
        modifiers = []
        default: DefaultValue = None
        default_expr: _Expr | None = None

        while True:
            token = self.current_token()

            if token.value == "required":
                self.advance()
                modifiers.append(ir.FieldModifier.REQUIRED)
            elif token.value == "optional":
                self.advance()
                modifiers.append(ir.FieldModifier.OPTIONAL)
            elif token.value == "pk":
                self.advance()
                modifiers.append(ir.FieldModifier.PK)
            elif token.value == "unique":
                self.advance()
                if self.match(TokenType.QUESTION):
                    self.advance()
                    modifiers.append(ir.FieldModifier.UNIQUE_NULLABLE)
                else:
                    modifiers.append(ir.FieldModifier.UNIQUE)
            elif token.value == "auto_add":
                self.advance()
                modifiers.append(ir.FieldModifier.AUTO_ADD)
            elif token.value == "auto_update":
                self.advance()
                modifiers.append(ir.FieldModifier.AUTO_UPDATE)
            elif token.value == "sensitive":
                self.advance()
                modifiers.append(ir.FieldModifier.SENSITIVE)
            elif self.match(TokenType.EQUALS):
                # default=value
                self.advance()
                # v0.29.0: Check if this is a typed expression (identifier followed
                # by an operator, or function call)
                if self._is_expression_default():
                    default_expr = self.collect_line_as_expr()
                # v0.10.2: Check for date expressions first (today, now)
                elif self.match(TokenType.TODAY) or self.match(TokenType.NOW):
                    default = self._parse_date_expr()
                elif self.match(TokenType.STRING):
                    default = self.advance().value
                elif self.match(TokenType.NUMBER):
                    num_str = self.advance().value
                    default = float(num_str) if "." in num_str else int(num_str)
                elif self.match(TokenType.TRUE):
                    self.advance()
                    default = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    default = False
                elif self.match(TokenType.IDENTIFIER):
                    # Could be enum value or boolean (for backwards compatibility)
                    val = self.advance().value
                    if val in ("true", "false"):
                        default = val == "true"
                    else:
                        default = val
                elif self._is_keyword_as_identifier():
                    # v0.9.1: Allow keywords as default enum values
                    # e.g., status: enum[draft,submitted,approved]=submitted
                    default = self.advance().value
                else:
                    # v0.14.1: Provide helpful error for invalid default values
                    err_token = self.current_token()
                    operator_tokens = {
                        TokenType.SLASH,
                        TokenType.STAR,
                        TokenType.PLUS,
                        TokenType.MINUS,
                        TokenType.COLON,
                        TokenType.COMMA,
                        TokenType.DOT,
                        TokenType.ARROW,
                    }
                    if err_token.type in operator_tokens:
                        raise make_parse_error(
                            f"Invalid default value - unexpected '{err_token.value}'.\n"
                            f"  If the default contains special characters, use quotes:\n"
                            f'  Example: mime_type: str(100)="application/pdf"',
                            self.file,
                            err_token.line,
                            err_token.column,
                        )
                    raise make_parse_error(
                        f"Invalid default value: {err_token.value}",
                        self.file,
                        err_token.line,
                        err_token.column,
                    )
            else:
                break

        return modifiers, default, default_expr

    def _is_expression_default(self) -> bool:
        """Check if the default value starting at current position is a typed expression.

        An expression default is detected when an identifier (or keyword-as-identifier)
        is followed by an arithmetic/comparison operator or '(' (function call).
        """
        _EXPR_OPERATORS = {
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
            TokenType.DOUBLE_EQUALS,
            TokenType.NOT_EQUALS,
            TokenType.GREATER_THAN,
            TokenType.LESS_THAN,
            TokenType.GREATER_EQUAL,
            TokenType.LESS_EQUAL,
            TokenType.DOT,
            TokenType.ARROW,
        }
        is_ident = self.match(TokenType.IDENTIFIER) or self._is_keyword_as_identifier()
        if not is_ident:
            # Check for 'if' keyword (conditional expression)
            return bool(self.current_token().value == "if")

        # Identifier followed by operator → expression
        next_tok = self.peek_token()
        if next_tok.type in _EXPR_OPERATORS:
            return True
        # Identifier followed by '(' → function call
        if next_tok.type == TokenType.LPAREN:
            return True
        # Identifier followed by 'and', 'or', 'in', 'is', 'not' → expression
        if next_tok.type in (
            TokenType.AND,
            TokenType.OR,
            TokenType.IN,
            TokenType.IS,
            TokenType.NOT,
        ):
            return True
        return False

    def _parse_field_spec(self) -> ir.FieldSpec:
        """Parse a single field: ``name: type [modifiers] [=default]``.

        Shared across entity, archetype, foreign_model, and stream schema
        parsers.  The caller is responsible for the surrounding loop and
        INDENT/DEDENT handling.
        """
        field_name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        field_type = self.parse_type_spec()
        modifiers, default, default_expr = self.parse_field_modifiers()
        return ir.FieldSpec(
            name=field_name,
            type=field_type,
            modifiers=modifiers,
            default=default,
            default_expr=default_expr,
        )

    def _parse_field_path(self) -> list[str]:
        """
        Parse a field path like 'field' or 'relation.field' or 'relation.subrelation.field'.

        Returns a list of path components.
        """
        path = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.DOT):
            self.advance()
            path.append(self.expect_identifier_or_keyword().value)

        return path

    def _parse_literal_value(self) -> str | int | float | bool | None:
        """Parse a literal value (string, number, boolean, null, or dotted path).

        Supports:
            - String literals: "hello"
            - Numbers: 42, 3.14
            - Booleans: true, false
            - Null: null, None
            - Identifiers: current_user, draft
            - Dotted paths: current_user.team_id, current_user.contact_id
        """
        if self.match(TokenType.STRING):
            return str(self.advance().value)
        elif self.match(TokenType.NUMBER):
            num_str = self.advance().value
            if "." in num_str:
                return float(num_str)
            return int(num_str)
        elif self.match(TokenType.TRUE):
            self.advance()
            return True
        elif self.match(TokenType.FALSE):
            self.advance()
            return False
        elif self.match(TokenType.IDENTIFIER):
            val = self.current_token().value
            if val == "null" or val == "None":
                self.advance()
                return None
            # Parse identifier, potentially with dotted path (e.g., current_user.team_id)
            result = str(self.advance().value)
            while self.match(TokenType.DOT):
                self.advance()
                next_part = self.expect_identifier_or_keyword().value
                result = f"{result}.{next_part}"
            return result
        else:
            # Allow keywords as values (e.g., enum values)
            if self._is_keyword_as_identifier():
                return str(self.advance().value)
            token = self.current_token()
            raise make_parse_error(
                f"Expected literal value, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )
