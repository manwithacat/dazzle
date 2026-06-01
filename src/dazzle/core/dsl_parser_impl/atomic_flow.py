"""Atomic-flow parser mixin (#1228 Phase 3c slice 3c.i).

Parses the new ``atomic <name> "Label":`` block. The DSL keyword
``atomic`` (vs the originally proposed ``flow``) was chosen because
``flow`` already names the E2E test construct in this parser.

DSL shape::

    atomic onboard_starter "Onboard Starter":
      intent: "Atomically create Person + Employment + Salary"
      permit:
        execute: role(hr_admin)
      on_failure: rollback_all

      input person_legal_name: str(200) required
      input person_email: email required
      input started_at: date required

      create Person:
        legal_name: input.person_legal_name
        email: input.person_email
        started_at: input.started_at

      create Employment:
        person: above.Person.id
        role: input.role
        start_date: input.started_at

Runtime (single DB transaction, ``above`` resolution, route emit)
lands in slice 3c.ii. This slice ships IR + parser + validator only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class AtomicFlowParserMixin:
    """Parser mixin for ``atomic`` blocks (#1228)."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        parse_type_spec: Any
        file: Any

    def parse_atomic_flow(self) -> ir.AtomicFlowSpec:
        """Parse an ``atomic <name> "Label":`` block."""
        self.expect(TokenType.ATOMIC)
        name = self.expect(TokenType.IDENTIFIER).value
        label = name
        if self.match(TokenType.STRING):
            label = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        intent: str | None = None
        permit_execute: list[str] = []
        on_failure = ir.FlowFailureMode.ROLLBACK_ALL
        audit_mode = ir.FlowAuditMode.ASYNC
        inputs: list[ir.FlowInput] = []
        steps: list[ir.AtomicFlowStep] = []

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            tok = self.current_token()
            if tok.type == TokenType.INTENT:
                self.advance()
                self.expect(TokenType.COLON)
                intent = self.expect(TokenType.STRING).value
                self.skip_newlines()
            elif tok.type == TokenType.PERMIT:
                permit_execute = self._parse_atomic_permit()
            elif tok.type == TokenType.ON_FAILURE:
                self.advance()
                self.expect(TokenType.COLON)
                mode_tok = self.expect_identifier_or_keyword()
                if str(mode_tok.value) != "rollback_all":
                    raise make_parse_error(
                        f"`on_failure` only accepts `rollback_all` in this release; "
                        f"got `{mode_tok.value}`.",
                        self.file,
                        mode_tok.line,
                        mode_tok.column,
                    )
                on_failure = ir.FlowFailureMode.ROLLBACK_ALL
                self.skip_newlines()
            elif tok.type == TokenType.AUDIT:
                # `audit: strict | async` — per-flow audit durability (#1317).
                self.advance()
                self.expect(TokenType.COLON)
                mode_tok = self.expect_identifier_or_keyword()
                mode_val = str(mode_tok.value)
                if mode_val == "strict":
                    audit_mode = ir.FlowAuditMode.STRICT
                elif mode_val == "async":
                    audit_mode = ir.FlowAuditMode.ASYNC
                else:
                    raise make_parse_error(
                        f"`audit:` only accepts `strict` or `async`; got `{mode_val}`.",
                        self.file,
                        mode_tok.line,
                        mode_tok.column,
                    )
                self.skip_newlines()
            elif tok.type == TokenType.INPUT:
                inputs.append(self._parse_atomic_input())
            elif tok.type == TokenType.CREATE:
                steps.append(self._parse_atomic_create())
            elif tok.type == TokenType.UPDATE:
                steps.append(self._parse_atomic_update())
            else:
                # Unknown key — skip the line to avoid getting stuck.
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.AtomicFlowSpec(
            name=name,
            label=label,
            intent=intent,
            permit_execute=permit_execute,
            on_failure=on_failure,
            audit_mode=audit_mode,
            inputs=inputs,
            steps=steps,
        )

    def _parse_atomic_permit(self) -> list[str]:
        """Parse ``permit:`` block with ``execute: role(...)``."""
        self.expect(TokenType.PERMIT)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        roles: list[str] = []
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            key_tok = self.expect_identifier_or_keyword()
            if str(key_tok.value) != "execute":
                raise make_parse_error(
                    f"`atomic permit:` only accepts `execute:` in this release; "
                    f"got `{key_tok.value}`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.expect(TokenType.COLON)
            # role(name, name, ...) — single name in MVP
            kind_tok = self.expect(TokenType.ROLE)
            self.expect(TokenType.LPAREN)
            roles.append(str(self.expect_identifier_or_keyword().value))
            while self.match(TokenType.COMMA):
                self.advance()
                roles.append(str(self.expect_identifier_or_keyword().value))
            self.expect(TokenType.RPAREN)
            _ = kind_tok  # consumed for shape
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return roles

    def _parse_atomic_input(self) -> ir.FlowInput:
        """Parse one ``input <name>: <type> [required]`` line."""
        self.expect(TokenType.INPUT)
        name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        ftype = self.parse_type_spec()
        required = False
        tok = self.current_token()
        if tok.type == TokenType.IDENTIFIER and str(tok.value) == "required":
            self.advance()
            required = True
        self.skip_newlines()
        return ir.FlowInput(name=str(name), type=ftype, required=required)

    def _parse_atomic_create(self) -> ir.FlowCreate:
        """Parse a ``create <Entity>:`` block of field assignments."""
        self.expect(TokenType.CREATE)
        entity = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        assignments: dict[str, ir.FlowFieldValue] = {}
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            field_tok = self.expect_identifier_or_keyword()
            field_name = str(field_tok.value)
            self.expect(TokenType.COLON)
            assignments[field_name] = self._parse_flow_field_value()
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return ir.FlowCreate(entity=str(entity), assignments=assignments)

    def _parse_atomic_update(self) -> ir.FlowUpdate:
        """Parse an ``update <Entity>(<target>):`` block (#1313).

        ``<target>`` selects the existing row to mutate — an ``input.<id>``
        or ``above.<Entity>.id`` reference (the same value forms a create
        assignment accepts), resolving to the row's primary key. Indented
        ``field: value`` lines are the assignments (an "end-date" is just
        an assignment to the entity's temporal end column).
        """
        self.expect(TokenType.UPDATE)
        entity = self.expect_identifier_or_keyword().value
        self.expect(TokenType.LPAREN)
        target = self._parse_flow_field_value()
        self.expect(TokenType.RPAREN)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        assignments: dict[str, ir.FlowFieldValue] = {}
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            field_tok = self.expect_identifier_or_keyword()
            field_name = str(field_tok.value)
            self.expect(TokenType.COLON)
            assignments[field_name] = self._parse_flow_field_value()
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return ir.FlowUpdate(entity=str(entity), target=target, assignments=assignments)

    def _parse_flow_field_value(self) -> ir.FlowFieldValue:
        """Parse the right-hand side of a ``field: value`` in a create.

        Three forms:
        - ``input.<name>`` → INPUT_REF
        - ``above.<Entity>.<field>`` → ABOVE_REF
        - literal: string, integer, bool, or bare identifier (enum value)
        """
        tok = self.current_token()
        # String literal
        if tok.type == TokenType.STRING:
            self.advance()
            return ir.FlowFieldValue(kind=ir.FlowFieldValueKind.LITERAL, literal=str(tok.value))
        # Numeric literal (int or float)
        if tok.type == TokenType.NUMBER:
            self.advance()
            raw = str(tok.value)
            value: int | float = int(raw) if raw.lstrip("-").isdigit() else float(raw)
            return ir.FlowFieldValue(kind=ir.FlowFieldValueKind.LITERAL, literal=value)
        # Identifier-style RHS: input.X, above.E.F, or bare identifier (enum value)
        if tok.type == TokenType.IDENTIFIER or tok.type == TokenType.INPUT:
            head_tok = self.advance()
            head = str(head_tok.value)
            if head == "input":
                self.expect(TokenType.DOT)
                inp_tok = self.expect_identifier_or_keyword()
                return ir.FlowFieldValue(
                    kind=ir.FlowFieldValueKind.INPUT_REF,
                    input_name=str(inp_tok.value),
                )
            if head == "above":
                self.expect(TokenType.DOT)
                ent_tok = self.expect_identifier_or_keyword()
                self.expect(TokenType.DOT)
                fld_tok = self.expect_identifier_or_keyword()
                return ir.FlowFieldValue(
                    kind=ir.FlowFieldValueKind.ABOVE_REF,
                    above_entity=str(ent_tok.value),
                    above_field=str(fld_tok.value),
                )
            # Bare identifier — treat as enum-value literal (e.g. `currency: gbp`)
            return ir.FlowFieldValue(kind=ir.FlowFieldValueKind.LITERAL, literal=head)
        raise make_parse_error(
            f"Unexpected token `{tok.value}` for atomic-flow field value.",
            self.file,
            tok.line,
            tok.column,
        )
