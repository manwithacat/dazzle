"""Guided-onboarding parser mixin for DAZZLE DSL (v0.71.0).

Parses the top-level ``guide`` block. Inline annotation sugar
(``onboarding`` keyword inside a surface action) is deferred to
v0.71.1 — same IR, additional parser surface.

DSL Syntax (v0.71.0 — explicit-target form):

    guide workspace_setup "First-run setup":
      audience: persona = admin and entity.Task.count = 0

      step create_task:
        kind: popover
        target: surface.task_list.action.create
        title: "Click here to create your first task"
        body: "We'll walk you through filling it in."
        placement: bottom
        complete_on: click
        audience_when: entity.Task.count = 0

      step invite_team:
        kind: inline_card
        target: surface.team_list
        title: "Invite your team"
        body: "Other members can co-edit your tasks."
        complete_on: event entity.User.created

      step_order: [create_task, invite_team]

      on_complete:
        emit: event entity.Onboarding.completed
        redirect: surface.task_list

Notes:

- ``audience`` and ``audience_when`` accept the same predicate
  algebra as ``scope:`` rules (see ``project_predicate_algebra``
  memory). The parser captures the raw string; the linker compiles
  and validates against the FK graph at link time.
- ``complete_on: click`` / ``dismiss`` are bare keywords;
  ``complete_on: event <ref>`` consumes the next token as the event
  ref string; ``complete_on: field_filled <path>`` likewise.
- ``target`` is captured as a raw dotted path string; the linker
  resolves it to a real IR node and fails the build on miss.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class OnboardingParserMixin:
    """Parser mixin for ``guide`` blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _parse_construct_header: Any

    # ------------------------------------------------------------------
    # Top-level entrypoint
    # ------------------------------------------------------------------

    def parse_guide(self) -> ir.GuideSpec:
        """Parse a top-level ``guide`` block."""
        name, title, _ = self._parse_construct_header(TokenType.GUIDE)

        audience: str = ""
        steps: list[ir.GuideStep] = []
        step_order: list[str] = []
        on_complete: ir.GuideOnComplete | None = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()

            if tok.value == "audience":
                audience = self._parse_predicate_line()
            elif tok.value == "step":
                steps.append(self._parse_guide_step())
            elif tok.value == "step_order":
                step_order = self._parse_step_order()
            elif tok.value == "on_complete":
                on_complete = self._parse_on_complete_block()
            else:
                # Unknown sub-key: skip its line so we don't lock up.
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.GuideSpec(
            name=name,
            title=title or name,
            audience=audience,
            steps=steps,
            step_order=step_order,
            on_complete=on_complete,
        )

    # ------------------------------------------------------------------
    # `step <name>:` block
    # ------------------------------------------------------------------

    def _parse_guide_step(self) -> ir.GuideStep:
        """Parse one ``step <name>:`` block inside a guide."""
        self.advance()  # consume `step`
        step_name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        kind: ir.GuideStepKind = ir.GuideStepKind.POPOVER
        title = ""
        body = ""
        target = ""
        placement = "bottom"
        cta_label: str | None = None
        cta_target: str | None = None
        complete_on = ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.DISMISS)
        audience_when: str | None = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            key = tok.value

            if key == "kind":
                kind = self._parse_kind_value()
            elif key == "title":
                title = self._parse_kv_string_line()
            elif key == "body":
                body = self._parse_kv_string_line()
            elif key == "target":
                target = self._parse_kv_string_line()
            elif key == "placement":
                placement = self._parse_kv_string_line()
            elif key == "cta_label":
                cta_label = self._parse_kv_string_line()
            elif key == "cta_target":
                cta_target = self._parse_kv_string_line()
            elif key == "complete_on":
                complete_on = self._parse_complete_on_value()
            elif key == "audience_when":
                audience_when = self._parse_predicate_line()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.GuideStep(
            name=step_name,
            kind=kind,
            title=title,
            body=body,
            target=target,
            placement=placement,
            cta_label=cta_label,
            cta_target=cta_target,
            complete_on=complete_on,
            audience_when=audience_when,
        )

    # ------------------------------------------------------------------
    # complete_on parsing
    # ------------------------------------------------------------------

    def _parse_complete_on_value(self) -> ir.GuideCompleteOn:
        """Parse the right-hand side of ``complete_on:``.

        Accepted shapes:
            complete_on: click
            complete_on: dismiss
            complete_on: event <ref-path>
            complete_on: field_filled <field-path>
        """
        self.advance()  # consume `complete_on`
        self.expect(TokenType.COLON)
        kind_tok = self.expect_identifier_or_keyword()
        kw = kind_tok.value
        if kw == "click":
            self.skip_newlines()
            return ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK)
        if kw == "dismiss":
            self.skip_newlines()
            return ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.DISMISS)
        if kw == "event":
            ref = self._consume_dotted_path()
            self.skip_newlines()
            return ir.GuideCompleteOn(
                kind=ir.GuideCompleteOnKind.EVENT,
                event_ref=ref,
            )
        if kw == "field_filled":
            ref = self._consume_dotted_path()
            self.skip_newlines()
            return ir.GuideCompleteOn(
                kind=ir.GuideCompleteOnKind.FIELD_FILLED,
                field_filled=ref,
            )
        # Unknown — preserve as plain dismiss so the parse doesn't
        # abort; the linker can flag a more useful error.
        self.skip_newlines()
        return ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.DISMISS)

    # ------------------------------------------------------------------
    # Sub-helpers
    # ------------------------------------------------------------------

    def _parse_kind_value(self) -> ir.GuideStepKind:
        """Parse ``kind: <identifier>`` — maps to GuideStepKind."""
        self.advance()  # consume `kind`
        self.expect(TokenType.COLON)
        value = self.expect_identifier_or_keyword().value
        self.skip_newlines()
        try:
            return ir.GuideStepKind(value)
        except ValueError:
            # Unrecognised kind — default to popover; linker will warn.
            return ir.GuideStepKind.POPOVER

    def _parse_kv_string_line(self) -> str:
        """Parse ``<key>: <string-or-identifier-tail>``.

        Consumes the key + colon. Reads either a quoted string or a
        dotted path / identifier expression (whitespace-bounded).
        Returns the captured value.
        """
        self.advance()  # consume key
        self.expect(TokenType.COLON)
        tok = self.current_token()
        if tok.type == TokenType.STRING:
            self.advance()
            self.skip_newlines()
            return str(tok.value)
        # Identifier / dotted path / keyword — consume tokens until
        # we hit a newline/dedent.
        value = self._consume_dotted_path()
        self.skip_newlines()
        return value

    def _parse_predicate_line(self) -> str:
        """Capture an audience predicate as a raw string until newline.

        Audience predicates reuse the ``scope:`` predicate algebra and
        may contain reserved keywords (``persona``, ``entity``, ``and``,
        ``or``) plus dotted paths (``entity.Task.count``). We tokenize
        them but defer parsing to the linker — same shape as how the
        parser captures scope conditions today.

        Joins token values with single spaces except around dots so
        ``entity.Task.count`` round-trips intact.
        """
        self.advance()  # consume key
        self.expect(TokenType.COLON)
        parts: list[str] = []
        token_types: list[TokenType] = []
        while True:
            tok = self.current_token()
            if tok.type in (
                TokenType.NEWLINE,
                TokenType.DEDENT,
                TokenType.EOF,
                TokenType.INDENT,
            ):
                break
            parts.append(str(tok.value))
            token_types.append(tok.type)
            self.advance()
        self.skip_newlines()

        # Re-stitch with whitespace, suppressing it around DOTs so
        # dotted paths stay compact.
        out: list[str] = []
        for i, (part, tt) in enumerate(zip(parts, token_types, strict=True)):
            prev_is_dot = i > 0 and token_types[i - 1] == TokenType.DOT
            curr_is_dot = tt == TokenType.DOT
            if out and not (prev_is_dot or curr_is_dot):
                out.append(" ")
            out.append(part)
        return "".join(out).strip()

    def _consume_dotted_path(self) -> str:
        """Consume a sequence of identifiers / keywords joined by dots
        (e.g. ``surface.task_list.action.create``,
        ``entity.Task.created``). Returns the joined string."""
        parts: list[str] = []
        # First segment: must be identifier-like
        first = self.expect_identifier_or_keyword()
        parts.append(str(first.value))
        while self.match(TokenType.DOT):
            self.advance()
            next_tok = self.expect_identifier_or_keyword()
            parts.append(str(next_tok.value))
        return ".".join(parts)

    def _parse_step_order(self) -> list[str]:
        """Parse ``step_order: [name1, name2, …]`` or a YAML-ish dash list."""
        self.advance()  # consume `step_order`
        self.expect(TokenType.COLON)
        order: list[str] = []
        if self.match(TokenType.LBRACKET):
            self.advance()
            while not self.match(TokenType.RBRACKET):
                tok = self.expect_identifier_or_keyword()
                order.append(str(tok.value))
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)
            self.skip_newlines()
            return order
        # No bracket — must be dash-list form
        self.skip_newlines()
        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break
                if self.match(TokenType.MINUS):
                    self.advance()
                    tok = self.expect_identifier_or_keyword()
                    order.append(str(tok.value))
                    self.skip_newlines()
                else:
                    self.advance()
                    self.skip_newlines()
            if self.match(TokenType.DEDENT):
                self.advance()
        return order

    def _parse_on_complete_block(self) -> ir.GuideOnComplete:
        """Parse ``on_complete:`` sub-block (emit + redirect)."""
        self.advance()  # consume `on_complete`
        self.expect(TokenType.COLON)
        self.skip_newlines()

        emit: str | None = None
        redirect: str | None = None

        if not self.match(TokenType.INDENT):
            return ir.GuideOnComplete()

        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            tok = self.current_token()
            key = tok.value
            if key == "emit":
                self.advance()
                self.expect(TokenType.COLON)
                # Accept `emit: event <ref>` or `emit: <ref>`
                next_tok = self.current_token()
                if next_tok.type != TokenType.STRING and next_tok.value == "event":
                    self.advance()
                emit = self._consume_dotted_path()
                self.skip_newlines()
            elif key == "redirect":
                redirect = self._parse_kv_string_line()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.GuideOnComplete(emit=emit, redirect=redirect)
