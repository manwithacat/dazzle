"""
Type parsing for DAZZLE DSL.

Handles field type specifications and field modifiers.
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


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

        # v0.7.1: has_many EntityName [cascade|restrict|nullify] [readonly]
        elif token.type == TokenType.HAS_MANY:
            self.advance()
            entity_name = self.expect(TokenType.IDENTIFIER).value
            behavior, readonly = self._parse_relationship_modifiers()
            return ir.FieldType(
                kind=ir.FieldTypeKind.HAS_MANY,
                ref_entity=entity_name,
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

    def parse_field_modifiers(
        self,
    ) -> tuple[list[ir.FieldModifier], str | int | float | bool | None]:
        """
        Parse field modifiers and default value.

        Returns:
            Tuple of (modifiers, default_value)
        """
        modifiers = []
        default: str | int | float | bool | None = None

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
            elif self.match(TokenType.EQUALS):
                # default=value
                self.advance()
                if self.match(TokenType.STRING):
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
                break

        return modifiers, default

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
        """Parse a literal value (string, number, boolean, or null)."""
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
            # Treat as string value (for enum values etc)
            return str(self.advance().value)
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
