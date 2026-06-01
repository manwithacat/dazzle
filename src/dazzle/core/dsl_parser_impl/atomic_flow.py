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
        invariants: list[ir.FlowInvariant] = []

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
            elif tok.type == TokenType.INVARIANT:
                invariants.append(self._parse_atomic_invariant())
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
            invariants=invariants,
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

    def _parse_atomic_invariant(self) -> ir.FlowInvariant:
        """Parse one ``invariant:`` line (#1318, ADR-0031).

        Shape::

            invariant: <sum|count> ( <Entity> [. <field>] where <filter> ) <op> <rhs>

        - ``count`` omits ``.field``; ``sum`` requires it.
        - ``<op>`` ∈ ``= <= >= < >``.
        - ``<filter>`` is a conjunction (AND) of ``<column> = (input.<name> |
          literal)`` equality terms — captured raw into ``raw_filter`` as
          ``(column, kind, value)`` triples for the linker to compile (Task 4).
        - ``<rhs>`` is a numeric literal OR ``input.<name>.<field>``.

        Produces a *raw* ``FlowInvariant``: ``anchor_entity`` and
        ``anchor_input`` stay ``None`` (derived by the linker);
        ``agg_fn``/``entity``/``field``/``op``/``rhs``/``raw_filter`` are
        populated here.
        """
        kw_tok = self.expect(TokenType.INVARIANT)
        self.expect(TokenType.COLON)

        # Aggregate function: only `sum` / `count` are keyword tokens; anything
        # else (e.g. `avg`) lexes as an identifier and is rejected here.
        fn_tok = self.current_token()
        if fn_tok.type == TokenType.SUM:
            agg_fn = ir.FlowAggregateFn.SUM
        elif fn_tok.type == TokenType.COUNT:
            agg_fn = ir.FlowAggregateFn.COUNT
        else:
            raise make_parse_error(
                f"`invariant:` aggregate must be `sum` or `count`; got `{fn_tok.value}`.",
                self.file,
                fn_tok.line,
                fn_tok.column,
            )
        self.advance()

        self.expect(TokenType.LPAREN)
        entity = str(self.expect_identifier_or_keyword().value)

        field: str | None = None
        if self.match(TokenType.DOT):
            self.advance()
            field = str(self.expect_identifier_or_keyword().value)

        if agg_fn == ir.FlowAggregateFn.SUM and field is None:
            raise make_parse_error(
                f"`sum(...)` invariant requires a field — write `sum({entity}.<field> where ...)`.",
                self.file,
                kw_tok.line,
                kw_tok.column,
            )
        if agg_fn == ir.FlowAggregateFn.COUNT and field is not None:
            raise make_parse_error(
                f"`count(...)` invariant takes no field — write `count({entity} where ...)`.",
                self.file,
                kw_tok.line,
                kw_tok.column,
            )

        self.expect(TokenType.WHERE)
        raw_filter = self._parse_invariant_filter()
        self.expect(TokenType.RPAREN)

        op = self._parse_invariant_op()
        rhs = self._parse_invariant_rhs()
        self.skip_newlines()

        return ir.FlowInvariant(
            agg_fn=agg_fn,
            entity=entity,
            field=field,
            anchor_entity=None,
            anchor_input=None,
            op=op,
            rhs=rhs,
            raw_filter=raw_filter,
        )

    def _parse_invariant_filter(self) -> tuple[tuple[str, str, str], ...]:
        """Parse the ``where`` filter: AND-joined ``<col> = (input.<n> | literal)``.

        Returns a tuple of ``(column, kind, value)`` triples where ``kind`` ∈
        {"input", "literal"}. The v1 grammar is deliberately bounded — no
        ADR-0009 algebra (PathCheck/ExistsCheck/current_user); the linker
        compiles these raw terms into a ``ScopePredicate`` in Task 4.
        """
        terms: list[tuple[str, str, str]] = []
        while True:
            col_tok = self.expect_identifier_or_keyword()
            column = str(col_tok.value)
            self.expect(TokenType.EQUALS)
            val_tok = self.current_token()
            if val_tok.type == TokenType.INPUT:
                self.advance()
                self.expect(TokenType.DOT)
                name = str(self.expect_identifier_or_keyword().value)
                terms.append((column, "input", name))
            elif val_tok.type == TokenType.NUMBER:
                self.advance()
                terms.append((column, "literal", str(val_tok.value)))
            elif val_tok.type == TokenType.STRING:
                self.advance()
                terms.append((column, "literal", str(val_tok.value)))
            else:
                raise make_parse_error(
                    "`invariant:` filter value must be `input.<name>` or a literal; "
                    f"got `{val_tok.value}`.",
                    self.file,
                    val_tok.line,
                    val_tok.column,
                )
            if self.match(TokenType.AND):
                self.advance()
                continue
            break
        return tuple(terms)

    def _parse_invariant_op(self) -> ir.CompOp:
        """Parse the comparison operator: ``= <= >= < >``."""
        tok = self.current_token()
        op_map = {
            TokenType.EQUALS: ir.CompOp.EQ,
            TokenType.LESS_EQUAL: ir.CompOp.LTE,
            TokenType.GREATER_EQUAL: ir.CompOp.GTE,
            TokenType.LESS_THAN: ir.CompOp.LT,
            TokenType.GREATER_THAN: ir.CompOp.GT,
        }
        op = op_map.get(tok.type)
        if op is None:
            raise make_parse_error(
                f"`invariant:` comparison must be one of `= <= >= < >`; got `{tok.value}`.",
                self.file,
                tok.line,
                tok.column,
            )
        self.advance()
        return op

    def _parse_invariant_rhs(self) -> ir.InvariantRhs:
        """Parse the RHS bound: a numeric literal OR ``input.<name>.<field>``."""
        tok = self.current_token()
        if tok.type == TokenType.NUMBER:
            self.advance()
            raw = str(tok.value)
            value: int | float = int(raw) if raw.lstrip("-").isdigit() else float(raw)
            return ir.InvariantRhs(literal=value)
        if tok.type == TokenType.INPUT:
            self.advance()
            self.expect(TokenType.DOT)
            name = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.DOT)
            anchor_field = str(self.expect_identifier_or_keyword().value)
            return ir.InvariantRhs(anchor_input=name, anchor_field=anchor_field)
        raise make_parse_error(
            "`invariant:` right-hand side must be a numeric literal or "
            f"`input.<name>.<field>`; got `{tok.value}`.",
            self.file,
            tok.line,
            tok.column,
        )

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
