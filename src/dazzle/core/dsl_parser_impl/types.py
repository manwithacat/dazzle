"""
Type parsing for DAZZLE DSL.

Handles field type specifications and field modifiers.
"""

import re
from collections.abc import Callable
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

# Operator tokens that indicate an invalid default value
_INVALID_DEFAULT_OPERATOR_TOKENS = frozenset(
    {
        TokenType.SLASH,
        TokenType.STAR,
        TokenType.PLUS,
        TokenType.MINUS,
        TokenType.COLON,
        TokenType.COMMA,
        TokenType.DOT,
        TokenType.ARROW,
    }
)

# Tokens that indicate an expression default (after an identifier)
_EXPR_OPERATORS = frozenset(
    {
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
)


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

    # ------------------------------------------------------------------
    # parse_type_spec and sub-parsers
    # ------------------------------------------------------------------

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

        # Dispatch by token value for keyword-style types
        _value_dispatch: dict[str, Callable[[], ir.FieldType]] = {
            "str": self._parse_str_type,
            "text": self._parse_text_type,
            "int": self._parse_int_type,
            "decimal": self._parse_decimal_type,
            "float": self._parse_float_type,
            "bool": self._parse_bool_type,
            "date": self._parse_date_type,
            "datetime": self._parse_datetime_type,
            "uuid": self._parse_uuid_type,
            "email": self._parse_email_type,
            "json": self._parse_json_type,
            "money": self._parse_money_type,
            "file": self._parse_file_type,
            "url": self._parse_url_type,
            "timezone": self._parse_timezone_type,
            "enum": self._parse_enum_type,
            "ref": self._parse_ref_type,
        }

        value_parser = _value_dispatch.get(token.value)
        if value_parser is not None:
            return value_parser()

        # Dispatch by token type for relationship types
        _token_type_dispatch: dict[TokenType, Callable[[], ir.FieldType]] = {
            TokenType.HAS_MANY: self._parse_has_many_type,
            TokenType.HAS_ONE: self._parse_has_one_type,
            TokenType.EMBEDS: self._parse_embeds_type,
            TokenType.BELONGS_TO: self._parse_belongs_to_type,
        }

        token_type_parser = _token_type_dispatch.get(token.type)
        if token_type_parser is not None:
            return token_type_parser()

        if token.type in (TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            raise make_parse_error(
                "Missing field type after ':'.\n"
                "  Expected a type like: str(200), int, bool, date, ref Entity, etc.\n"
                "  Example: name: str(200) required",
                self.file,
                token.line,
                token.column,
            )
        raise make_parse_error(
            f"Unknown type: {token.value!r}",
            self.file,
            token.line,
            token.column,
        )

    def _parse_str_type(self) -> ir.FieldType:
        """Parse str(N) type."""
        self.advance()
        self.expect(TokenType.LPAREN)
        max_len = int(self.expect(TokenType.NUMBER).value)
        self.expect(TokenType.RPAREN)
        return ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=max_len)

    def _parse_text_type(self) -> ir.FieldType:
        """Parse text type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.TEXT)

    def _parse_int_type(self) -> ir.FieldType:
        """Parse int type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.INT)

    def _parse_float_type(self) -> ir.FieldType:
        """Parse float type (IEEE 754 double precision)."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.FLOAT)

    def _parse_decimal_type(self) -> ir.FieldType:
        """Parse decimal(P,S) type."""
        self.advance()
        if not self.match(TokenType.LPAREN):
            tok = self.current_token()
            raise make_parse_error(
                "decimal requires precision and scale arguments: decimal(P,S)\n"
                "  Example: amount: decimal(10,2)",
                self.file,
                tok.line,
                tok.column,
            )
        self.expect(TokenType.LPAREN)
        precision = int(self.expect(TokenType.NUMBER).value)
        self.expect(TokenType.COMMA)
        scale = int(self.expect(TokenType.NUMBER).value)
        self.expect(TokenType.RPAREN)
        return ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=precision, scale=scale)

    def _parse_bool_type(self) -> ir.FieldType:
        """Parse bool type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.BOOL)

    def _parse_date_type(self) -> ir.FieldType:
        """Parse date type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.DATE)

    def _parse_datetime_type(self) -> ir.FieldType:
        """Parse datetime type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.DATETIME)

    def _parse_uuid_type(self) -> ir.FieldType:
        """Parse uuid type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.UUID)

    def _parse_email_type(self) -> ir.FieldType:
        """Parse email type."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.EMAIL)

    def _parse_json_type(self) -> ir.FieldType:
        """Parse json type (v0.9.4)."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.JSON)

    def _parse_money_type(self) -> ir.FieldType:
        """Parse money or money(CURRENCY) type (v0.9.5)."""
        self.advance()
        currency_code = "GBP"  # Default to GBP for UK focus
        if self.match(TokenType.LPAREN):
            self.advance()
            currency_code = self.expect_identifier_or_keyword().value.upper()
            self.expect(TokenType.RPAREN)
        return ir.FieldType(kind=ir.FieldTypeKind.MONEY, currency_code=currency_code)

    def _parse_file_type(self) -> ir.FieldType:
        """Parse file or file(200MB) type (v0.9.5, v0.39.0)."""
        self.advance()
        max_size = None
        if self.match(TokenType.LPAREN):
            self.advance()
            max_size = self._parse_size_literal()
            self.expect(TokenType.RPAREN)
        return ir.FieldType(kind=ir.FieldTypeKind.FILE, max_size=max_size)

    def _parse_url_type(self) -> ir.FieldType:
        """Parse url type (v0.9.5)."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.URL)

    def _parse_timezone_type(self) -> ir.FieldType:
        """Parse timezone type (v0.10.3) - IANA timezone identifier."""
        self.advance()
        return ir.FieldType(kind=ir.FieldTypeKind.TIMEZONE)

    def _parse_enum_type(self) -> ir.FieldType:
        """Parse enum[val1,val2,...] type."""
        self.advance()
        self.expect(TokenType.LBRACKET)
        values = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.COMMA):
            self.advance()
            values.append(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.RBRACKET)
        return ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=values)

    def _parse_ref_type(self) -> ir.FieldType:
        """Parse ref EntityName type."""
        self.advance()
        entity_name = self.expect(TokenType.IDENTIFIER).value
        return ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity=entity_name)

    def _parse_has_many_type(self) -> ir.FieldType:
        """Parse has_many EntityName [via JunctionEntity] [cascade|restrict|nullify] [readonly] (v0.7.1)."""
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

    def _parse_has_one_type(self) -> ir.FieldType:
        """Parse has_one EntityName [cascade|restrict] [readonly] (v0.7.1)."""
        self.advance()
        entity_name = self.expect(TokenType.IDENTIFIER).value
        behavior, readonly = self._parse_relationship_modifiers()
        return ir.FieldType(
            kind=ir.FieldTypeKind.HAS_ONE,
            ref_entity=entity_name,
            relationship_behavior=behavior,
            readonly=readonly,
        )

    def _parse_embeds_type(self) -> ir.FieldType:
        """Parse embeds EntityName (v0.7.1)."""
        self.advance()
        entity_name = self.expect(TokenType.IDENTIFIER).value
        return ir.FieldType(kind=ir.FieldTypeKind.EMBEDS, ref_entity=entity_name)

    def _parse_belongs_to_type(self) -> ir.FieldType:
        """Parse belongs_to EntityName (v0.7.1)."""
        self.advance()
        entity_name = self.expect(TokenType.IDENTIFIER).value
        return ir.FieldType(kind=ir.FieldTypeKind.BELONGS_TO, ref_entity=entity_name)

    # ------------------------------------------------------------------
    # Relationship and duration helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # parse_field_modifiers and default-value sub-parsers
    # ------------------------------------------------------------------

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
        modifiers: list[ir.FieldModifier] = []
        default: DefaultValue = None
        default_expr: _Expr | None = None

        _modifier_map: dict[str, ir.FieldModifier] = {
            "required": ir.FieldModifier.REQUIRED,
            "optional": ir.FieldModifier.OPTIONAL,
            "pk": ir.FieldModifier.PK,
            "auto_add": ir.FieldModifier.AUTO_ADD,
            "auto_update": ir.FieldModifier.AUTO_UPDATE,
            "sensitive": ir.FieldModifier.SENSITIVE,
            "searchable": ir.FieldModifier.SEARCHABLE,
            "indexed": ir.FieldModifier.INDEXED,
        }

        while True:
            token = self.current_token()

            # Simple single-keyword modifiers
            simple_mod = _modifier_map.get(token.value)
            if simple_mod is not None:
                self.advance()
                modifiers.append(simple_mod)
                continue

            # unique / unique? — needs special handling for optional '?'
            if token.value == "unique":
                self.advance()
                if self.match(TokenType.QUESTION):
                    self.advance()
                    modifiers.append(ir.FieldModifier.UNIQUE_NULLABLE)
                else:
                    modifiers.append(ir.FieldModifier.UNIQUE)
                continue

            # default = <value>
            if self.match(TokenType.EQUALS):
                self.advance()
                default, default_expr = self._parse_default_value()
                continue

            break

        return modifiers, default, default_expr

    def _parse_default_value(
        self,
    ) -> tuple[DefaultValue, "_Expr | None"]:
        """Parse the value portion of a ``= <value>`` default clause.

        Returns a (default, default_expr) pair exactly as ``parse_field_modifiers``
        expects; exactly one of the two will be non-None.
        """
        # v0.29.0: typed expression default (e.g., = box1 + box2, = if ...)
        if self._is_expression_default():
            return None, self.collect_line_as_expr()

        # v0.10.2: date expression (today, now, today + 7d, …)
        if self.match(TokenType.TODAY) or self.match(TokenType.NOW):
            return self._parse_date_expr(), None

        if self.match(TokenType.STRING):
            return self.advance().value, None

        if self.match(TokenType.NUMBER):
            num_str = self.advance().value
            value: DefaultValue = float(num_str) if "." in num_str else int(num_str)
            return value, None

        if self.match(TokenType.TRUE):
            self.advance()
            return True, None

        if self.match(TokenType.FALSE):
            self.advance()
            return False, None

        if self.match(TokenType.IDENTIFIER):
            val = self.advance().value
            if val in ("true", "false"):
                return val == "true", None
            return val, None

        if self._is_keyword_as_identifier():
            # v0.9.1: Allow keywords as default enum values
            # e.g., status: enum[draft,submitted,approved]=submitted
            return self.advance().value, None

        # v0.14.1: Provide helpful error for invalid default values
        err_token = self.current_token()
        if err_token.type in _INVALID_DEFAULT_OPERATOR_TOKENS:
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

    def _is_expression_default(self) -> bool:
        """Check if the default value starting at current position is a typed expression.

        An expression default is detected when an identifier (or keyword-as-identifier)
        is followed by an arithmetic/comparison operator or '(' (function call).
        """
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

    def _parse_size_literal(self) -> int:
        """Parse a size literal like 200MB, 1GB, 500KB.

        Returns size in bytes.
        """
        num_token = self.expect(TokenType.NUMBER)
        value = int(num_token.value)

        unit_token = self.current_token()
        unit = str(unit_token.value).upper()
        _SIZE_UNITS = {"KB": 1024, "MB": 1024 * 1024, "GB": 1024 * 1024 * 1024}
        if unit not in _SIZE_UNITS:
            raise make_parse_error(
                f"Expected size unit (KB, MB, GB), got '{unit_token.value}'",
                self.file,
                unit_token.line,
                unit_token.column,
            )
        self.advance()
        return value * _SIZE_UNITS[unit]

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
