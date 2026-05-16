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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..ir.grants import GrantApprovalMode, GrantExpiryMode, GrantRelationSpec, GrantSchemaSpec
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


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
        """Parse a ``relation <name> "Label":`` sub-block within a grant_schema.

        Refactored to dispatch-table style (follow-on to #1098). 9
        IDENT-text-matched ``_gr_kw_*`` parsers + tolerant
        ``_skip_unknown_grant_relation_field`` on_unknown +
        ``_build_grant_relation`` builder enforcing the required
        ``granted_by`` field.
        """
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        label = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _GrantRelationState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_GRANT_RELATION_KEYWORDS,
            ident_keywords=_GRANT_RELATION_IDENT_KEYWORDS,
            state=state,
            on_unknown=_skip_unknown_grant_relation_field,
        )
        self.expect(TokenType.DEDENT)
        return _build_grant_relation(self, name, label, loc, state)

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


# ============================================================ #
# _parse_grant_relation — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 124-line monolith was replaced (v0.70.30) with the dispatch
# pattern shipped in #1097. 9 IDENT-text-matched `_gr_kw_*` parsers
# + tolerant `_skip_unknown_grant_relation_field` on_unknown +
# `_build_grant_relation` builder enforcing the required
# ``granted_by`` field.


@dataclass
class _GrantRelationState:
    """Accumulator for :meth:`GrantParserMixin._parse_grant_relation`."""

    description: str | None = None
    principal_label: str | None = None
    confirmation: str | None = None
    revoke_verb: str | None = None
    granted_by: ir.ConditionExpr | None = None
    approved_by: ir.ConditionExpr | None = None
    approval: GrantApprovalMode = GrantApprovalMode.REQUIRED
    expiry: GrantExpiryMode = GrantExpiryMode.REQUIRED
    max_duration: str | ir.ParamRef | None = field(default=None)


# ---------- IDENT-text-matched keyword parsers ---------- #


def _gr_kw_description(parser: Any, state: _GrantRelationState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.description = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _gr_kw_principal_label(parser: Any, state: _GrantRelationState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.principal_label = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _gr_kw_confirmation(parser: Any, state: _GrantRelationState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.confirmation = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _gr_kw_revoke_verb(parser: Any, state: _GrantRelationState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.revoke_verb = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _gr_kw_granted_by(parser: Any, state: _GrantRelationState) -> None:
    """``granted_by: <condition_expr>`` — required field."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.granted_by = parser.parse_condition_expr()
    parser.skip_newlines()


def _gr_kw_approved_by(parser: Any, state: _GrantRelationState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.approved_by = parser.parse_condition_expr()
    parser.skip_newlines()


def _gr_kw_approval(parser: Any, state: _GrantRelationState) -> None:
    """``approval: required|immediate|...`` — delegates to mixin enum mapper."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.approval = parser._parse_approval_mode(parser.advance().value)
    parser.skip_newlines()


def _gr_kw_expiry(parser: Any, state: _GrantRelationState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.expiry = parser._parse_expiry_mode(parser.advance().value)
    parser.skip_newlines()


def _gr_kw_max_duration(parser: Any, state: _GrantRelationState) -> None:
    """``max_duration: <duration>`` OR ``max_duration: param("key")``."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.PARAM):
        parser.advance()
        parser.expect(TokenType.LPAREN)
        ref_key = parser.expect(TokenType.STRING).value
        parser.expect(TokenType.RPAREN)
        state.max_duration = ir.ParamRef(key=ref_key, param_type="str", default="")
    else:
        state.max_duration = parser.advance().value
    parser.skip_newlines()


# ---------- Dispatch table + on_unknown + builder ---------- #


# `description` and `approval` are lexer keywords (TokenType.DESCRIPTION /
# TokenType.APPROVAL) — they must live in the token-keyed table so the
# dispatch helper finds them before falling through to the IDENT lookup.
# The remaining 7 are plain identifiers — they live in the IDENT table.
_GRANT_RELATION_KEYWORDS: dict[TokenType, KeywordParser[_GrantRelationState]] = {
    TokenType.DESCRIPTION: _gr_kw_description,
    TokenType.APPROVAL: _gr_kw_approval,
}


_GRANT_RELATION_IDENT_KEYWORDS: dict[str, KeywordParser[_GrantRelationState]] = {
    "principal_label": _gr_kw_principal_label,
    "confirmation": _gr_kw_confirmation,
    "revoke_verb": _gr_kw_revoke_verb,
    "granted_by": _gr_kw_granted_by,
    "approved_by": _gr_kw_approved_by,
    "expiry": _gr_kw_expiry,
    "max_duration": _gr_kw_max_duration,
}


def _skip_unknown_grant_relation_field(parser: Any) -> None:
    """Tolerate ``unknown: value`` lines (mirrors legacy else branch).

    Advance past the unknown keyword + optional colon, then delegate
    to the mixin's ``_grant_skip_to_next_field`` helper to consume
    the value tokens up to the next newline.
    """
    parser.advance()
    if parser.match(TokenType.COLON):
        parser.advance()
    parser._grant_skip_to_next_field()


def _build_grant_relation(
    parser: Any,
    name: str,
    label: str,
    loc: Any,
    state: _GrantRelationState,
) -> GrantRelationSpec:
    """Enforce required ``granted_by`` field; assemble the IR."""
    if state.granted_by is None:
        tok = parser.current_token()
        raise make_parse_error(
            "relation requires a 'granted_by' field",
            parser.file,
            tok.line,
            tok.column,
        )

    return GrantRelationSpec(
        name=name,
        label=label,
        description=state.description,
        principal_label=state.principal_label,
        confirmation=state.confirmation,
        revoke_verb=state.revoke_verb,
        granted_by=state.granted_by,
        approved_by=state.approved_by,
        approval=state.approval,
        expiry=state.expiry,
        max_duration=state.max_duration,
        source_location=loc,
    )
