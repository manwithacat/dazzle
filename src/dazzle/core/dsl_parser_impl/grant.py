# src/dazzle/core/dsl_parser_impl/grant.py
"""
Grant schema parser mixin for DAZZLE DSL.

Parses grant_schema blocks with nested relation sub-blocks.

DSL Syntax (v0.42.0):
    grant_schema department_delegation "Department Delegation":
      description: "Delegation of department-level responsibilities"
      scope: Department

      relation acting_hod "Assign covering HoD":
        granted_by: role(senior_leadership)
        approval: required
        expiry: required
        max_duration: 90d
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..ir.grants import GrantApprovalMode, GrantExpiryMode, GrantRelationSpec, GrantSchemaSpec
from ..lexer import TokenType


class GrantParserMixin:
    """Parser mixin for grant_schema blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _source_location: Any
        parse_condition_expr: Any

    def parse_grant_schema(self) -> GrantSchemaSpec:
        """
        Parse a grant_schema block.

        Grammar:
            grant_schema NAME STRING COLON NEWLINE INDENT
              [description COLON STRING NEWLINE]
              scope COLON IDENTIFIER NEWLINE
              (relation NAME STRING COLON NEWLINE INDENT ... DEDENT)+
            DEDENT
        """
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        label = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description: str | None = None
        scope: str | None = None
        relations: list[GrantRelationSpec] = []
        scope_token = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "description":
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "scope":
                scope_token = token
                self.advance()
                self.expect(TokenType.COLON)
                scope = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif field_name == "relation":
                self.advance()
                relation = self._parse_grant_relation()
                relations.append(relation)

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                self._grant_skip_to_next_field()

        self.expect(TokenType.DEDENT)

        if scope is None:
            from ..errors import make_parse_error

            t = scope_token or self.current_token()
            raise make_parse_error(
                "grant_schema requires a 'scope' field",
                self.file,
                t.line,
                t.column,
            )

        return GrantSchemaSpec(
            name=name,
            label=label,
            description=description,
            scope=scope,
            relations=relations,
            source_location=loc,
        )

    def _parse_grant_relation(self) -> GrantRelationSpec:
        """Parse a relation sub-block within a grant_schema."""
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        label = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description: str | None = None
        principal_label: str | None = None
        confirmation: str | None = None
        revoke_verb: str | None = None
        granted_by: ir.ConditionExpr | None = None
        approved_by: ir.ConditionExpr | None = None
        approval = GrantApprovalMode.REQUIRED
        expiry = GrantExpiryMode.REQUIRED
        max_duration: str | ir.ParamRef | None = None
        granted_by_token = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "description":
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "principal_label":
                self.advance()
                self.expect(TokenType.COLON)
                principal_label = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "confirmation":
                self.advance()
                self.expect(TokenType.COLON)
                confirmation = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "revoke_verb":
                self.advance()
                self.expect(TokenType.COLON)
                revoke_verb = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "granted_by":
                granted_by_token = token
                self.advance()
                self.expect(TokenType.COLON)
                granted_by = self.parse_condition_expr()
                self.skip_newlines()

            elif field_name == "approved_by":
                self.advance()
                self.expect(TokenType.COLON)
                approved_by = self.parse_condition_expr()
                self.skip_newlines()

            elif field_name == "approval":
                self.advance()
                self.expect(TokenType.COLON)
                approval_str = self.advance().value
                approval = self._parse_approval_mode(approval_str)
                self.skip_newlines()

            elif field_name == "expiry":
                self.advance()
                self.expect(TokenType.COLON)
                expiry_str = self.advance().value
                expiry = self._parse_expiry_mode(expiry_str)
                self.skip_newlines()

            elif field_name == "max_duration":
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.PARAM):
                    self.advance()
                    self.expect(TokenType.LPAREN)
                    ref_key = self.expect(TokenType.STRING).value
                    self.expect(TokenType.RPAREN)
                    max_duration = ir.ParamRef(key=ref_key, param_type="str", default="")
                else:
                    max_duration = self.advance().value
                self.skip_newlines()

            else:
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                self._grant_skip_to_next_field()

        self.expect(TokenType.DEDENT)

        if granted_by is None:
            from ..errors import make_parse_error

            t = granted_by_token or self.current_token()
            raise make_parse_error(
                "relation requires a 'granted_by' field",
                self.file,
                t.line,
                t.column,
            )

        return GrantRelationSpec(
            name=name,
            label=label,
            description=description,
            principal_label=principal_label,
            confirmation=confirmation,
            revoke_verb=revoke_verb,
            granted_by=granted_by,
            approved_by=approved_by,
            approval=approval,
            expiry=expiry,
            max_duration=max_duration,
            source_location=loc,
        )

    def _parse_approval_mode(self, value: str) -> GrantApprovalMode:
        mode_map = {
            "required": GrantApprovalMode.REQUIRED,
            "immediate": GrantApprovalMode.IMMEDIATE,
            "none": GrantApprovalMode.NONE,
        }
        if value in mode_map:
            return mode_map[value]
        from ..errors import make_parse_error

        t = self.current_token()
        raise make_parse_error(
            f"Invalid approval mode '{value}'. Valid: required, immediate, none",
            self.file,
            t.line,
            t.column,
        )

    def _parse_expiry_mode(self, value: str) -> GrantExpiryMode:
        mode_map = {
            "required": GrantExpiryMode.REQUIRED,
            "optional": GrantExpiryMode.OPTIONAL,
            "none": GrantExpiryMode.NONE,
        }
        if value in mode_map:
            return mode_map[value]
        from ..errors import make_parse_error

        t = self.current_token()
        raise make_parse_error(
            f"Invalid expiry mode '{value}'. Valid: required, optional, none",
            self.file,
            t.line,
            t.column,
        )

    def _grant_skip_to_next_field(self) -> None:
        """Skip tokens until next field or end of block."""
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            if self.match(TokenType.NEWLINE):
                self.skip_newlines()
                break
            self.advance()
