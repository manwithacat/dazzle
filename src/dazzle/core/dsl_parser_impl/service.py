"""
Service parsing for DAZZLE DSL.

Handles external API and domain service declarations.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class ServiceParserMixin:
    """
    Mixin providing service and foreign model parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        enum_from_token: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any
        parse_type_spec: Any
        parse_field_modifiers: Any
        _parse_surface_access: Any  # From SurfaceParserMixin
        _parse_dotted_path: Any  # From ProcessParserMixin
        _source_location: Any  # v0.31.0: Source location helper from BaseParser
        _parse_construct_header: Any

    def parse_service(self) -> ir.APISpec | ir.DomainServiceSpec:
        """Parse service declaration (external API or domain service).

        External APIs have: spec, auth_profile, owner
        Domain services have: kind, input, output, guarantees, stub
        """
        name, title, _ = self._parse_construct_header(TokenType.SERVICE)

        # Peek at first directive to determine service type
        self.skip_newlines()
        if self.match(TokenType.KIND):
            # Domain service (v0.5.0)
            return self._parse_domain_service_body(name, title)
        else:
            # External API (original behavior)
            return self._parse_external_api_body(name, title)

    def _parse_external_api_body(self, name: str, title: str | None) -> ir.APISpec:
        """Parse external API service body."""
        spec_url = None
        spec_inline = None
        auth_profile = None
        owner = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # spec: url "..."
            if self.match(TokenType.SPEC):
                self.advance()
                self.expect(TokenType.COLON)

                if self.match(TokenType.URL):
                    self.advance()
                    spec_url = self.expect(TokenType.STRING).value
                elif self.match(TokenType.INLINE):
                    self.advance()
                    spec_inline = self.expect(TokenType.STRING).value

                self.skip_newlines()

            # auth_profile: kind [options...]
            elif self.match(TokenType.AUTH_PROFILE):
                self.advance()
                self.expect(TokenType.COLON)

                auth_kind_token = self.expect(TokenType.IDENTIFIER)
                try:
                    auth_kind = ir.AuthKind(auth_kind_token.value)
                except ValueError as exc:
                    valid = ", ".join(k.value for k in ir.AuthKind)
                    raise make_parse_error(
                        f"Unknown auth_profile kind '{auth_kind_token.value}'. "
                        f"Valid kinds: {valid}.",
                        self.file,
                        auth_kind_token.line,
                        auth_kind_token.column,
                    ) from exc

                # Parse options (key=value pairs)
                options = {}
                while self.match(TokenType.IDENTIFIER):
                    key = self.advance().value
                    self.expect(TokenType.EQUALS)
                    value = self.expect(TokenType.STRING).value
                    options[key] = value

                auth_profile = ir.AuthProfile(kind=auth_kind, options=options)
                self.skip_newlines()

            # owner: "..."
            elif self.match(TokenType.OWNER):
                self.advance()
                self.expect(TokenType.COLON)
                owner = self.expect(TokenType.STRING).value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        if auth_profile is None:
            token = self.current_token()
            raise make_parse_error(
                "Service must have auth_profile",
                self.file,
                token.line,
                token.column,
            )

        return ir.APISpec(
            name=name,
            title=title,
            spec_url=spec_url,
            spec_inline=spec_inline,
            auth_profile=auth_profile,
            owner=owner,
        )

    def _parse_domain_service_body(self, name: str, title: str | None) -> ir.DomainServiceSpec:
        """Parse domain service body (v0.5.0).

        DSL syntax:
            service calculate_vat "Calculate VAT":
              kind: domain_logic

              input:
                invoice_id: uuid required

              output:
                vat_amount: money
                breakdown: json

              guarantees:
                - "Must not mutate the invoice record."

              stub: python
        """
        kind = ir.DomainServiceKind.DOMAIN_LOGIC
        inputs: list[ir.ServiceFieldSpec] = []
        outputs: list[ir.ServiceFieldSpec] = []
        guarantees: list[str] = []
        stub_language = ir.StubLanguage.PYTHON

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # kind: domain_logic | validation | integration | workflow
            if self.match(TokenType.KIND):
                self.advance()
                self.expect(TokenType.COLON)
                # Use expect_identifier_or_keyword since 'integration' is a keyword
                kind_token = self.expect_identifier_or_keyword()
                try:
                    kind = ir.DomainServiceKind(kind_token.value)
                except ValueError as exc:
                    valid = ", ".join(k.value for k in ir.DomainServiceKind)
                    raise make_parse_error(
                        f"Invalid service kind '{kind_token.value}'. Valid kinds: {valid}.",
                        self.file,
                        kind_token.line,
                        kind_token.column,
                    ) from exc
                self.skip_newlines()

            # input:
            elif self.match(TokenType.INPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                inputs = self._parse_service_fields()
                self.expect(TokenType.DEDENT)

            # output:
            elif self.match(TokenType.OUTPUT):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                outputs = self._parse_service_fields()
                self.expect(TokenType.DEDENT)

            # guarantees:
            elif self.match(TokenType.GUARANTEES):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                guarantees = self._parse_guarantee_list()
                self.expect(TokenType.DEDENT)

            # stub: python | typescript
            elif self.match(TokenType.STUB):
                self.advance()
                self.expect(TokenType.COLON)
                lang_token = self.expect(TokenType.IDENTIFIER)
                stub_language = self.enum_from_token(ir.StubLanguage, lang_token)
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.DomainServiceSpec(
            name=name,
            title=title,
            kind=kind,
            inputs=inputs,
            outputs=outputs,
            guarantees=guarantees,
            stub_language=stub_language,
        )

    def _parse_service_fields(self) -> list[ir.ServiceFieldSpec]:
        """Parse service input/output fields.

        Format:
            field_name: type_name [required]
        """
        fields: list[ir.ServiceFieldSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # field_name: type_name [required]
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Parse type - could be identifier or type keyword with params like decimal(10,2)
            type_name = self.expect_identifier_or_keyword().value

            # Check for type parameters like (10,2) or (200)
            if self.match(TokenType.LPAREN):
                self.advance()
                params = []
                params.append(self.expect(TokenType.NUMBER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    params.append(self.expect(TokenType.NUMBER).value)
                self.expect(TokenType.RPAREN)
                type_name = f"{type_name}({','.join(params)})"

            # Check for required modifier
            required = False
            if self.match(TokenType.IDENTIFIER):
                if self.current_token().value == "required":
                    self.advance()
                    required = True

            fields.append(
                ir.ServiceFieldSpec(
                    name=field_name,
                    type_name=type_name,
                    required=required,
                )
            )
            self.skip_newlines()

        return fields

    def _parse_guarantee_list(self) -> list[str]:
        """Parse guarantee list (strings prefixed with dash).

        Format:
            - "Guarantee text here"
            - "Another guarantee"
        """
        guarantees: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # - "guarantee text"
            if self.match(TokenType.MINUS):
                self.advance()
                guarantee_text = self.expect(TokenType.STRING).value
                guarantees.append(guarantee_text)
                self.skip_newlines()
            else:
                break

        return guarantees

    def parse_foreign_model(self) -> ir.ForeignModelSpec:
        """Parse foreign_model declaration."""
        self.expect(TokenType.FOREIGN_MODEL)

        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.FROM)
        api_ref = self.expect(TokenType.IDENTIFIER).value

        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        key_fields = []
        constraints = []
        fields = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # key: field1[,field2,...]
            if self.match(TokenType.KEY):
                self.advance()
                self.expect(TokenType.COLON)

                key_fields.append(self.expect(TokenType.IDENTIFIER).value)
                while self.match(TokenType.COMMA):
                    self.advance()
                    key_fields.append(self.expect(TokenType.IDENTIFIER).value)

                self.skip_newlines()

            # constraint kind [options...]
            elif self.match(TokenType.CONSTRAINT):
                self.advance()

                constraint_kind_token = self.expect(TokenType.IDENTIFIER)
                try:
                    constraint_kind = ir.ForeignConstraintKind(constraint_kind_token.value)
                except ValueError as exc:
                    valid = ", ".join(k.value for k in ir.ForeignConstraintKind)
                    raise make_parse_error(
                        f"Invalid foreign constraint kind '{constraint_kind_token.value}'. "
                        f"Valid kinds: {valid}.",
                        self.file,
                        constraint_kind_token.line,
                        constraint_kind_token.column,
                    ) from exc

                # Parse options (key=value pairs)
                options = {}
                while self.match(TokenType.IDENTIFIER):
                    key = self.advance().value
                    self.expect(TokenType.EQUALS)

                    if self.match(TokenType.STRING):
                        options[key] = self.advance().value
                    elif self.match(TokenType.NUMBER):
                        options[key] = self.advance().value
                    elif self.match(TokenType.IDENTIFIER):
                        options[key] = self.advance().value

                constraints.append(
                    ir.ForeignConstraint(
                        kind=constraint_kind,
                        options=options,
                    )
                )

                self.skip_newlines()

            # field_name: type [modifiers...]
            else:
                fields.append(self._parse_field_spec())  # type: ignore[attr-defined]  # mixin method from TypeParserMixin
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ForeignModelSpec(
            name=name,
            title=title,
            api_ref=api_ref,
            key_fields=key_fields,
            constraints=constraints,
            fields=fields,
        )

    def parse_experience(self) -> ir.ExperienceSpec:
        """Parse experience declaration."""
        name, title, loc = self._parse_construct_header(TokenType.EXPERIENCE)

        access_spec = None
        priority = ir.BusinessPriority.MEDIUM
        context_vars: list[ir.FlowContextVar] = []

        # context: block (optional, before access/priority/start)
        if self.match(TokenType.CONTEXT):
            self.advance()
            self.expect(TokenType.COLON)
            self.skip_newlines()
            self.expect(TokenType.INDENT)

            while not self.match(TokenType.DEDENT):
                self.skip_newlines()
                if self.match(TokenType.DEDENT):
                    break
                var_name = self.expect(TokenType.IDENTIFIER).value
                self.expect(TokenType.COLON)
                entity_ref = self.expect(TokenType.IDENTIFIER).value
                context_vars.append(ir.FlowContextVar(name=var_name, entity_ref=entity_ref))
                self.skip_newlines()

            self.expect(TokenType.DEDENT)
            self.skip_newlines()

        # access: public | authenticated | persona(name1, name2) (optional, before start)
        if self.match(TokenType.ACCESS):
            self.advance()
            self.expect(TokenType.COLON)
            access_spec = self._parse_surface_access()
            self.skip_newlines()

        # priority: critical|high|medium|low (optional, before start)
        if self.match(TokenType.PRIORITY):
            self.advance()
            self.expect(TokenType.COLON)
            priority_token = self.expect_identifier_or_keyword()
            priority = self.enum_from_token(ir.BusinessPriority, priority_token)
            self.skip_newlines()

        # start at step StepName
        self.expect(TokenType.START)
        self.expect(TokenType.AT)
        self.expect(TokenType.STEP)
        start_step = self.expect_identifier_or_keyword().value
        self.skip_newlines()

        steps = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.STEP):
                step = self.parse_experience_step()
                steps.append(step)
            elif self.match(TokenType.EOF):
                self.error("Unexpected end of file inside experience block")  # type: ignore[attr-defined]
            else:
                token = self.current_token()
                self.error(  # type: ignore[attr-defined]
                    f"Expected 'step' inside experience block, "
                    f"got '{token.value}'. "
                    f"Each step must begin with the 'step' keyword."
                )

        self.expect(TokenType.DEDENT)

        # Auto-add context vars for entity_ref steps with creates (saves_to)
        existing_var_names = {v.name for v in context_vars}
        for step in steps:
            if step.entity_ref and step.saves_to:
                parts = step.saves_to.split(".", 1)
                if len(parts) == 2 and parts[0] == "context":
                    var_name = parts[1]
                    if var_name not in existing_var_names:
                        context_vars.append(
                            ir.FlowContextVar(name=var_name, entity_ref=step.entity_ref)
                        )
                        existing_var_names.add(var_name)

        return ir.ExperienceSpec(
            name=name,
            title=title,
            context=context_vars,
            start_step=start_step,
            steps=steps,
            access=access_spec,
            priority=priority,
            source=loc,
        )

    def parse_experience_step(self) -> ir.ExperienceStep:
        """Parse a ``step <name>:`` block inside an ``experience`` declaration.

        Refactored from the 184-line monolith into a sequential phase-helper
        composition (not dispatch-table — the phases have a fixed order and
        each is optional, so the #1097 helper doesn't apply). Each phase
        below conditionally consumes its keyword and mutates the
        :class:`_StepState` accumulator; the public function is a thin
        sequence of phase calls + a final builder.
        """
        self.expect(TokenType.STEP)
        name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _StepState()
        self._parse_step_kind_and_target(state)
        self._parse_step_creates(state)
        self._parse_step_fields(state)
        self._parse_step_defaults(state)
        self._parse_step_saves_to(state)
        self._parse_step_prefill(state)
        self._parse_step_when(state)
        self._parse_step_access(state)
        self._parse_step_transitions(state)
        self.expect(TokenType.DEDENT)
        return _build_experience_step(name, state)

    # ---------- parse_experience_step phase helpers ---------- #

    def _parse_step_kind_and_target(self, state: "_StepState") -> None:
        """Phase 1: ``entity: X`` shorthand OR ``kind: ...`` + target.

        Mutually exclusive — `entity:` infers ``kind=SURFACE`` and skips
        the explicit ``kind:`` + ``surface:`` / ``integration: action:``
        target pair. The first branch is the shorthand path.
        """
        if self.match(TokenType.ENTITY):
            self.advance()
            self.expect(TokenType.COLON)
            state.entity_ref = self.expect(TokenType.IDENTIFIER).value
            state.kind = ir.StepKind.SURFACE
            self.skip_newlines()
            return

        # Long form: kind: <enum> followed by target.
        self.expect(TokenType.KIND)
        self.expect(TokenType.COLON)
        kind_token = self.expect_identifier_or_keyword()
        state.kind = self.enum_from_token(ir.StepKind, kind_token)
        self.skip_newlines()

        if state.kind == ir.StepKind.SURFACE:
            self.expect(TokenType.SURFACE)
            state.surface = self.expect(TokenType.IDENTIFIER).value
            self.skip_newlines()
        elif state.kind == ir.StepKind.INTEGRATION:
            self.expect(TokenType.INTEGRATION)
            state.integration = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ACTION)
            state.action = self.expect(TokenType.IDENTIFIER).value
            self.skip_newlines()

    def _parse_step_creates(self, state: "_StepState") -> None:
        """``creates: varname`` — shorthand for ``saves_to: context.varname``."""
        if not self.match(TokenType.CREATES):
            return
        self.advance()
        self.expect(TokenType.COLON)
        creates_var = self.expect(TokenType.IDENTIFIER).value
        state.saves_to = f"context.{creates_var}"
        self.skip_newlines()

    def _parse_step_fields(self, state: "_StepState") -> None:
        """``fields: f1, f2, ...`` — restrict the auto-form to a subset."""
        if not self.match(TokenType.FIELDS):
            return
        self.advance()
        self.expect(TokenType.COLON)
        fields_list: list[str] = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.COMMA):
            self.advance()
            fields_list.append(self.expect_identifier_or_keyword().value)
        state.fields = fields_list
        self.skip_newlines()

    def _parse_step_defaults(self, state: "_StepState") -> None:
        """``defaults:`` block — shorthand prefills with ``$var`` → ``context.var.id``."""
        if not self.match(TokenType.DEFAULTS):
            return
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            if self.match(TokenType.STRING):
                expr = f'"{self.advance().value}"'
            elif self.match(TokenType.DOLLAR):
                self.advance()
                var_name = self.expect(TokenType.IDENTIFIER).value
                expr = f"context.{var_name}.id"
            else:
                expr = self._parse_dotted_path()
            state.prefills.append(ir.StepPrefill(field=field_name, expression=expr))
            self.skip_newlines()
        self.expect(TokenType.DEDENT)
        self.skip_newlines()

    def _parse_step_saves_to(self, state: "_StepState") -> None:
        """``saves_to: <dotted.path>`` — explicit context-binding."""
        if not self.match(TokenType.SAVES_TO):
            return
        self.advance()
        self.expect(TokenType.COLON)
        state.saves_to = self._parse_dotted_path()
        self.skip_newlines()

    def _parse_step_prefill(self, state: "_StepState") -> None:
        """``prefill:`` block — explicit field → expression list."""
        if not self.match(TokenType.PREFILL):
            return
        self.advance()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break
            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            if self.match(TokenType.STRING):
                expr = f'"{self.advance().value}"'
            else:
                expr = self._parse_dotted_path()
            state.prefills.append(ir.StepPrefill(field=field_name, expression=expr))
            self.skip_newlines()
        self.expect(TokenType.DEDENT)
        self.skip_newlines()

    def _parse_step_when(self, state: "_StepState") -> None:
        """``when: <expression>`` — raw token stream up to newline/dedent/EOF."""
        if not self.match(TokenType.WHEN):
            return
        self.advance()
        self.expect(TokenType.COLON)
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE) and not self.match(TokenType.DEDENT):
            tok = self.current_token()
            if tok.type == TokenType.EOF:
                break
            parts.append(tok.value)
            self.advance()
        state.when = " ".join(parts)
        self.skip_newlines()

    def _parse_step_access(self, state: "_StepState") -> None:
        """``access: public | authenticated | persona(...)``"""
        if not self.match(TokenType.ACCESS):
            return
        self.advance()
        self.expect(TokenType.COLON)
        state.access = self._parse_surface_access()
        self.skip_newlines()

    def _parse_step_transitions(self, state: "_StepState") -> None:
        """``on <event> -> step <name>`` — zero or more transitions."""
        while self.match(TokenType.ON):
            self.advance()
            event = self.expect_identifier_or_keyword().value
            self.expect(TokenType.ARROW)
            self.expect(TokenType.STEP)
            next_step = self.expect_identifier_or_keyword().value
            state.transitions.append(
                ir.StepTransition(event=event, next_step=next_step),
            )
            self.skip_newlines()


# ============================================================ #
# parse_experience_step — sequential-phase decomposition       #
# ============================================================ #
#
# Unlike the dispatch-table refactors (#1097), an experience step
# has a *fixed-order* sequence of optional phases. The 184-line
# monolith was split (v0.70.33) into a `_StepState` accumulator,
# 9 phase helpers on the mixin (each conditionally consumes its
# keyword + mutates state), and this builder. The public function
# becomes ~25 lines of orchestration.


@dataclass
class _StepState:
    """Accumulator for :meth:`ServiceParserMixin.parse_experience_step`."""

    kind: ir.StepKind = ir.StepKind.SURFACE
    surface: str | None = None
    entity_ref: str | None = None
    integration: str | None = None
    action: str | None = None
    saves_to: str | None = None
    fields: list[str] | None = None
    prefills: list[ir.StepPrefill] = field(default_factory=list)
    when: str | None = None
    access: ir.SurfaceAccessSpec | None = None
    transitions: list[ir.StepTransition] = field(default_factory=list)


def _build_experience_step(name: str, state: _StepState) -> ir.ExperienceStep:
    return ir.ExperienceStep(
        name=name,
        kind=state.kind,
        surface=state.surface,
        entity_ref=state.entity_ref,
        integration=state.integration,
        action=state.action,
        saves_to=state.saves_to,
        fields=state.fields,
        prefills=state.prefills,
        when=state.when,
        transitions=state.transitions,
        access=state.access,
    )
